# CKP01 — Chatbot Profissional · Assistente de Jogos (GuiaGamer)

**Prompt Engineering & AI · FIAP · 2º Semestre 2026**

**Integrantes:**
- Vinicius Molena (RM571270)
- Matheus Caviglia Ferreira (RM569638)
- Gabriel Vilas Boas da Silva Viana (RM571603)
- Nathan Guilherme Werner (RM572925)
- Gustavo Henrique Pereira Correia (RM569921)
- Ricardo Algazi dos Santos (RM569600)

---

## Domínio

**GuiaGamer** é um **assistente de dúvidas e guia de jogos** — um "wiki
conversacional" que responde perguntas sobre mecânicas, builds e
estratégias de **League of Legends**, **Brawl Stars** e **Minecraft**. O
usuário escolhe o jogo na interface e conversa em linguagem natural, em vez
de procurar em wikis, vídeos e fóruns dispersos.

**Por que esse domínio foi escolhido:**
- É um problema real: jogadores têm dúvidas constantes durante e entre
  partidas (o que comprar, qual personagem usar, como avançar) e as
  respostas estão espalhadas e desatualizadas.
- O conhecimento é bem estruturado e amplo, o que sustenta os 3
  checkpoints: o chatbot (CKP01) vira a base de um RAG sobre wikis e notas de
  patch (CKP02), que por sua vez vira uma ferramenta de um agente de apoio
  ao jogador (CKP03).
- O grupo conhece os jogos, o que ajuda a escrever prompts e casos de teste
  realistas.

**Usuários-alvo:** jogadores casuais e competitivos, principalmente
iniciantes e intermediários, que querem tirar dúvidas rápidas e receber
builds e estratégias explicadas com o "porquê".

---

## Arquitetura (2 chains — Aula 03)

1. **Chat com memória** (`memory_manager.py`) — uma `ConversationChain` com
   `ConversationTokenBufferMemory`, usada na aba de chat. O jogo escolhido
   entra no system prompt como variável `{jogo}`; trocar de jogo reinicia a
   memória.
2. **Pipeline estruturado** (`chain.py`) — uma chain LCEL pura
   (`ChatPromptTemplate | ChatOllama(format="json") | PydanticOutputParser`),
   usada na aba "Ficha de build". Recebe jogo e objetivo e devolve uma
   `FichaEstrategia` validada (ver `schemas.py`), sem depender do histórico.

As duas chains usam o `gemma4:cloud` via Ollama Cloud, com ciclos de vida
independentes.

---

## Requisitos atendidos

| Requisito | Status | Implementação |
|---|---|---|
| Pipeline LCEL | ✅ | `chain.py` — `prompt \| llm \| PydanticOutputParser` |
| ChatOllama | ✅ | `gemma4:cloud` via Ollama Cloud (`OLLAMA_API_KEY` em `.env`) |
| ChatPromptTemplate | ✅ | `chain.py` e `memory_manager.py` — system/human separados, variáveis `{jogo}`, `{objetivo}`, `{input}` |
| Memória gerenciada (2 chains, Aula 03) | ✅ | `ConversationChain` + `ConversationTokenBufferMemory` (1500 tokens), justificada em `memory_manager.py`; o módulo oferece as 3 estratégias (buffer, summary, token_buffer) |
| Pydantic v2 (≥4 campos) | ✅ | `FichaEstrategia` com 8 campos tipados e validadores em `schemas.py` |
| Context rot | ✅ | `context_rot.py` — experimentos A, B e C (contexto crescente, janela limitada, A/B de prompt) |
| System prompt com persona (XML tagging) | ✅ | `prompts.py` — `<instrucao_critica>`, `<persona>`, `<diretrizes>`, `<restricoes>` |
| Domínio documentado | ✅ | Este README + `prompts.py` |
| Projeto local estruturado (sem Colab) | ✅ | Pacote `app/` + `.env.example` + `requirements.txt` |
| **Diferencial** — métricas (tiktoken + gráfico) | ✅ | `context_rot.py` — tabelas com tokens por janela e `gerar_grafico_context_rot()` (gera PNG ao rodar) |
| **Diferencial** — meta prompting | ✅ | `context_rot.py` (experimento D) + `prompts.py` — antes/depois documentado abaixo |

---

## Justificativa da memória

**Estratégia escolhida: `ConversationTokenBufferMemory`, com teto de 1500
tokens.**

Um assistente de dúvidas depende de detalhes precisos que o jogador cita ao
longo da conversa: campeão e rota, elo, modo de jogo, itens que já possui.
Comparamos as 3 opções:

- **`ConversationBufferMemory`** (histórico completo): preserva tudo, mas
  cresce sem limite. O custo por chamada sobe a cada turno (no experimento A
  abaixo, o prompt vai de 468 para 29.336 tokens) sem ganho de qualidade
  para dúvidas antigas já resolvidas.
- **`ConversationSummaryMemory`** (resumo via LLM): custo baixo, mas o
  resumo tende a perder detalhes específicos (ex.: "Ahri no mid, elo Prata,
  primeiro item Rabadon") que mudam completamente a resposta correta, e
  exige uma chamada extra ao modelo a cada turno.
- **`ConversationTokenBufferMemory`** (escolhida): mantém o histórico
  literal até um teto de tokens e descarta as trocas mais antigas.
  Equilibra fidelidade ao contexto recente com custo de tokens previsível e
  sem chamadas extras.

**Efeito no custo de tokens:** o histórico enviado a cada turno nunca passa
de 1500 tokens (mais o system prompt, ~330), em vez de crescer sem limite.

**Por que 1500:** é o teto da faixa exigida (800–1500). Nos testes com 1000
tokens o buffer descartou os primeiros turnos (as respostas do modelo eram
longas) e o chatbot esqueceu o campeão, a rota e o elo. Por isso o system
prompt limita as respostas a ~100 palavras e o teto foi elevado a 1500.

**Trade-off assumido:** em conversas muito longas o início é descartado
(ver experimento B do context rot). Para dúvidas de jogo isso é aceitável;
o jogador pode reiterar o contexto ou iniciar uma nova sessão.

**Contagem de tokens:** `ChatOllamaTiktoken` (em `chain.py`) faz o
`ChatOllama` contar tokens com `tiktoken`, evitando o download de um
tokenizador da HuggingFace que a memória exigiria por padrão.

### Demonstração de memória em 6 turnos (executada)

Executado com o jogo **League of Legends** e `gemma4:cloud`:

| Turno | Usuário | Resposta do GuiaGamer (resumo) |
|---|---|---|
| 1 | "Eu jogo de Ahri no mid e estou no elo Prata." | Dicas de farm, combo e objetivos para Ahri no Prata |
| 2 | "Morro muito para assassinos na fase de rotas." | Explica o problema e sugere guardar o Charm (E) |
| 3 | "Uso Flash e Ignite como feitiços." | Avalia o Ignite contra assassinos e sugere alternativas |
| 4 | "Meu primeiro item completo costuma ser o Cetro do Rabadon." | Alerta que Rabadon é caro demais como primeiro item |
| 5 | "Jogo só solo queue, umas 3 partidas por dia." | Dicas de consistência para solo queue |
| 6 | "Qual campeã eu jogo, em qual rota e em qual elo estou?" | **"Você joga de Ahri, na rota do Mid e está no elo Prata."** ✅ (e resume feitiços e problemas) |

---

## Context rot

`context_rot.py` mede o efeito do contexto sobre a qualidade com a **mesma
pergunta final** em janelas de tamanhos diferentes. Os turnos iniciais
informam 4 detalhes do jogador (campeã **Ahri**, rota **mid**, elo
**Prata**, primeiro item **Rabadon**); em seguida entram turnos de recheio
com **distratores** (um amigo com outro campeão, rota, elo e item). A
pergunta final exige lembrar os 4 detalhes **do jogador**. Métrica: quantos
dos 4 aparecem na resposta, com tokens contados por **tiktoken**
(`cl100k_base`, `temperature=0`).

```bash
python -m app.context_rot   # roda os experimentos A–D, imprime as tabelas e salva os gráficos (PNG)
```

### Experimento A — contexto crescente (sem truncar)

| Turnos de recheio | Tokens no prompt | Detalhes lembrados |
|---|---|---|
| 0 | 468 | 4/4 |
| 5 | 975 | 4/4 |
| 10 | 1334 | 4/4 |
| 20 | 2052 | 4/4 |
| 40 | 3488 | 4/4 |
| 80 | 6360 | 4/4 |
| 200 | 14976 | 4/4 |
| 400 | 29336 | 4/4 |

**Leitura:** o `gemma4:cloud` **não degradou** até ~29 mil tokens: lembrou
os 4 detalhes mesmo com distratores. O que cresce é o **custo**: ~63× mais
tokens (468 → 29.336) para o mesmo resultado, o que justifica limitar o
histórico com `TokenBuffer`.

### Experimento B — janela de tokens limitada (degradação real)

Mesma conversa de 80 turnos (6360 tokens) e mesma pergunta, mas cortada para
manter só as mensagens mais recentes que cabem em W tokens — exatamente o
que a `ConversationTokenBufferMemory` faz.

| Limite de tokens do histórico | Tokens no prompt | Detalhes lembrados |
|---|---|---|
| 200 | 516 | 0/4 |
| 500 | 800 | 0/4 |
| 1000 | 1304 | 0/4 |
| 1500 | 1810 | 0/4 |
| 3000 | 3313 | 0/4 |
| 8000 (conversa inteira) | 6360 | 4/4 |

**Leitura:** quando a janela é menor que a conversa, as âncoras são
descartadas e o modelo responde "você ainda não me informou…" (0/4). É a
degradação de qualidade causada por janela insuficiente e o trade-off
central da memória `TokenBuffer`: **custo baixo e previsível** em troca de
**esquecer o início** de conversas longas. Em uso normal (5–8 turnos com
respostas de ~100 palavras) o buffer de 1500 tokens comporta a conversa
inteira, como mostra a demonstração de 6 turnos.

### Experimento C — A/B: parágrafo único × XML tagging

Mesmo contexto crescente, pergunta **fora do domínio** (receita de bolo de
cenoura) e só o system prompt muda (parágrafo único × prompt com XML
tagging, Aula 04). Métrica: a resposta traz ingredientes da receita?

| Turnos | Tokens | Parágrafo: saiu do domínio? | Palavras | XML: saiu do domínio? | Palavras |
|---|---|---|---|---|---|
| 0 | 468 | Não | 55 | Não | 65 |
| 20 | 2052 | Não | 31 | Não | 31 |
| 80 | 6360 | Não | 31 | Não | 33 |
| 200 | 14976 | Não | 31 | Não | 36 |
| 400 | 29336 | Não | 37 | Não | 45 |

**Leitura:** com este modelo, **os dois formatos** mantiveram a aderência ao
domínio em todas as janelas — não houve vazamento nem diferença mensurável.
Portanto o ganho do XML tagging aqui não aparece em aderência, e sim em
manutenção e organização do prompt (seções separadas), além do ganho de
tokens do meta prompting (próxima seção).

---

## Meta prompting (diferencial)

O experimento D de `context_rot.py` usa o próprio `gemma4:cloud` para
melhorar o system prompt do chat, com uma chain LCEL
(`ChatPromptTemplate.from_template | ChatOllama | StrOutputParser`) e um
meta-prompt em XML (`PROMPT_OTIMIZADOR` em `prompts.py`, com `<tarefa>`,
`<prompt_original>` e `<formato_saida>`). O
otimizador é instruído a preservar o nome, o idioma, o limite de 100
palavras, as restrições de domínio e a variável `{jogo}`; o código valida
que a variável sobreviveu.

```bash
python -m app.context_rot   # o experimento D otimiza, mede tokens e roda o teste A/B
```

- **Antes (`SYSTEM_PROMPT_CHAT_V1`, escrito à mão):** 6 seções XML
  (`<critico>`, `<persona>`, `<tom>`, `<regras>`, `<restricoes>`,
  `<lembrete_final>`), textos longos e regras repetidas — **631 tokens**.
- **Depois (`SYSTEM_PROMPT_CHAT`, otimizado pelo modelo):** seções
  `<instrucao_critica>` (no início e no fim), `<persona>`, `<diretrizes>` e
  `<restricoes>`, com regras fundidas — **329 tokens (−48%)**. É a versão
  usada pelo chat (ver `prompts.py`).
- **Mudanças apontadas pelo modelo:** (1) XML tagging para segmentar
  persona, diretrizes e restrições; (2) instruções críticas no início e no
  fim para reforçar domínio e limite de palavras; (3) fusão de regras
  redundantes e linguagem mais direta.

**Teste A/B (mesmas perguntas, temperature 0, League of Legends):**

| Caso | Antes (palavras) | Depois (palavras) | Resultado |
|---|---|---|---|
| Fora do domínio (receita) | 60 | 67 | Ambos recusam e redirecionam |
| Duas perguntas (uma fora) | 99 | 88 | Ambos explicam o último hit |
| Dúvida do jogo (Ahri/itens) | 97 | 86 | Ambos recomendam itens iniciais coerentes |
| Pedido de trapaça (script) | 90 | 83 | Ambos recusam e citam risco de banimento |

**Validação:** depois de adotar a versão otimizada, repetimos a
demonstração de memória de 6 turnos (turno 6 correto: Ahri, mid, Prata) e os
experimentos de context rot acima (todos gerados com o prompt otimizado).

---

## Como executar 

```bash
cp .env.example .env     # edite com sua OLLAMA_API_KEY — este arquivo NÃO vai no .zip
pip install -r requirements.txt
python -m app.main       # Gradio: http://localhost:7860
```

No Windows (PowerShell): `Copy-Item .env.example .env`.

Script opcional (context rot e meta prompting): `python -m app.context_rot`.

---

## Estrutura do projeto

```
guiagamer/
├── app/
│   ├── __init__.py
│   ├── main.py             # Interface Gradio + entry point
│   ├── chain.py            # Pipeline LCEL estruturado (chain nº 2, Aula 03)
│   ├── memory_manager.py   # ConversationChain + 3 estratégias de memória (chain nº 1, Aula 03)
│   ├── schemas.py          # Pydantic v2 (FichaEstrategia, RelatorioSessao)
│   ├── context_rot.py      # Demonstração de context rot + métricas + meta prompting
│   └── prompts.py          # System prompts (XML tagging)
├── .env.example
├── requirements.txt
└── README.md
```

---

## Observações

- Projeto novo, construído do zero para este domínio.
- Modelo usado: exclusivamente `gemma4:cloud` via Ollama Cloud.
- O `.env` real (com a chave) nunca vai no `.zip` — apenas o `.env.example`.
- Base do CKP02 (RAG) e CKP03 (Agente): módulos propositalmente modulares.
- `ConversationChain` e as memórias vêm de `langchain-classic`, como nos
  notebooks das aulas (classes marcadas como deprecated, mas exigidas pelo
  enunciado).

---

Disciplina: Prompt Engineering and Artificial Intelligence · FIAP · CC 2026
Prof. Jorge Luiz Gomes · profjorge.gomes@fiap.com.br
