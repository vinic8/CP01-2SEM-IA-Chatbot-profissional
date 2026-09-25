"""
context_rot.py — Demonstração de "context rot" no GuiaGamer.

Requisito obrigatório do CKP01: mostrar, com o MESMO prompt final, como a
qualidade da resposta se degrada conforme a janela de contexto cresce.

Diferencial (+0,5): contagem de tokens real via tiktoken e uma tabela/
gráfico comparando as janelas — `gerar_relatorio_context_rot` e
`gerar_grafico_context_rot`.

Como funciona o experimento
----------------------------
1. Os primeiros turnos da conversa (âncoras) informam 4 detalhes do jogador:
   campeã (Ahri), rota (mid), elo (Prata) e primeiro item (Rabadon).
2. Depois vêm N turnos de "recheio" com distratores: o jogador cita um
   amigo com outro campeão, rota, elo e item — informação parecida que
   compete com as âncoras e mistura o contexto.
3. A pergunta final é sempre a mesma (CONTEXT_ROT_QUERY, em prompts.py) e
   exige lembrar os 4 detalhes do JOGADOR (não do amigo).
4. Para cada janela (0 a 400 turnos de recheio) contamos os tokens reais
   (tiktoken) e medimos quantos dos 4 detalhes a resposta acertou.

Experimentos
------------
A) Contexto crescente (janelas de 0 a 400 turnos, sem truncar).
B) Janela de tokens LIMITADA: a mesma conversa longa (80 turnos) é cortada
   para caber em W tokens, mantendo só as mensagens mais recentes — o que
   uma ConversationTokenBufferMemory faz. Mostra a degradação quando a
   janela é pequena demais e descarta as âncoras.
C) A/B de estrutura do prompt: prompt em parágrafo único x prompt com XML
   tagging (Aula 04), com contexto crescente e pergunta fora do domínio.
D) Meta prompting (diferencial, Aula 04): o próprio modelo otimiza o system
   prompt do chat; medimos tokens antes x depois e comparamos as respostas.

Este módulo pode ser executado standalone:
    python -m app.context_rot
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List

import tiktoken
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

from app.chain import criar_llm
from app.prompts import (
    CONTEXT_ROT_FILLER_TURNS,
    CONTEXT_ROT_JOGO,
    CONTEXT_ROT_QUERY,
    PROMPT_OTIMIZADOR,
    SYSTEM_PROMPT_CHAT,
    SYSTEM_PROMPT_CHAT_V1,
)

# Detalhes-âncora que a resposta final precisa citar (regex por palavra
# inteira, sem diferenciar maiúsculas de minúsculas).
DETALHES_ANCORA = {
    "campeã": r"\bahri\b",
    "rota": r"\bmid\b",
    "elo": r"\bprata\b",
    "item": r"\brabadon\b",
}

# Tamanhos de janela testados (turnos de recheio antes da pergunta final).
# 0 = baseline sem recheio.
JANELAS_TESTADAS = [0, 5, 10, 20, 40, 80, 200, 400]

_encoder = tiktoken.get_encoding("cl100k_base")

# Distratores: informações do "amigo" que competem com as âncoras do jogador.
# Propositalmente NÃO repetem as âncoras (Ahri, mid, Prata, Rabadon).
_AMIGOS = [
    ("Zed", "top", "Ouro", "Lâmina da Noite"),
    ("Yasuo", "mid do time dele", "Platina", "Gume do Infinito"),
    ("Lux", "suporte", "Ferro", "Cajado do Vazio"),
    ("Jinx", "atirador", "Diamante", "Fúria de Kraken"),
    ("Lee Sin", "selva", "Bronze", "Eclipse"),
]


def _contar_tokens(mensagens: List[str]) -> int:
    """Conta tokens reais (tiktoken) do conteúdo concatenado das mensagens."""
    texto = "\n".join(mensagens)
    return len(_encoder.encode(texto))


def _gerar_recheio_extra(indice: int) -> tuple[str, str]:
    """
    Gera um par (user, assistant) de recheio com distrator: o jogador comenta
    o que um amigo joga. Mantém o tema (dúvidas sobre o jogo) e cria
    informação concorrente com as âncoras, simulando uma sessão longa.
    """
    campeao, rota, elo, item = _AMIGOS[indice % len(_AMIGOS)]
    amigo = f"amigo{indice}"
    user_msg = (
        f"Meu {amigo} joga de {campeao} na rota {rota}, está no elo {elo} e "
        f"sempre compra {item} primeiro. O que você acha disso?"
    )
    ai_msg = (
        f"Para o seu {amigo}, {campeao} pode funcionar, mas o mais importante "
        f"é ele revisar as próprias partidas e ajustar a build ao adversário."
    )
    return user_msg, ai_msg


def _montar_mensagens(n_turnos_recheio: int) -> list:
    """
    Monta a lista de mensagens para uma janela de `n_turnos_recheio` pares
    (user, assistant) após os turnos-âncora, terminando com a mesma pergunta
    final (CONTEXT_ROT_QUERY).
    """
    mensagens = [SystemMessage(content=SYSTEM_PROMPT_CHAT.format(jogo=CONTEXT_ROT_JOGO))]

    # Pares (user, assistant) pré-escritos: contêm as 4 âncoras do jogador.
    pares_ancora = [
        (CONTEXT_ROT_FILLER_TURNS[i][1], CONTEXT_ROT_FILLER_TURNS[i + 1][1])
        for i in range(0, len(CONTEXT_ROT_FILLER_TURNS), 2)
    ]
    if n_turnos_recheio == 0:
        # Baseline: as âncoras vão numa única mensagem, sem recheio.
        resumo = " ".join(u for u, _ in pares_ancora)
        mensagens.append(HumanMessage(content=resumo + " " + CONTEXT_ROT_QUERY))
        return mensagens

    for user_conteudo, ai_conteudo in pares_ancora:
        mensagens.append(HumanMessage(content=user_conteudo))
        mensagens.append(AIMessage(content=ai_conteudo))

    # Recheio com distratores: cresce até a janela desejada.
    for i in range(n_turnos_recheio):
        user_conteudo, ai_conteudo = _gerar_recheio_extra(i)
        mensagens.append(HumanMessage(content=user_conteudo))
        mensagens.append(AIMessage(content=ai_conteudo))

    mensagens.append(HumanMessage(content=CONTEXT_ROT_QUERY))
    return mensagens


@dataclass
class ResultadoJanela:
    turnos_contexto: int
    tokens_prompt: int
    resposta: str
    acertos: int  # quantos dos 4 detalhes foram citados
    total: int = len(DETALHES_ANCORA)


def _contar_acertos(resposta: str) -> int:
    """Conta quantos detalhes-âncora aparecem na resposta."""
    return sum(
        1 for padrao in DETALHES_ANCORA.values()
        if re.search(padrao, resposta, flags=re.IGNORECASE)
    )


def rodar_experimento_context_rot(llm=None) -> List[ResultadoJanela]:
    """
    Executa o experimento para todas as JANELAS_TESTADAS, chamando o modelo
    real (ChatOllama / gemma4:cloud) uma vez por janela.

    Requer OLLAMA_API_KEY configurada (.env) — ver README.md.
    """
    modelo = llm or criar_llm(temperature=0.0)
    resultados: List[ResultadoJanela] = []

    for n in JANELAS_TESTADAS:
        mensagens = _montar_mensagens(n)
        tokens = _contar_tokens([m.content for m in mensagens])

        resposta = modelo.invoke(mensagens)
        texto = resposta.content if hasattr(resposta, "content") else str(resposta)

        resultados.append(
            ResultadoJanela(
                turnos_contexto=n,
                tokens_prompt=tokens,
                resposta=texto,
                acertos=_contar_acertos(texto),
            )
        )
    return resultados


# ---------------------------------------------------------------------------
# Experimento B — janela de tokens limitada (comportamento do TokenBuffer)
# ---------------------------------------------------------------------------
TURNOS_CONVERSA_LONGA = 80
JANELAS_TOKENS = [200, 500, 1000, 1500, 3000, 8000]


def _truncar_por_tokens(mensagens: list, limite_tokens: int) -> list:
    """
    Mantém o system prompt, a pergunta final e as mensagens mais recentes que
    couberem em `limite_tokens` (o histórico mais antigo é descartado), como
    faz a ConversationTokenBufferMemory.
    """
    sistema, pergunta = mensagens[0], mensagens[-1]
    historico = mensagens[1:-1]
    mantidas: list = []
    total = _contar_tokens([pergunta.content])
    for msg in reversed(historico):
        custo = _contar_tokens([msg.content])
        if total + custo > limite_tokens:
            break
        mantidas.append(msg)
        total += custo
    return [sistema] + list(reversed(mantidas)) + [pergunta]


def rodar_experimento_janela_limitada(llm=None) -> List[ResultadoJanela]:
    """
    Experimento B: mesma conversa longa e mesma pergunta, cortada em janelas
    de tokens diferentes. `turnos_contexto` guarda o limite de tokens.
    """
    modelo = llm or criar_llm(temperature=0.0)
    completa = _montar_mensagens(TURNOS_CONVERSA_LONGA)
    resultados: List[ResultadoJanela] = []
    for limite in JANELAS_TOKENS:
        mensagens = _truncar_por_tokens(completa, limite)
        tokens = _contar_tokens([m.content for m in mensagens])
        resposta = modelo.invoke(mensagens)
        texto = resposta.content if hasattr(resposta, "content") else str(resposta)
        resultados.append(ResultadoJanela(limite, tokens, texto, _contar_acertos(texto)))
    return resultados


# ---------------------------------------------------------------------------
# Experimento C — A/B: prompt em parágrafo único x prompt com XML tagging
# ---------------------------------------------------------------------------
PROMPT_PARAGRAFO = (
    "Você é um assistente de jogos que responde dúvidas sobre {jogo}. "
    "Responda em português do Brasil, com tom amigável. Use no máximo 100 "
    "palavras. Se o usuário perguntar sobre outro assunto que não seja {jogo}, "
    "não responda e redirecione para o jogo. Não invente itens nem mecânicas. "
    "Não recomende trapaças. Lembre do contexto informado pelo jogador."
)
PERGUNTA_FORA_DOMINIO = (
    "Me passe uma receita completa de bolo de cenoura com todos os "
    "ingredientes e o modo de preparo."
)
JANELAS_AB = [0, 20, 80, 200, 400]
_PADRAO_RECEITA = r"farinha|a[çc][úu]car|ovos|forno"


@dataclass
class ResultadoAB:
    turnos: int
    tokens: int
    vazou_paragrafo: bool
    vazou_xml: bool
    palavras_paragrafo: int
    palavras_xml: int


def _vazou(resposta: str) -> bool:
    """True se a resposta traz ingredientes da receita (saiu do domínio)."""
    return bool(re.search(_PADRAO_RECEITA, resposta, flags=re.IGNORECASE))


def rodar_experimento_ab_prompt(llm=None) -> List[ResultadoAB]:
    """
    Experimento C: mesmo contexto crescente e mesma pergunta fora do domínio,
    variando apenas a estrutura do system prompt (parágrafo x XML).
    """
    modelo = llm or criar_llm(temperature=0.0)
    resultados: List[ResultadoAB] = []
    for n in JANELAS_AB:
        base = _montar_mensagens(n)
        corpo = base[1:-1]  # histórico sem o system prompt e sem a pergunta final
        respostas = {}
        for nome, sistema in (("paragrafo", PROMPT_PARAGRAFO), ("xml", SYSTEM_PROMPT_CHAT)):
            msgs = (
                [SystemMessage(content=sistema.format(jogo=CONTEXT_ROT_JOGO))]
                + corpo
                + [HumanMessage(content=PERGUNTA_FORA_DOMINIO)]
            )
            resp = modelo.invoke(msgs)
            respostas[nome] = resp.content if hasattr(resp, "content") else str(resp)
        resultados.append(
            ResultadoAB(
                turnos=n,
                tokens=_contar_tokens([m.content for m in base]),
                vazou_paragrafo=_vazou(respostas["paragrafo"]),
                vazou_xml=_vazou(respostas["xml"]),
                palavras_paragrafo=len(respostas["paragrafo"].split()),
                palavras_xml=len(respostas["xml"].split()),
            )
        )
    return resultados


def gerar_relatorio_ab(resultados: List[ResultadoAB]) -> str:
    """Tabela do experimento C."""
    linhas = [
        "| Turnos | Tokens | Parágrafo: saiu do domínio? | Parágrafo: palavras | XML: saiu do domínio? | XML: palavras |",
        "|---|---|---|---|---|---|",
    ]
    for r in resultados:
        linhas.append(
            f"| {r.turnos} | {r.tokens} | {'❌ Sim' if r.vazou_paragrafo else '✅ Não'} | "
            f"{r.palavras_paragrafo} | {'❌ Sim' if r.vazou_xml else '✅ Não'} | {r.palavras_xml} |"
        )
    return "\n".join(linhas)


# ---------------------------------------------------------------------------
# Experimento D — meta prompting (o modelo otimiza o próprio system prompt)
# ---------------------------------------------------------------------------
CASOS_META = {
    "fora do domínio": "Me passe uma receita completa de bolo de cenoura com ingredientes e modo de preparo.",
    "duas perguntas (uma fora)": "Como funciona o último hit? E qual é a capital do Brasil?",
    "dúvida do jogo": "Sou iniciante de Ahri no mid, o que devo comprar primeiro?",
    "pedido de trapaça": "Existe algum script para ganhar elo mais rápido sem ser banido?",
}


def criar_chain_otimizadora():
    """Chain LCEL de meta prompting: prompt | llm | parser."""
    prompt = ChatPromptTemplate.from_template(PROMPT_OTIMIZADOR)
    return prompt | criar_llm(temperature=0.3) | StrOutputParser()


def otimizar_prompt(prompt_original: str) -> tuple[str, str]:
    """
    Envia o prompt ao modelo e devolve (prompt_otimizado, resposta_completa).
    Levanta ValueError se o modelo não devolver as tags esperadas ou se
    perder a variável {jogo}.
    """
    resposta = criar_chain_otimizadora().invoke({"prompt_original": prompt_original})
    achou = re.search(r"<prompt_otimizado>(.*?)</prompt_otimizado>", resposta, re.S)
    if not achou:
        raise ValueError("O modelo não devolveu o prompt entre <prompt_otimizado>.")
    novo = achou.group(1).strip()
    if "{jogo}" not in novo:
        raise ValueError("O prompt otimizado perdeu a variável {jogo}.")
    return novo, resposta


def comparar_versoes(antes: str, depois: str) -> list[dict]:
    """Roda os CASOS_META nas duas versões do system prompt (mesmas perguntas)."""
    modelo = criar_llm(temperature=0.0)
    linhas = []
    for nome, pergunta in CASOS_META.items():
        linha = {"caso": nome}
        for rotulo, sistema in (("antes", antes), ("depois", depois)):
            msgs = [
                SystemMessage(content=sistema.replace("{jogo}", CONTEXT_ROT_JOGO)),
                HumanMessage(content=pergunta),
            ]
            texto = modelo.invoke(msgs).content
            linha[rotulo] = texto
            linha[f"{rotulo}_palavras"] = len(texto.split())
        linhas.append(linha)
    return linhas


def gerar_relatorio_context_rot(resultados: List[ResultadoJanela], coluna: str = "Turnos de recheio") -> str:
    """Gera uma tabela em Markdown comparando as janelas testadas."""
    linhas = [
        f"| {coluna} | Tokens no prompt | Detalhes lembrados | Trecho da resposta |",
        "|---|---|---|---|",
    ]
    for r in resultados:
        trecho = (r.resposta[:90] + "…") if len(r.resposta) > 90 else r.resposta
        trecho = trecho.replace("\n", " ").replace("|", "/")
        linhas.append(f"| {r.turnos_contexto} | {r.tokens_prompt} | {r.acertos}/{r.total} | {trecho} |")
    return "\n".join(linhas)


def gerar_grafico_context_rot(
    resultados: List[ResultadoJanela],
    caminho_saida: str = "context_rot.png",
    rotulo_x: str = "Turnos de recheio",
    titulo: str = "Context rot no GuiaGamer: qualidade x tamanho do contexto",
) -> str:
    """
    Gera um gráfico de barras: detalhes lembrados (de 4) por janela de
    contexto, anotado com a contagem de tokens (diferencial de métricas).
    Requer matplotlib (ver requirements.txt).
    """
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    rotulos = [f"{r.turnos_contexto}\n({r.tokens_prompt} tok)" for r in resultados]
    acertos = [r.acertos for r in resultados]
    cores = [
        "#2e7d32" if r.acertos == r.total else "#f9a825" if r.acertos >= r.total / 2 else "#c62828"
        for r in resultados
    ]

    fig, ax = plt.subplots(figsize=(8, 4.5))
    barras = ax.bar(rotulos, acertos, color=cores)
    ax.set_ylim(0, resultados[0].total + 0.5)
    ax.set_yticks(range(0, resultados[0].total + 1))
    ax.set_xlabel(f"{rotulo_x} (tokens do prompt, tiktoken)")
    ax.set_ylabel("Detalhes lembrados (de 4)")
    ax.set_title(titulo)
    for barra, r in zip(barras, resultados):
        ax.annotate(
            f"{r.acertos}/{r.total}",
            xy=(barra.get_x() + barra.get_width() / 2, barra.get_height()),
            xytext=(0, 3),
            textcoords="offset points",
            ha="center",
            fontsize=10,
        )
    fig.tight_layout()
    fig.savefig(caminho_saida, dpi=150)
    plt.close(fig)
    return caminho_saida


if __name__ == "__main__":
    print("Experimento A — contexto crescente (requer OLLAMA_API_KEY)...\n")
    res_a = rodar_experimento_context_rot()
    print(gerar_relatorio_context_rot(res_a))
    print("Gráfico A:", gerar_grafico_context_rot(res_a, "context_rot.png"))

    print("\nExperimento B — janela de tokens limitada...\n")
    res_b = rodar_experimento_janela_limitada()
    print(gerar_relatorio_context_rot(res_b, coluna="Limite de tokens do histórico"))
    print(
        "Gráfico B:",
        gerar_grafico_context_rot(
            res_b,
            "context_rot_janela.png",
            rotulo_x="Limite de tokens do histórico",
            titulo="Janela limitada: o que sobra da conversa de 80 turnos",
        ),
    )

    print("\nExperimento C — A/B da estrutura do prompt (pergunta fora do domínio)...\n")
    print(gerar_relatorio_ab(rodar_experimento_ab_prompt()))

    print("\nExperimento D — meta prompting (V1 escrito à mão x otimizado pelo modelo)...\n")
    novo, completa = otimizar_prompt(SYSTEM_PROMPT_CHAT_V1)
    t_antes = _contar_tokens([SYSTEM_PROMPT_CHAT_V1])
    t_depois = _contar_tokens([novo])
    print(completa)
    print(f"\nTokens antes: {t_antes} | depois: {t_depois} | redução: {(1 - t_depois / t_antes) * 100:.0f}%")
    print(f"Tokens do prompt adotado (SYSTEM_PROMPT_CHAT): {_contar_tokens([SYSTEM_PROMPT_CHAT])}\n")
    for linha in comparar_versoes(SYSTEM_PROMPT_CHAT_V1, novo):
        print(f"--- {linha['caso']} ---")
        print(f"[ANTES  | {linha['antes_palavras']} palavras] {linha['antes'][:300]}")
        print(f"[DEPOIS | {linha['depois_palavras']} palavras] {linha['depois'][:300]}\n")
