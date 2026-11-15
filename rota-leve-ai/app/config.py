"""Configuração via variáveis de ambiente (12-factor). Nenhuma credencial fica no código."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Settings:
    # LLM. Sem chave ou sem modelo => modo "template" (sem IA generativa externa).
    # LLM_PROVIDER: "groq" (padrão, API compatível com OpenAI) ou "gemini".
    llm_provider: str = os.getenv("LLM_PROVIDER", "groq").strip().lower()
    llm_api_key: str | None = os.getenv("LLM_API_KEY") or None
    # Sem padrão de propósito: o ID do modelo muda com frequência; confira no console do provedor.
    llm_model: str = os.getenv("LLM_MODEL", "").strip()
    llm_base_url: str = os.getenv("LLM_BASE_URL", "https://api.groq.com/openai/v1")
    llm_timeout_s: float = float(os.getenv("LLM_TIMEOUT_S", "10"))
    llm_max_retries: int = int(os.getenv("LLM_MAX_RETRIES", "1"))

    # Segurança service-to-service (a API .NET/Java envia este header). Vazio => sem auth (só dev).
    service_api_key: str | None = os.getenv("SERVICE_API_KEY") or None
    # "production" no Render (definido no render.yaml); "local" no computador do desenvolvedor.
    # Fallback: o Render define RENDER=true em todos os serviços.
    deploy_env: str = os.getenv("APP_ENV") or ("production" if os.getenv("RENDER") else "local")

    # Dados
    data_dir: Path = Path(os.getenv("DATA_DIR", str(BASE_DIR / "data")))

    # RAG
    rag_top_k: int = int(os.getenv("RAG_TOP_K", "2"))
    rag_min_score: float = float(os.getenv("RAG_MIN_SCORE", "0.15"))

    # Cache de explicações (em produção: trocar por Redis)
    cache_size: int = int(os.getenv("EXPLANATION_CACHE_SIZE", "256"))


def get_settings() -> Settings:
    return Settings()
