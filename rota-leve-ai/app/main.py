from __future__ import annotations

import hmac
import json
import logging
from functools import lru_cache

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import RedirectResponse

from .catalog import Catalog
from .chat import ChatAssistant
from .config import Settings, get_settings
from .explain import Explainer
from .llm import build_llm
from .models import ChatRequest, ChatResponse, RankRequest, RankResponse, Route
from .rag import Retriever
from .reports import ReportStore
from .service import RouteRanker

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

app = FastAPI(
    title="Rota Leve — Serviço de IA",
    version="1.0.0",
    description="Avalia e reordena rotas de transporte público por perfil de mobilidade e explica em linguagem natural.",
)


@lru_cache
def get_ranker() -> RouteRanker:
    s: Settings = get_settings()
    catalog = Catalog.from_file(s.data_dir / "pontos.json")
    store = ReportStore.from_seed(s.data_dir / "relatos.json")
    retriever = Retriever.from_file(s.data_dir / "base_conhecimento.json", min_score=s.rag_min_score)
    return RouteRanker(catalog, store, Explainer(retriever, build_llm(s), s.rag_top_k))


def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    expected = get_settings().service_api_key
    if expected and not (x_api_key and hmac.compare_digest(x_api_key, expected)):
        raise HTTPException(status_code=401, detail="API key inválida ou ausente")


@app.get("/", include_in_schema=False)
def root() -> RedirectResponse:
    return RedirectResponse(url="/docs")


@app.get("/health")
def health() -> dict:
    ranker = get_ranker()
    return {
        "status": "ok",
        "ia_generativa": ranker.explainer.llm.name if ranker.explainer.llm else "desativada (modo template)",
        "trechos_na_base": len(ranker.explainer.retriever.chunks),
    }


@app.get("/v1/demo/routes", response_model=list[Route])
def demo_routes() -> list[Route]:
    raw = json.loads((get_settings().data_dir / "rotas_demo.json").read_text(encoding="utf-8"))
    return [Route(**r) for r in raw["rotas"]]


@app.post("/v1/routes/rank", response_model=RankResponse, dependencies=[Depends(require_api_key)])
def rank_routes(req: RankRequest) -> RankResponse:
    return get_ranker().rank(req.profile, req.routes, reports=req.reports, explain=req.explain)


@app.post("/v1/chat", response_model=ChatResponse, dependencies=[Depends(require_api_key)])
def chat(req: ChatRequest) -> ChatResponse:
    ranker = get_ranker()
    facts = ranker.route_facts(req.profile, req.routes, reports=req.reports) if req.routes else []
    assistant = ChatAssistant(ranker.explainer.retriever, ranker.explainer.llm)
    return assistant.reply(req.profile, req.messages, facts)
