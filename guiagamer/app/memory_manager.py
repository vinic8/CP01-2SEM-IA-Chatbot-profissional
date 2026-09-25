"""
memory_manager.py — Memória gerenciada do GuiaGamer.

Implementa a primeira das 2 chains da arquitetura da Aula 03: a
ConversationChain com memória, responsável pelo chat livre com o usuário.

Estratégia escolhida: ConversationTokenBufferMemory (1500 tokens)
-------------------------------------------------------------------
Justificativa (ver também README.md, seção "Justificativa da memória"):

Um assistente de dúvidas de jogo depende de detalhes precisos que o jogador
menciona ao longo da conversa: campeão e rota, elo/nível, modo de jogo,
itens que já possui, versão do jogo. Comparamos as 3 opções:

- ConversationBufferMemory (histórico completo): preserva 100% do
  contexto, mas cresce sem limite — em sessões longas o custo de tokens por
  chamada sobe a cada turno e a qualidade cai (context rot), sem ganho real,
  pois dúvidas antigas já resolvidas raramente importam para a atual.
- ConversationSummaryMemory (resumo via LLM): mantém o custo baixo, mas o
  resumo tende a perder detalhes específicos (ex.: "estou de Ahri no mid,
  elo Prata, primeiro item Rabadon") que mudam completamente a resposta
  correta. Também adiciona uma chamada extra ao LLM a cada turno.
- ConversationTokenBufferMemory (escolhida): mantém o histórico literal
  (sem perda por resumo) até um teto de tokens e depois descarta as trocas
  mais antigas. Equilibra fidelidade ao contexto recente — onde está a dúvida
  atual — com custo de tokens previsível e sem chamadas extras ao modelo.

1500 tokens é o teto da faixa exigida (800–1500). Como o system prompt
limita as respostas a ~100 palavras, o buffer comporta 5+ turnos completos.
"""

from __future__ import annotations

from langchain_classic.chains import ConversationChain
from langchain_classic.memory import (
    ConversationBufferMemory,
    ConversationSummaryMemory,
    ConversationTokenBufferMemory,
)
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from app.prompts import SYSTEM_PROMPT_CHAT

# Teto de tokens da memória — dentro da faixa 800–1500 exigida pelo CKP01.
MAX_TOKEN_LIMIT = 1500

# Template usado pela ConversationChain: ChatPromptTemplate com system message
# (persona em XML) e human message separados. {history} é preenchido pela
# memória (lista de mensagens) e {input} pela fala atual do usuário. A
# variável {jogo} é fixada via .partial() na criação da chain — a
# ConversationChain só aceita history e input como variáveis livres.
_CHAT_TEMPLATE = ChatPromptTemplate.from_messages(
    [
        ("system", SYSTEM_PROMPT_CHAT),
        MessagesPlaceholder(variable_name="history"),
        ("human", "{input}"),
    ]
)


# Estratégias de memória disponíveis (as 3 da Aula 02). O projeto usa
# "token_buffer" por padrão — justificativa no topo deste arquivo e no README.
ESTRATEGIAS_MEMORIA = ("buffer", "summary", "token_buffer")
ESTRATEGIA_PADRAO = "token_buffer"


def criar_memoria(
    llm: BaseChatModel,
    estrategia: str = ESTRATEGIA_PADRAO,
    max_token_limit: int = MAX_TOKEN_LIMIT,
):
    """
    Cria a memória gerenciada usada pelo chat, conforme a estratégia:

    - "buffer": guarda o histórico completo (custo cresce a cada turno);
    - "summary": o próprio LLM resume o histórico (custo fixo, perde detalhes);
    - "token_buffer": janela deslizante limitada em tokens (a escolhida).

    A TokenBuffer precisa de uma referência ao LLM porque usa o contador de
    tokens dele (llm.get_num_tokens_from_messages) para decidir quando podar
    as trocas mais antigas do histórico.
    """
    if estrategia == "buffer":
        return ConversationBufferMemory(memory_key="history", return_messages=True)
    if estrategia == "summary":
        return ConversationSummaryMemory(llm=llm, memory_key="history", return_messages=True)
    if estrategia == "token_buffer":
        return ConversationTokenBufferMemory(
            llm=llm,
            max_token_limit=max_token_limit,
            memory_key="history",
            return_messages=True,  # o MessagesPlaceholder espera lista de mensagens
        )
    raise ValueError(f"Estratégia inválida: {estrategia}. Use uma de {ESTRATEGIAS_MEMORIA}.")


def criar_chat_chain(
    llm: BaseChatModel,
    jogo: str,
    memory=None,
) -> ConversationChain:
    """
    Monta a ConversationChain (chain nº 1 da arquitetura de 2 chains da
    Aula 03): responsável pelo chat aberto com memória sobre o `jogo`.

    A segunda chain (pipeline LCEL para saída estruturada) fica em
    chain.py e é usada quando o usuário pede uma ficha de build/estratégia.
    """
    memoria = memory or criar_memoria(llm)
    return ConversationChain(
        llm=llm,
        memory=memoria,
        prompt=_CHAT_TEMPLATE.partial(jogo=jogo),
        verbose=False,
    )
