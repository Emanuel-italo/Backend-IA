"""Configuração via variáveis de ambiente (12-factor). Nenhuma credencial fica no código."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Settings:
    # LLM (Gemini via REST). Sem chave => modo "template" (sem IA generativa externa).
    gemini_api_key: str | None = os.getenv("GEMINI_API_KEY") or None
    llm_model: str = os.getenv("LLM_MODEL", "gemini-3.6-flash")
    llm_timeout_s: float = float(os.getenv("LLM_TIMEOUT_S", "10"))
    llm_max_retries: int = int(os.getenv("LLM_MAX_RETRIES", "1"))

    # Segurança service-to-service (a API .NET envia este header). Vazio => sem auth (só dev).
    service_api_key: str | None = os.getenv("SERVICE_API_KEY") or None

    # Dados
    data_dir: Path = Path(os.getenv("DATA_DIR", str(BASE_DIR / "data")))

    # RAG
    rag_top_k: int = int(os.getenv("RAG_TOP_K", "2"))
    rag_min_score: float = float(os.getenv("RAG_MIN_SCORE", "0.15"))

    # Cache de explicações (em produção: trocar por Redis)
    cache_size: int = int(os.getenv("EXPLANATION_CACHE_SIZE", "256"))


def get_settings() -> Settings:
    return Settings()
