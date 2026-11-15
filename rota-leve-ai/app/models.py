"""Contratos de dados (Pydantic). São também o contrato OpenAPI do serviço de IA."""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class Profile(str, Enum):
    GESTANTE = "gestante"
    CADEIRANTE = "cadeirante"
    CARRINHO = "carrinho"
    IDOSO = "idoso"
    MOBILIDADE_TEMPORARIA = "mobilidade_temporaria"  # perna engessada, pós-cirurgia


class Leg(BaseModel):
    mode: Literal["WALK", "SUBWAY", "TRAIN", "BUS"]
    distance_m: int = Field(0, ge=0)
    duration_min: int = Field(..., ge=0)
    from_place: str | None = None  # id no catálogo (estação/ponto) — None = sem dados
    to_place: str | None = None
    segment_id: str | None = None  # trecho de calçada (para relatos "calçada ruim")
    slope: Literal["plana", "leve", "ingreme"] = "plana"
    line: str | None = None
    num_stops: int | None = None


class Route(BaseModel):
    id: str
    summary: str
    duration_min: int = Field(..., ge=0)
    legs: list[Leg] = Field(..., min_length=1)


class ReportKind(str, Enum):
    ELEVADOR_FORA = "elevador_fora"
    ESCADA_ROLANTE_FORA = "escada_rolante_fora"
    CALCADA_RUIM = "calcada_ruim"
    SEM_COBERTURA = "sem_cobertura"


class Report(BaseModel):
    """Relato colaborativo. Expira se ninguém confirmar dentro do TTL."""

    id: str
    place_id: str  # estação/ponto ou segmento de calçada
    kind: ReportKind
    text: str = ""
    reported_at: datetime
    last_confirmed_at: datetime
    confirmations: int = Field(1, ge=1)
    ttl_hours: int = Field(72, ge=1)


class RankRequest(BaseModel):
    profile: Profile
    routes: list[Route] | None = None
    # Resposta crua da Google Directions API (mode=transit, alternatives=true). Alternativa a `routes`.
    directions: dict | None = None
    # Relatos opcionais; se ausente, o serviço usa a base local de relatos.
    reports: list[Report] | None = None
    explain: bool = True


class ScoreItem(BaseModel):
    code: str
    points: int  # negativo = penalidade
    detail: str


class Explanation(BaseModel):
    resumo: str
    pontos_de_atencao: list[str] = Field(default_factory=list)
    dica: str | None = None
    # llm = gerada pelo modelo e validada | template = sem LLM configurado | template_fallback = LLM falhou/reprovou
    source: Literal["llm", "template", "template_fallback"] = "template"
    fallback_reason: str | None = None
    kb_refs: list[str] = Field(default_factory=list)


class RankedRoute(BaseModel):
    route_id: str
    summary: str
    score: int
    label: Literal["recomendada", "com_ressalvas", "nao_recomendada"]
    blocking: bool
    duration_min: int
    walk_m: int
    breakdown: list[ScoreItem]
    explanation: Explanation | None = None


class RankResponse(BaseModel):
    profile: Profile
    routes: list[RankedRoute]
    generated_at: datetime
    notice: str = (
        "Pontuação de apoio à decisão baseada em dados colaborativos que podem estar desatualizados. "
        "Confirme a situação de elevadores e acessos nos canais oficiais."
    )
