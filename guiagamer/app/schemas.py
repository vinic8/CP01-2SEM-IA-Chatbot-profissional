"""
schemas.py — Schemas Pydantic v2 usados para validar a saída estruturada
do GuiaGamer.

O schema principal, FichaEstrategia, é preenchido pelo pipeline LCEL
(chain.py) via PydanticOutputParser, garantindo que a resposta do modelo
venha em formato previsível e tipado — diferente de um JsonOutputParser, que
retornaria apenas um dict sem validação de tipos nem de regras (ex.: nota
fora do intervalo 0-10).
"""

from __future__ import annotations

from enum import Enum
from typing import List

from pydantic import BaseModel, Field, field_validator


class JogoSuportado(str, Enum):
    """Jogos cobertos pelo GuiaGamer."""

    LOL = "League of Legends"
    BRAWL_STARS = "Brawl Stars"
    MINECRAFT = "Minecraft"


class NivelDificuldade(str, Enum):
    """Nível de dificuldade de execução da build/estratégia."""

    INICIANTE = "iniciante"
    INTERMEDIARIO = "intermediario"
    AVANCADO = "avancado"


class FichaEstrategia(BaseModel):
    """
    Ficha estruturada de build/estratégia gerada pelo GuiaGamer.

    Possui 8 campos tipados (acima do mínimo de 4 exigido), incluindo Enums,
    listas e um campo numérico com validação de intervalo.
    """

    jogo: JogoSuportado = Field(..., description="Jogo ao qual a ficha se refere.")
    titulo_build: str = Field(
        ..., description="Nome curto da build/estratégia (ex.: 'Ahri burst mid')."
    )
    objetivo: str = Field(
        ..., description="O que o jogador quer alcançar com esta build/estratégia."
    )
    dificuldade: NivelDificuldade = Field(
        ..., description="Dificuldade de execução: iniciante, intermediario ou avancado."
    )
    componentes: List[str] = Field(
        ...,
        min_length=1,
        description="Itens, personagens, recursos ou habilidades centrais da build.",
    )
    passo_a_passo: List[str] = Field(
        ...,
        min_length=1,
        description="Passos ordenados e acionáveis para executar a estratégia.",
    )
    erros_comuns: List[str] = Field(
        ...,
        min_length=1,
        description="Erros frequentes e pontos fracos da estratégia.",
    )
    nota_eficacia: int = Field(
        ...,
        ge=0,
        le=10,
        description="Nota de eficácia geral, de 0 (fraca) a 10 (excelente).",
    )

    @field_validator("componentes", "passo_a_passo", "erros_comuns")
    @classmethod
    def _sem_itens_vazios(cls, valor: List[str]) -> List[str]:
        """Garante que nenhum item da lista seja string vazia ou só espaços."""
        limpos = [item.strip() for item in valor if item and item.strip()]
        if not limpos:
            raise ValueError("A lista não pode ficar vazia após a limpeza.")
        return limpos

    @field_validator("titulo_build", "objetivo")
    @classmethod
    def _sem_texto_vazio(cls, valor: str) -> str:
        """Garante que campos de texto livre não venham vazios do modelo."""
        if not valor or not valor.strip():
            raise ValueError("Campo de texto não pode ser vazio.")
        return valor.strip()


class RelatorioSessao(BaseModel):
    """Schema auxiliar: resume uma sessão de chat (logging/telemetria)."""

    total_turnos: int = Field(..., ge=0, description="Número de trocas usuário/IA na sessão.")
    jogo: JogoSuportado = Field(..., description="Jogo discutido na sessão.")
    topico_principal: str = Field(..., description="Tópico central discutido na sessão.")
    estrategia_memoria: str = Field(
        ..., description="Estratégia de memória usada (buffer/summary/token_buffer)."
    )
    tokens_estimados: int = Field(
        ..., ge=0, description="Estimativa de tokens consumidos na sessão (via tiktoken)."
    )
