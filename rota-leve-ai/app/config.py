from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Settings:
    # chave e modelo da groq, sem eles usa o texto pronto
    llm_api_key: str | None = os.getenv("LLM_API_KEY") or None
    llm_model: str = os.getenv("LLM_MODEL", "").strip()
    llm_base_url: str = os.getenv("LLM_BASE_URL", "https://api.groq.com/openai/v1")
    llm_timeout_s: float = float(os.getenv("LLM_TIMEOUT_S", "10"))

    # chave que o front manda no header X-API-Key
    service_api_key: str | None = os.getenv("SERVICE_API_KEY") or None

    data_dir: Path = Path(os.getenv("DATA_DIR", str(BASE_DIR / "data")))

    rag_top_k: int = int(os.getenv("RAG_TOP_K", "2"))
    rag_min_score: float = float(os.getenv("RAG_MIN_SCORE", "0.15"))


def get_settings() -> Settings:
    return Settings()
