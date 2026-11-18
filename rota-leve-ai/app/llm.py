from __future__ import annotations

import json

import httpx


class LLMError(Exception):
    pass


class GroqClient:
    def __init__(self, api_key: str, model: str, base_url: str = "https://api.groq.com/openai/v1",
                 timeout_s: float = 10, transport: httpx.BaseTransport | None = None):
        self.name = model
        self.model = model
        self.url = base_url.rstrip("/") + "/chat/completions"
        # a chave vai no header e nao na url
        self.http = httpx.Client(timeout=timeout_s, headers={"Authorization": f"Bearer {api_key}"},
                                 transport=transport)

    def generate_json(self, system: str, user: str) -> dict:
        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "response_format": {"type": "json_object"},
        }
        try:
            resp = self.http.post(self.url, json=body)
        except httpx.HTTPError as exc:
            raise LLMError(f"Falha de rede: {type(exc).__name__}") from exc

        if resp.status_code != 200:
            raise LLMError(f"HTTP {resp.status_code} do provedor: {_mensagem_de_erro(resp)}")

        try:
            texto = resp.json()["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise LLMError("Resposta do modelo sem conteúdo") from exc
        return ler_json(texto)


def ler_json(texto: str) -> dict:
    texto = (texto or "").strip()
    if texto.startswith("```"):
        texto = texto.strip("`").removeprefix("json").strip()
    inicio, fim = texto.find("{"), texto.rfind("}")
    if inicio == -1 or fim < inicio:
        raise LLMError("Modelo não retornou JSON")
    try:
        dados = json.loads(texto[inicio:fim + 1])
    except json.JSONDecodeError as exc:
        raise LLMError("Modelo não retornou JSON válido") from exc
    return dados


def _mensagem_de_erro(resp: httpx.Response) -> str:
    try:
        erro = resp.json().get("error")
        msg = erro.get("message") if isinstance(erro, dict) else erro
    except (ValueError, AttributeError):
        msg = None
    return str(msg or resp.text or "sem detalhe")[:200]


def build_llm(s) -> GroqClient | None:
    if not s.llm_api_key or not s.llm_model:
        return None
    return GroqClient(s.llm_api_key, s.llm_model, s.llm_base_url, s.llm_timeout_s)
