"""
chain.py — Pipeline LCEL estruturado do GuiaGamer.

Implementa a segunda das 2 chains da arquitetura da Aula 03: um pipeline
LCEL puro (ChatPromptTemplate | ChatOllama | PydanticOutputParser) que
recebe o objetivo de um jogador em um jogo e devolve uma FichaEstrategia
validada.

Usamos PydanticOutputParser (não JsonOutputParser) porque o requisito do
CKP01 exige validação de tipos e regras de negócio (ex.: nota_eficacia
entre 0 e 10, listas não vazias) — um JsonOutputParser apenas desserializa
para dict, sem checar nada disso.
"""

from __future__ import annotations

import os
from typing import List

import tiktoken
from dotenv import load_dotenv
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable
from langchain_ollama import ChatOllama

from app.prompts import SYSTEM_PROMPT_FICHA
from app.schemas import FichaEstrategia

load_dotenv()

MODELO_OLLAMA = "gemma4:cloud"  # modelo exclusivo exigido pelo CKP01


class ChatOllamaTiktoken(ChatOllama):
    """
    ChatOllama que conta tokens com tiktoken (cl100k_base).

    A ConversationTokenBufferMemory chama llm.get_num_tokens_from_messages()
    para decidir quando descartar mensagens antigas. Sem este método o
    LangChain tenta baixar um tokenizador da HuggingFace (transformers);
    com ele, a contagem é local, rápida e consistente com o context_rot.py.
    """

    def get_token_ids(self, text: str) -> List[int]:
        return tiktoken.get_encoding("cl100k_base").encode(text)


def criar_llm(temperature: float = 0.4, formato_json: bool = False) -> ChatOllama:
    """
    Cria a instância do ChatOllama apontando para o Ollama Cloud.

    A OLLAMA_API_KEY é lida do ambiente (.env, via python-dotenv) — nunca
    hardcoded no código, e o .env nunca é enviado no .zip de entrega
    (apenas o .env.example).

    formato_json=True ativa o format="json" nativo do Ollama (Aula 03), que
    garante JSON válido na saída — usado na chain estruturada junto com o
    PydanticOutputParser.
    """
    api_key = os.getenv("OLLAMA_API_KEY")
    if not api_key:
        raise RuntimeError(
            "OLLAMA_API_KEY não encontrada. Copie .env.example para .env "
            "e preencha sua chave do Ollama Cloud antes de rodar o app."
        )
    return ChatOllamaTiktoken(
        model=MODELO_OLLAMA,
        temperature=temperature,
        base_url="https://ollama.com",
        format="json" if formato_json else None,
        client_kwargs={"headers": {"Authorization": f"Bearer {api_key}"}},
    )


def criar_pipeline_ficha(llm: ChatOllama | None = None) -> Runnable:
    """
    Monta o pipeline LCEL: prompt | llm | parser.

    Chain estruturada exigida pelo CKP01, construída com o operador `|` e
    usando ChatPromptTemplate (não f-strings manuais) com system message e
    human message separados. Variáveis do template: {jogo}, {objetivo}
    (entradas) e {format_instructions} (preenchida via partial).
    """
    # format="json" + PydanticOutputParser: combinação recomendada na Aula 03
    modelo = llm or criar_llm(formato_json=True)
    parser = PydanticOutputParser(pydantic_object=FichaEstrategia)

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", SYSTEM_PROMPT_FICHA),
            (
                "human",
                "Monte a ficha de build/estratégia para este objetivo:\n\n"
                "{objetivo}",
            ),
        ]
    ).partial(format_instructions=parser.get_format_instructions())

    # A arquitetura LCEL: cada componente é encadeado com o operador pipe.
    pipeline: Runnable = prompt | modelo | parser
    return pipeline


def gerar_ficha(jogo: str, objetivo: str, llm: ChatOllama | None = None) -> FichaEstrategia:
    """Função de conveniência: roda o pipeline completo para um jogo e objetivo."""
    pipeline = criar_pipeline_ficha(llm)
    resultado: FichaEstrategia = pipeline.invoke({"jogo": jogo, "objetivo": objetivo})
    return resultado
