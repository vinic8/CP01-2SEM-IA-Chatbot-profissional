"""
main.py — Interface Gradio e entry point do GuiaGamer.

Roda localmente com:
    python -m app.main

Abre em http://localhost:7860

Visual: tema "Cybernetic Arcade" (avatar do GuiaGamer), com o chat exibido
como o log de conversa de um jogo.

A interface expõe as DUAS chains da arquitetura do CKP01 (Aula 03):
  1. Aba "Chat" — ConversationChain com memória (memory_manager.py), para
     tirar dúvidas sobre o jogo escolhido.
  2. Aba "Ficha de build" — pipeline LCEL (chain.py) que roda separadamente
     e devolve uma FichaEstrategia validada por Pydantic.
"""

from __future__ import annotations

import base64
import os
import tempfile
from urllib.parse import quote

import gradio as gr

from app.chain import criar_llm, gerar_ficha
from app.memory_manager import criar_chat_chain
from app.prompts import JOGOS_SUPORTADOS
from app.schemas import FichaEstrategia

# Mensagem de boas-vindas exibida no log do chat (só na interface; não entra
# na memória da ConversationChain).
SAUDACAO = {
    "role": "assistant",
    "content": (
        "▶ **PLAYER 1 conectado!** Escolha o jogo acima e mande sua dúvida "
        "sobre mecânicas, builds ou estratégias."
    ),
}

# ---------------------------------------------------------------------------
# Estado compartilhado: um único LLM e a chain de chat com memória (uma por
# jogo selecionado), criados sob demanda.
# ---------------------------------------------------------------------------
_llm = None
_llm_json = None
_chat_chain = None
_jogo_atual = None


def _get_llm():
    global _llm
    if _llm is None:
        _llm = criar_llm()
    return _llm


def _get_llm_json():
    """LLM com format="json" para a chain estruturada (Aula 03)."""
    global _llm_json
    if _llm_json is None:
        _llm_json = criar_llm(formato_json=True)
    return _llm_json


def _get_chat_chain(jogo: str):
    """Cria a chain do jogo; ao trocar de jogo a memória é reiniciada."""
    global _chat_chain, _jogo_atual
    if _chat_chain is None or _jogo_atual != jogo:
        _chat_chain = criar_chat_chain(_get_llm(), jogo)
        _jogo_atual = jogo
    return _chat_chain


# ---------------------------------------------------------------------------
# Callbacks da interface
# ---------------------------------------------------------------------------
def responder_chat(mensagem: str, historico_ui: list, jogo: str) -> tuple:
    """Callback da aba de chat — usa a ConversationChain com memória."""
    chain = _get_chat_chain(jogo)
    resposta = chain.predict(input=mensagem)
    # Gradio 6 usa o formato de mensagens (role/content), não tuplas.
    historico_ui = historico_ui + [
        {"role": "user", "content": mensagem},
        {"role": "assistant", "content": resposta},
    ]
    return "", historico_ui


def reiniciar_memoria():
    """Zera a memória da conversa (nova sessão ou troca de jogo)."""
    global _chat_chain, _jogo_atual
    _chat_chain = None
    _jogo_atual = None
    return [SAUDACAO], ""


def _formatar_ficha(ficha: FichaEstrategia) -> str:
    """Formata a FichaEstrategia (Pydantic) em Markdown legível para a UI."""
    componentes = "\n".join(f"- {c}" for c in ficha.componentes)
    passos = "\n".join(f"{i}. {p}" for i, p in enumerate(ficha.passo_a_passo, start=1))
    erros = "\n".join(f"- {e}" for e in ficha.erros_comuns)
    return f"""\
## {ficha.titulo_build} — {ficha.jogo.value}

**Objetivo:** {ficha.objetivo}
**Dificuldade:** {ficha.dificuldade.value}
**Nota de eficácia:** {ficha.nota_eficacia}/10

### Componentes
{componentes}

### Passo a passo
{passos}

### Erros comuns / pontos fracos
{erros}
"""


def gerar_ficha_ui(jogo: str, objetivo: str) -> str:
    """Callback da aba de ficha — usa o pipeline LCEL + Pydantic."""
    if not objetivo or not objetivo.strip():
        return "⚠️ Descreva o seu objetivo antes de gerar a ficha."
    try:
        ficha = gerar_ficha(jogo, objetivo, llm=_get_llm_json())
    except Exception as exc:  # noqa: BLE001 — mostramos o erro na própria UI
        return f"❌ Erro ao gerar ficha: {exc}"
    return _formatar_ficha(ficha)


# ---------------------------------------------------------------------------
# Visual "Cybernetic Arcade" (avatar do GuiaGamer + ícones pixel art)
# ---------------------------------------------------------------------------
# Avatar (192x192 JPEG) embutido em base64 para manter o projeto na estrutura
# de arquivos do checkpoint; é gravado em um arquivo temporário ao iniciar.
_AVATAR_B64 = (
    "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"
    "nOvM68J0yey+zrwnXxOvM6Sdf//Z"
)


def _caminho_avatar() -> str:
    """Grava o avatar embutido em um arquivo temporário e devolve o caminho."""
    caminho = os.path.join(tempfile.gettempdir(), "guiagamer_avatar.jpg")
    if not os.path.exists(caminho):
        with open(caminho, "wb") as arquivo:
            arquivo.write(base64.b64decode(_AVATAR_B64))
    return caminho

# ---------------------------------------------------------------------------
# Ícones em pixel art (desenhados em código, inspirados em um pack de UI de
# jogos 8-bit: coração, balão de fala, espada, escudo, pergaminho...).
# Cada ícone é uma grade de caracteres; cada caractere é uma cor da paleta.
# ---------------------------------------------------------------------------
_PALETA = {
    "R": "#e53935", "D": "#8e1b1b", "W": "#ffd6d0", "Y": "#ffd54f", "O": "#f08a24",
    "B": "#3b6fb6", "N": "#1c2b4a", "G": "#9aa5b1", "L": "#d5dbe2", "C": "#f7e0b8",
    "K": "#4a2c12", "T": "#7ee7ff", "P": "#ff6b9d", "g": "#4caf50",
}

_ICONES = {
    "heart": [
        ".RRR.RRR.",
        "RWRRRRRRR",
        "RRRRRRRRR",
        "RRRRRRRRD",
        ".RRRRRRD.",
        "..RRRRD..",
        "...RRD...",
        "....D....",
    ],
    "bubble": [
        "..DDDDDDDDDD..",
        ".DCCCCCCCCCCD.",
        "DCCCCCCCCCCCCD",
        "DCCRRRRRRRRCCD",
        "DCCCCCCCCCCCCD",
        "DCCRRRRRRCCCCD",
        "DCCCCCCCCCCCCD",
        ".DCCCCCCCCCCD.",
        "..DDDDDCDDDD..",
        "......DCD.....",
        ".......D......",
    ],
    "scroll": [
        "..KKKKKKKKK.",
        ".KCCCCCCCCCK",
        ".KCKKKKKKCCK",
        ".KCCCCCCCCCK",
        ".KCKKKKKKKCK",
        ".KCCCCCCCCCK",
        ".KCKKKKKCCCK",
        ".KCCCCCCCCCK",
        "..KKKKKKKKK.",
    ],
    "sword": [
        "..........LL",
        ".........LLG",
        "........LLG.",
        ".......LLG..",
        "......LLG...",
        ".K...LLG....",
        "..KKLLG.....",
        "...KKG......",
        "..KKKK......",
        ".KK..KK.....",
        "KK..........",
        "K...........",
    ],
    "shield": [
        "LLLLLLLLLL",
        "LNNNNNNNNL",
        "LNNNGGNNNL",
        "LNNNGGNNNL",
        "LNGGGGGGNL",
        "LNGGGGGGNL",
        "LNNNGGNNNL",
        "LNNNGGNNNL",
        ".LNNGGNNL.",
        "..LNNNNL..",
        "...LLLL...",
    ],
    "trophy": [
        ".OOOOOOOOO.",
        "OYYYYYYYYYO",
        "OYYYYYYYYYO",
        "OYYYYYYYYYO",
        ".OYYYYYYYO.",
        "..OYYYYYO..",
        "...OYYYO...",
        "....OYO....",
        "....OYO....",
        "..OOOOOOO..",
        ".OYYYYYYYO.",
    ],
    "potion": [
        "...KKK...",
        "...KCK...",
        "...BBB...",
        "..BTTTB..",
        "..BTTTB..",
        ".BTTTTTB.",
        "BTTTTTTTB",
        "BTTWTTTTB",
        "BTTTTTTTB",
        ".BTTTTTB.",
        "..BBBBB..",
    ],
    "smile": [
        "..OOOOOO..",
        ".OYYYYYYO.",
        "OYYYYYYYYO",
        "OYYKYYKYYO",
        "OYYKYYKYYO",
        "OYYYYYYYYO",
        "OYKYYYYKYO",
        "OYYKKKKYYO",
        ".OYYYYYYO.",
        "..OOOOOO..",
    ],
    "arrow": [
        "....KK..",
        "....KKK.",
        "KKKKKKKK",
        "KKKKKKKK",
        "....KKK.",
        "....KK..",
    ],
}


def _icone_svg(mapa: list[str]) -> tuple[int, int, str]:
    """Converte a grade de caracteres em (largura, altura, url CSS de um SVG)."""
    altura, largura = len(mapa), len(mapa[0])
    retangulos = []
    for y, linha in enumerate(mapa):
        assert len(linha) == largura, "linha do ícone com largura diferente"
        x = 0
        while x < largura:
            cor = linha[x]
            if cor == ".":
                x += 1
                continue
            inicio = x
            while x < largura and linha[x] == cor:
                x += 1
            retangulos.append(
                f'<rect x="{inicio}" y="{y}" width="{x - inicio}" height="1" fill="{_PALETA[cor]}"/>'
            )
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {largura} {altura}" '
        f'shape-rendering="crispEdges">{"".join(retangulos)}</svg>'
    )
    return largura, altura, 'url("data:image/svg+xml;utf8,' + quote(svg, safe="") + '")'


def _css_icones() -> str:
    """Gera as classes .ico-<nome> (uso em HTML) e as variáveis para ::before."""
    css = [
        ".ico { --s: 3; display: inline-block; vertical-align: middle; image-rendering: pixelated;"
        " background-size: 100% 100%; background-repeat: no-repeat; }"
    ]
    for nome, mapa in _ICONES.items():
        largura, altura, url = _icone_svg(mapa)
        css.append(
            f".ico-{nome} {{ width: calc({largura}px * var(--s)); height: calc({altura}px * var(--s));"
            f" background-image: {url}; }}"
        )
        css.append(f":root {{ --url-{nome}: {url}; --w-{nome}: {largura}; --h-{nome}: {altura}; }}")
    return "\n".join(css)


def _pseudo_icone(seletor: str, nome: str, escala: int = 3) -> str:
    """Regra que coloca o ícone `nome` antes do conteúdo de `seletor`."""
    return (
        f"{seletor}::before {{ content: ''; display: inline-block; vertical-align: middle;"
        f" margin-right: 10px; image-rendering: pixelated; background: var(--url-{nome}) center / 100% 100% no-repeat;"
        f" width: calc(var(--w-{nome}) * {escala}px); height: calc(var(--h-{nome}) * {escala}px); }}"
    )


TEMA = gr.themes.Base(
    primary_hue="cyan",
    secondary_hue="pink",
    neutral_hue="slate",
    font=[gr.themes.GoogleFont("VT323"), "monospace"],
    font_mono=[gr.themes.GoogleFont("VT323"), "monospace"],
).set(
    body_background_fill="#0b1530",
    body_background_fill_dark="#0b1530",
    body_text_color="#d8f6ff",
    body_text_color_dark="#d8f6ff",
    block_background_fill="#0f1c3d",
    block_background_fill_dark="#0f1c3d",
    block_border_color="#2a4b7c",
    block_border_color_dark="#2a4b7c",
    block_label_background_fill="#0f1c3d",
    block_label_background_fill_dark="#0f1c3d",
    block_label_text_color="#7ee7ff",
    block_label_text_color_dark="#7ee7ff",
    input_background_fill="#08112a",
    input_background_fill_dark="#08112a",
    input_border_color="#2a4b7c",
    input_border_color_dark="#2a4b7c",
)

CSS = """
@import url('https://fonts.googleapis.com/css2?family=Press+Start+2P&family=VT323&display=swap');

:root, .dark {
  --neon-cyan: #7ee7ff; --neon-pink: #ff6b9d; --neon-yellow: #ffd45e;
  --rainbow: linear-gradient(90deg, #ff6b9d, #ffd45e, #6bff8f, #7ee7ff, #5b8cff, #b36bff);
  --moldura: #0a0f1f;  /* contorno escuro estilo janela de jogo 8-bit */
  --realce: #3b6fb6;
}
html, body {
  height: 100vh; margin: 0; overflow: hidden;
  background: radial-gradient(circle at 50% -10%, #1d3568 0%, #0b1530 55%, #070d20 100%) fixed !important;
}
/* tela cheia, sem rolagem da página: só o log do chat rola por dentro */
.gradio-container, .gradio-container .main, .gradio-container .wrap, .gradio-container .contain {
  max-width: 100% !important; width: 100% !important;
}
.gradio-container {
  background: transparent !important; font-family: 'VT323', monospace !important; font-size: 20px;
  margin: 0 !important; padding: 10px 2vw !important; height: 100vh; overflow-x: hidden; overflow-y: auto;
  gap: 8px !important;
}
.gradio-container::before {
  content: ""; position: fixed; inset: 0; pointer-events: none; opacity: .06;
  background-image: linear-gradient(#7ee7ff 1px, transparent 1px), linear-gradient(90deg, #7ee7ff 1px, transparent 1px);
  background-size: 24px 24px;
}
/* janelas quadradas com contorno de pixel (só nos blocos principais) */
.block { border-radius: 0 !important; }
#sel-jogo, #sel-jogo-ficha, #chat-log, #ficha-out, #campo-msg, #campo-obj {
  border: 4px solid var(--moldura) !important; box-shadow: inset 0 0 0 3px var(--realce) !important;
  padding: 6px 12px !important; gap: 4px !important;
}
.block:has(#hud) { border: none !important; box-shadow: none !important; padding: 0 !important; background: transparent !important; }
.gradio-container .form { border: none !important; box-shadow: none !important; padding: 0 !important; background: transparent !important; }
#chat-log .message-buttons, #chat-log .message-buttons-left, #chat-log .message-buttons-right { display: none !important; }

/* ---------- HUD / cabeçalho ---------- */
#hud {
  display: flex; align-items: center; gap: 18px; padding: 10px 18px; margin: 0;
  background: linear-gradient(#0f1c3d, #0f1c3d) padding-box, var(--rainbow) border-box;
  border: 4px solid transparent; border-radius: 0;
  box-shadow: 0 0 0 3px var(--moldura), 0 0 22px rgba(126, 231, 255, .25);
}
#hud .avatar { width: 68px; height: 68px; border-radius: 50%; flex: none; padding: 3px; background: var(--rainbow); box-shadow: 0 0 16px rgba(179, 107, 255, .55); }
#hud .avatar img { width: 100%; height: 100%; border-radius: 50%; display: block; }
#hud .titulo { font-family: 'Press Start 2P', monospace; font-size: 22px; line-height: 1.3; color: var(--neon-cyan); text-shadow: 0 0 10px rgba(126, 231, 255, .8), 3px 3px 0 #ff6b9d55; display: flex; align-items: center; gap: 12px; }
#hud .sub { font-size: 20px; color: #a9c7e8; letter-spacing: 1px; margin-top: 2px; }
#hud .status { margin-left: auto; display: flex; align-items: center; gap: 14px; }
#hud .vidas { display: flex; gap: 4px; }
#hud .barras { display: flex; flex-direction: column; gap: 6px; }
#hud .barra { display: flex; align-items: center; gap: 6px; font-family: 'Press Start 2P', monospace; font-size: 9px; color: #d8f6ff; }
#hud .trilho { width: 130px; height: 12px; background: #08112a; border: 3px solid var(--moldura); box-shadow: 0 0 0 2px #d5dbe2; }
#hud .trilho i { display: block; height: 100%; width: 80%; background: repeating-linear-gradient(90deg, #e53935 0 6px, #ff8a80 6px 8px); }
#hud .trilho.mp i { width: 65%; background: repeating-linear-gradient(90deg, #3b6fb6 0 6px, #7ee7ff 6px 8px); }
#hud .oneup {
  font-family: 'Press Start 2P', monospace; font-size: 18px; color: #f08a24;
  text-shadow: 2px 0 0 #4a2c12, -2px 0 0 #4a2c12, 0 2px 0 #4a2c12, 0 -2px 0 #4a2c12, 3px 3px 0 #ffd54f;
}

/* ---------- abas ---------- */
.tab-wrapper, .tabs { background: transparent !important; border: none !important; box-shadow: none !important; padding: 0 !important; }
button[role="tab"] {
  font-family: 'Press Start 2P', monospace !important; font-size: 11px !important; color: #a9c7e8 !important;
  background: #0f1c3d !important; border: 3px solid var(--moldura) !important; border-bottom: none !important;
  border-radius: 0 !important; margin-right: 6px; padding: 10px 14px !important; display: inline-flex; align-items: center;
}
button[role="tab"][aria-selected="true"] { color: #08112a !important; background: var(--neon-yellow) !important; box-shadow: inset 0 3px 0 #fff3b0; }

/* ---------- log do chat ---------- */
#chat-log { background: rgba(8, 17, 42, .92) !important; box-shadow: inset 0 0 0 3px var(--realce), inset 0 0 30px rgba(0, 0, 0, .6) !important; padding: 4px !important; }
#chat-log .message-row, #chat-log .message-row.panel, #chat-log .panel-wrap, #chat-log .message-wrap { background: transparent !important; }
#chat-log .message-row { padding: 4px 8px !important; }
#chat-log .message, #chat-log .message * { font-family: 'VT323', monospace !important; }
#chat-log .message, #chat-log .message p, #chat-log .message li, #chat-log .message span { font-size: 22px !important; line-height: 1.2 !important; }
/* balão do bot: painel escuro com contorno ciano */
#chat-log .bot.message {
  background: #10214a !important; color: #d8f6ff !important; border: none !important; border-radius: 0 !important;
  padding: 8px 14px !important; box-shadow: 4px 0 0 #7ee7ff, -4px 0 0 #7ee7ff, 0 4px 0 #7ee7ff, 0 -4px 0 #7ee7ff !important; margin: 4px !important;
}
/* balão do jogador: bege com contorno vermelho, como o ícone de fala */
#chat-log .user.message {
  background: #f7e0b8 !important; color: #3b2413 !important; border: none !important; border-radius: 0 !important;
  padding: 8px 14px !important; box-shadow: 4px 0 0 #b3261e, -4px 0 0 #b3261e, 0 4px 0 #b3261e, 0 -4px 0 #b3261e !important; margin: 4px !important;
}
#chat-log .user.message * { color: #3b2413 !important; }
#chat-log img.avatar-image { border: 3px solid var(--neon-cyan); border-radius: 50%; box-shadow: 0 0 10px rgba(126, 231, 255, .6); }

/* ---------- campos ---------- */
textarea, input, .wrap input {
  font-family: 'VT323', monospace !important; font-size: 22px !important; color: #d8f6ff !important;
  border: 3px solid var(--moldura) !important; border-radius: 0 !important; background: #08112a !important;
}
textarea:focus, input:focus { box-shadow: 0 0 0 3px var(--neon-cyan) !important; }
label span, .block-label, .block-info, [data-testid="block-info"] {
  font-family: 'Press Start 2P', monospace !important; font-size: 10px !important; color: var(--neon-cyan) !important;
  letter-spacing: 1px; text-transform: uppercase;
}

/* ---------- botões chunky (estilo BONUS / MENU / OK!) ---------- */
button.btn {
  font-family: 'Press Start 2P', monospace !important; font-size: 11px !important; text-transform: uppercase;
  border: none !important; border-radius: 0 !important; padding: 16px 18px !important; min-height: 56px;
  display: inline-flex; align-items: center; justify-content: center; white-space: nowrap;
  transition: transform .08s;
}
button.btn:hover { filter: brightness(1.1); transform: translateY(-1px); }
button.btn:active { transform: translateY(3px); }
button.btn-send  { background: #f4c430 !important; color: #4a2c12 !important;
  box-shadow: 4px 0 0 #4a2c12, -4px 0 0 #4a2c12, 0 4px 0 #4a2c12, 0 -4px 0 #4a2c12, inset 4px 4px 0 #fff0a0, inset -4px -4px 0 #c08a10 !important; }
button.btn-reset { background: #e8892b !important; color: #4a2c12 !important;
  box-shadow: 4px 0 0 #4a2c12, -4px 0 0 #4a2c12, 0 4px 0 #4a2c12, 0 -4px 0 #4a2c12, inset 4px 4px 0 #ffc47a, inset -4px -4px 0 #b05a10 !important; }
button.btn-ficha { background: #c8352e !important; color: #fff3e0 !important;
  box-shadow: 4px 0 0 #3a0d0a, -4px 0 0 #3a0d0a, 0 4px 0 #3a0d0a, 0 -4px 0 #3a0d0a, inset 4px 4px 0 #ff8a80, inset -4px -4px 0 #8e1b1b !important; }

/* ---------- ficha de build ---------- */
#ficha-out {
  background: rgba(8, 17, 42, .92) !important; min-height: calc(100vh - 340px); max-height: calc(100vh - 340px); overflow-y: auto; font-size: 22px;
  box-shadow: inset 0 0 0 3px #b36bff !important;
}
#ficha-out h2, #ficha-out h3 { font-family: 'Press Start 2P', monospace !important; color: var(--neon-yellow); line-height: 1.5; margin: 6px 0; }
#ficha-out h2 { font-size: 14px; } #ficha-out h3 { font-size: 11px; color: var(--neon-cyan); }
footer { display: none !important; }
"""

# ícones nas abas, rótulos e botões
CSS += "\n" + _css_icones() + "\n" + "\n".join(
    [
        _pseudo_icone('button[role="tab"]:nth-of-type(1)', "bubble", 2),
        _pseudo_icone('button[role="tab"]:nth-of-type(2)', "scroll", 2),
        _pseudo_icone("#sel-jogo [data-testid=\"block-info\"]", "shield", 2),
        _pseudo_icone("#sel-jogo-ficha [data-testid=\"block-info\"]", "shield", 2),
        _pseudo_icone("button.btn-send", "arrow", 3),
        _pseudo_icone("button.btn-reset", "potion", 2),
        _pseudo_icone("button.btn-ficha", "sword", 2),
    ]
)

CABECALHO_HTML = """
<div id="hud">
  <div class="avatar"><img src="data:image/jpeg;base64,__AVATAR_INLINE__" alt="Avatar do GuiaGamer"></div>
  <div>
    <div class="titulo"><span class="ico ico-trophy" style="--s:2"></span>GUIAGAMER</div>
    <div class="sub">CYBERNETIC ARCADE · wiki conversacional de LoL, Brawl Stars e Minecraft</div>
  </div>
  <div class="status">
    <span class="oneup">1UP!</span>
    <span class="ico ico-smile" style="--s:3"></span>
    <div class="vidas"><span class="ico ico-heart"></span><span class="ico ico-heart"></span><span class="ico ico-heart"></span></div>
    <div class="barras">
      <div class="barra">HP <span class="trilho"><i></i></span></div>
      <div class="barra">MP <span class="trilho mp"><i></i></span></div>
    </div>
  </div>
</div>
"""


# ---------------------------------------------------------------------------
# Montagem da interface Gradio
# ---------------------------------------------------------------------------
def construir_interface() -> gr.Blocks:
    avatar = _caminho_avatar()
    with gr.Blocks(title="GuiaGamer — Wiki conversacional de jogos") as demo:
        gr.HTML(CABECALHO_HTML.replace("__AVATAR_INLINE__", _AVATAR_B64))

        with gr.Tab("CHAT"):
            seletor_jogo = gr.Dropdown(
                choices=JOGOS_SUPORTADOS,
                value=JOGOS_SUPORTADOS[0],
                label="Jogo (trocar reinicia a memória)",
                elem_id="sel-jogo",
            )
            chatbot_ui = gr.Chatbot(
                value=[SAUDACAO],
                show_label=False,
                height="calc(100vh - 470px)",
                min_height=160,
                layout="panel",
                avatar_images=(None, avatar),
                elem_id="chat-log",
            )
            with gr.Row(equal_height=True):
                caixa_msg = gr.Textbox(
                    show_label=False,
                    lines=1,
                    max_lines=1,
                    scale=6,
                    elem_id="campo-msg",
                    placeholder="> Digite sua dúvida. Ex.: Sou iniciante de Ahri no mid, que itens comprar primeiro?",
                )
                botao_enviar = gr.Button("Enviar", elem_classes=["btn", "btn-send"], scale=1, min_width=200)
                botao_reiniciar = gr.Button("Nova sessão", elem_classes=["btn", "btn-reset"], scale=1, min_width=200)

            entradas = [caixa_msg, chatbot_ui, seletor_jogo]
            botao_enviar.click(responder_chat, entradas, [caixa_msg, chatbot_ui])
            caixa_msg.submit(responder_chat, entradas, [caixa_msg, chatbot_ui])
            botao_reiniciar.click(reiniciar_memoria, outputs=[chatbot_ui, caixa_msg])
            seletor_jogo.change(reiniciar_memoria, outputs=[chatbot_ui, caixa_msg])

        with gr.Tab("FICHA DE BUILD"):
            with gr.Row(equal_height=True):
                seletor_jogo_ficha = gr.Dropdown(
                    choices=JOGOS_SUPORTADOS, value=JOGOS_SUPORTADOS[0], label="Jogo",
                    scale=2, elem_id="sel-jogo-ficha",
                )
                caixa_objetivo = gr.Textbox(
                    show_label=False,
                    lines=2,
                    max_lines=2,
                    scale=6,
                    elem_id="campo-obj",
                    placeholder="> Descreva seu objetivo. Ex.: Quero uma build de Ahri para o mid, sou iniciante e prefiro dano em burst.",
                )
                botao_ficha = gr.Button("Gerar ficha", elem_classes=["btn", "btn-ficha"], scale=1, min_width=170)
            saida_ficha = gr.Markdown(elem_id="ficha-out")

            botao_ficha.click(
                gerar_ficha_ui, [seletor_jogo_ficha, caixa_objetivo], [saida_ficha]
            )

    return demo


def main() -> None:
    demo = construir_interface()
    demo.launch(server_name="localhost", server_port=7860, theme=TEMA, css=CSS)


if __name__ == "__main__":
    main()
