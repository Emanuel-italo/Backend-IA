from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class Profile(str, Enum):
    GESTANTE = "gestante"
    CADEIRANTE = "cadeirante"
    CARRINHO = "carrinho"
    IDOSO = "idoso"
    MOBILIDADE_TEMPORARIA = "mobilidade_temporaria"  # ex: perna engessada


class Leg(BaseModel):
    mode: Literal["WALK", "SUBWAY", "TRAIN", "BUS"]
    distance_m: int = Field(0, ge=0)
    duration_min: int = Field(..., ge=0)
    from_place: str | None = None
    to_place: str | None = None
    segment_id: str | None = None
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
    id: str
    place_id: str
    kind: ReportKind
    text: str = ""
    reported_at: datetime
    last_confirmed_at: datetime
    confirmations: int = Field(1, ge=1)
    ttl_hours: int = Field(72, ge=1)


class RankRequest(BaseModel):
    profile: Profile
    routes: list[Route] = Field(..., min_length=1, max_length=10)
    reports: list[Report] | None = None
    explain: bool = True


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(..., min_length=1, max_length=1000)


class ChatRequest(BaseModel):
    profile: Profile
    messages: list[ChatMessage] = Field(..., min_length=1, max_length=20)
    routes: list[Route] | None = Field(None, max_length=10)
    reports: list[Report] | None = None

    @model_validator(mode="after")
    def _ultima_e_do_usuario(self) -> "ChatRequest":
        if self.messages[-1].role != "user":
            raise ValueError("A última mensagem precisa ser do usuário (role=user).")
        return self


class ChatResponse(BaseModel):
    reply: str
    source: Literal["llm", "template", "template_fallback"]
    fallback_reason: str | None = None
    out_of_scope: bool = False
    routes_cited: list[str] = Field(default_factory=list)
    kb_refs: list[str] = Field(default_factory=list)
    notice: str = (
        "Assistente com IA: as respostas podem conter erros. Confirme a situação de elevadores e acessos "
        "nos canais oficiais. Não informe dados pessoais na conversa."
    )


class ScoreItem(BaseModel):
    code: str
    points: int
    detail: str


class Explanation(BaseModel):
    resumo: str
    pontos_de_atencao: list[str] = Field(default_factory=list)
    dica: str | None = None
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
