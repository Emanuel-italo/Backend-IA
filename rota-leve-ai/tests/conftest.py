import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.catalog import Catalog
from app.explain import Explainer
from app.models import Route
from app.rag import Retriever
from app.reports import ReportStore
from app.service import RouteRanker

DATA = Path(__file__).resolve().parent.parent / "data"
NOW = datetime(2026, 11, 14, 12, 0, tzinfo=timezone.utc)


@pytest.fixture(scope="session")
def catalog():
    return Catalog.from_file(DATA / "pontos.json")


@pytest.fixture(scope="session")
def retriever():
    return Retriever.from_file(DATA / "base_conhecimento.json")


@pytest.fixture()
def store():
    return ReportStore.from_seed(DATA / "relatos.json", now=NOW)


@pytest.fixture(scope="session")
def routes():
    raw = json.loads((DATA / "rotas_demo.json").read_text(encoding="utf-8"))
    return [Route(**r) for r in raw["rotas"]]


@pytest.fixture()
def ranker(catalog, store, retriever):
    return RouteRanker(catalog, store, Explainer(retriever, llm=None))


class FakeLLM:
    """LLM falso para testes: devolve uma resposta fixa ou lança erro."""

    name = "fake"

    def __init__(self, response=None, error=None):
        self.response, self.error, self.calls, self.last_user = response, error, 0, ""

    def generate_json(self, system, user):
        self.calls += 1
        self.last_user = user
        if self.error:
            raise self.error
        return self.response
