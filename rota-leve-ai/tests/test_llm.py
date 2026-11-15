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


# ---------------------------------------------------------------- Grok (formato OpenAI)
from app.config import Settings  # noqa: E402
from app.llm import GeminiClient as _G, OpenAICompatibleClient, build_llm  # noqa: E402


def openai_ok(text):
    return {"choices": [{"message": {"role": "assistant", "content": text}}]}


def grok(handler, retries=1):
    return OpenAICompatibleClient("chave-de-teste", "grok-x", timeout_s=1, max_retries=retries,
                                  transport=httpx.MockTransport(handler))


def test_grok_sucesso_bearer_no_header_e_url_padrao():
    seen = {}

    def handler(req):
        seen["url"], seen["auth"] = str(req.url), req.headers.get("authorization")
        seen["body"] = json.loads(req.content)
        return httpx.Response(200, json=openai_ok('```json\n{"resumo": "ok"}\n```'))

    assert grok(handler).generate_json("s", "u") == {"resumo": "ok"}
    assert seen["url"] == "https://api.x.ai/v1/chat/completions"
    assert seen["auth"] == "Bearer chave-de-teste" and "chave-de-teste" not in seen["url"]
    assert seen["body"]["model"] == "grok-x"
    assert [m["role"] for m in seen["body"]["messages"]] == ["system", "user"]


def test_grok_400_tenta_de_novo_sem_response_format():
    bodies = []

    def handler(req):
        body = json.loads(req.content)
        bodies.append(body)
        if "response_format" in body:
            return httpx.Response(400, json={"error": "não suportado"})
        return httpx.Response(200, json=openai_ok('{"resumo": "ok"}'))

    assert grok(handler, retries=0).generate_json("s", "u")["resumo"] == "ok"
    assert len(bodies) == 2 and "response_format" not in bodies[1]


def test_grok_429_faz_retry_e_401_nao(monkeypatch):
    monkeypatch.setattr("app.llm.time.sleep", lambda s: None)
    calls = []

    def h429(req):
        calls.append(1)
        return httpx.Response(429)

    with pytest.raises(LLMError):
        grok(h429, retries=1).generate_json("s", "u")
    assert len(calls) == 2

    calls.clear()

    def h401(req):
        calls.append(1)
        return httpx.Response(401)

    with pytest.raises(LLMError) as exc:
        grok(h401, retries=3).generate_json("s", "u")
    assert len(calls) == 1 and "chave-de-teste" not in str(exc.value)


@pytest.mark.parametrize("payload", [{"choices": []}, openai_ok(""), openai_ok("não é json"), openai_ok("[1]")])
def test_grok_resposta_invalida_vira_llm_error(payload, monkeypatch):
    monkeypatch.setattr("app.llm.time.sleep", lambda s: None)
    with pytest.raises(LLMError):
        grok(lambda req: httpx.Response(200, json=payload), retries=0).generate_json("s", "u")


def test_build_llm_escolhe_provedor():
    assert build_llm(Settings(llm_api_key=None, llm_model="m")) is None
    assert build_llm(Settings(llm_api_key="k", llm_model="")) is None
    assert isinstance(build_llm(Settings(llm_api_key="k", llm_model="m", llm_provider="grok")), OpenAICompatibleClient)
    assert isinstance(build_llm(Settings(llm_api_key="k", llm_model="m", llm_provider="gemini")), _G)
