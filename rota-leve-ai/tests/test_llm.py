import json

import httpx
import pytest

from app.llm import GeminiClient, LLMError


def gemini_ok(text):
    return {"candidates": [{"content": {"parts": [{"text": text}]}}]}


def client(handler, retries=1):
    return GeminiClient("chave-de-teste", "modelo-x", timeout_s=1, max_retries=retries,
                        transport=httpx.MockTransport(handler))


def test_sucesso_e_chave_vai_no_header_nao_na_url():
    seen = {}

    def handler(req):
        seen["url"], seen["key"] = str(req.url), req.headers.get("x-goog-api-key")
        return httpx.Response(200, json=gemini_ok('```json\n{"resumo": "ok"}\n```'))

    assert client(handler).generate_json("s", "u") == {"resumo": "ok"}
    assert seen["key"] == "chave-de-teste" and "chave-de-teste" not in seen["url"]


def test_400_tenta_de_novo_sem_generation_config():
    bodies = []

    def handler(req):
        body = json.loads(req.content)
        bodies.append(body)
        if "generationConfig" in body:
            return httpx.Response(400, json={"error": "campo inválido"})
        return httpx.Response(200, json=gemini_ok('{"resumo": "ok"}'))

    assert client(handler, retries=0).generate_json("s", "u")["resumo"] == "ok"
    assert len(bodies) == 2 and "generationConfig" not in bodies[1]


def test_503_faz_retry_e_depois_falha(monkeypatch):
    monkeypatch.setattr("app.llm.time.sleep", lambda s: None)
    calls = []

    def handler(req):
        calls.append(1)
        return httpx.Response(503)

    with pytest.raises(LLMError):
        client(handler, retries=1).generate_json("s", "u")
    assert len(calls) == 2


def test_401_nao_faz_retry_e_erro_nao_vaza_a_chave():
    calls = []

    def handler(req):
        calls.append(1)
        return httpx.Response(401)

    with pytest.raises(LLMError) as exc:
        client(handler, retries=3).generate_json("s", "u")
    assert len(calls) == 1 and "chave-de-teste" not in str(exc.value)


@pytest.mark.parametrize("payload", [{"candidates": []}, gemini_ok("não é json"), gemini_ok("[1, 2]")])
def test_resposta_invalida_vira_llm_error(payload, monkeypatch):
    monkeypatch.setattr("app.llm.time.sleep", lambda s: None)
    with pytest.raises(LLMError):
        client(lambda req: httpx.Response(200, json=payload), retries=0).generate_json("s", "u")
