"""Testes da chamada à Groq. O MockTransport simula a Groq, então não precisa de internet nem de chave."""
import json

import httpx
import pytest

from app.llm import GroqClient, LLMError, ler_json


def cliente(handler):
    return GroqClient("chave-de-teste", "modelo-x", timeout_s=1, transport=httpx.MockTransport(handler))


def test_envia_a_chave_no_header_e_le_a_resposta_em_json():
    visto = {}

    def groq_falsa(req):
        visto["auth"] = req.headers.get("authorization")
        visto["body"] = json.loads(req.content)
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"resumo": "ok"}'}}]})

    assert cliente(groq_falsa).generate_json("instruções", "pergunta") == {"resumo": "ok"}
    assert visto["auth"] == "Bearer chave-de-teste"
    assert [m["role"] for m in visto["body"]["messages"]] == ["system", "user"]


def test_erro_da_groq_vira_llm_error_sem_mostrar_a_chave():
    erro = {"error": {"message": "The model `xyz` does not exist"}}
    with pytest.raises(LLMError) as exc:
        cliente(lambda req: httpx.Response(404, json=erro)).generate_json("s", "u")
    assert "does not exist" in str(exc.value) and "chave-de-teste" not in str(exc.value)


def test_le_json_mesmo_com_cercas_ou_texto_em_volta():
    assert ler_json('```json\n{"resumo": "ok"}\n```') == {"resumo": "ok"}
    assert ler_json('Claro! {"resumo": "ok"}') == {"resumo": "ok"}
    with pytest.raises(LLMError):
        ler_json("não é json")
