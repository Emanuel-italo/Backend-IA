import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import main
from app.config import Settings

DATA = Path(__file__).resolve().parent.parent / "data"
ROTAS = json.loads((DATA / "rotas_demo.json").read_text(encoding="utf-8"))["rotas"]
CHAVE = {"X-API-Key": "segredo"}


@pytest.fixture()
def api(monkeypatch):
    monkeypatch.setattr(main, "get_settings", lambda: Settings(llm_api_key=None, service_api_key="segredo"))
    main.get_ranker.cache_clear()
    yield TestClient(main.app)
    main.get_ranker.cache_clear()


def test_health_responde(api):
    assert api.get("/health").json()["status"] == "ok"


def test_rank_devolve_rotas_ordenadas_com_explicacao(api):
    r = api.post("/v1/routes/rank", json={"profile": "gestante", "routes": ROTAS}, headers=CHAVE)
    assert r.status_code == 200
    assert r.json()["routes"][0]["route_id"] == "r2-onibus-direto"
    assert r.json()["routes"][0]["explanation"]["resumo"]


def test_sem_chave_ou_com_chave_errada_responde_401(api):
    corpo = {"profile": "idoso", "routes": ROTAS}
    assert api.post("/v1/routes/rank", json=corpo).status_code == 401
    assert api.post("/v1/routes/rank", json=corpo, headers={"X-API-Key": "errada"}).status_code == 401


@pytest.mark.parametrize("corpo", [
    {"profile": "astronauta", "routes": ROTAS},  # perfil que nao existe
    {"profile": "gestante", "routes": []},  # sem rota
])
def test_entrada_invalida_responde_422(api, corpo):
    assert api.post("/v1/routes/rank", json=corpo, headers=CHAVE).status_code == 422


def test_chat_responde(api):
    corpo = {"profile": "gestante", "routes": ROTAS,
             "messages": [{"role": "user", "content": "O elevador da Sé está funcionando?"}]}
    r = api.post("/v1/chat", json=corpo, headers=CHAVE)
    assert r.status_code == 200 and r.json()["reply"]


def test_chat_rejeita_conversa_que_nao_termina_com_pergunta(api):
    corpo = {"profile": "gestante", "messages": [{"role": "assistant", "content": "Olá!"}]}
    assert api.post("/v1/chat", json=corpo, headers=CHAVE).status_code == 422
