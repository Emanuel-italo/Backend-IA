import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import main
from app.config import Settings

DATA = Path(__file__).resolve().parent.parent / "data"
ROUTES = json.loads((DATA / "rotas_demo.json").read_text(encoding="utf-8"))["rotas"]
DIRECTIONS = json.loads((Path(__file__).parent / "fixtures" / "directions_sample.json").read_text(encoding="utf-8"))


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setattr(main, "get_settings", lambda: Settings(gemini_api_key=None, service_api_key=None))
    main.get_ranker.cache_clear()
    yield TestClient(main.app)
    main.get_ranker.cache_clear()


def test_health(client):
    body = client.get("/health").json()
    assert body["status"] == "ok" and body["trechos_na_base"] > 0


def test_rank_devolve_rotas_ordenadas_com_explicacao(client):
    r = client.post("/v1/routes/rank", json={"profile": "gestante", "routes": ROUTES})
    assert r.status_code == 200
    body = r.json()
    assert body["routes"][0]["route_id"] == "r2-onibus-direto"
    assert body["routes"][0]["explanation"]["resumo"]
    assert body["notice"]


def test_rank_aceita_resposta_da_directions_api(client):
    r = client.post("/v1/routes/rank", json={"profile": "cadeirante", "directions": DIRECTIONS})
    assert r.status_code == 200 and len(r.json()["routes"]) == 2


@pytest.mark.parametrize("payload", [
    {"profile": "gestante"},                                  # sem rotas
    {"profile": "gestante", "routes": []},                    # lista vazia
    {"profile": "", "routes": ROUTES},                        # perfil vazio
    {"profile": "astronauta", "routes": ROUTES},              # perfil inexistente
    {"routes": ROUTES},                                       # sem perfil
    {"profile": "gestante", "directions": {"status": "ZERO_RESULTS", "routes": []}},
    {"profile": "gestante", "routes": [{"id": "x", "summary": "s", "duration_min": -1, "legs": []}]},
])
def test_entradas_invalidas_retornam_422(client, payload):
    assert client.post("/v1/routes/rank", json=payload).status_code == 422


def test_api_key_obrigatoria_quando_configurada(monkeypatch):
    monkeypatch.setattr(main, "get_settings", lambda: Settings(gemini_api_key=None, service_api_key="segredo"))
    main.get_ranker.cache_clear()
    c = TestClient(main.app)
    body = {"profile": "idoso", "routes": ROUTES}
    assert c.post("/v1/routes/rank", json=body).status_code == 401
    assert c.post("/v1/routes/rank", json=body, headers={"X-API-Key": "errado"}).status_code == 401
    assert c.post("/v1/routes/rank", json=body, headers={"X-API-Key": "segredo"}).status_code == 200
    main.get_ranker.cache_clear()
