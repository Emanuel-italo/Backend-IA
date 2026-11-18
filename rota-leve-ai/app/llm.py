"""Chamada ao modelo de IA generativa (Groq).

A Groq usa o mesmo formato da API da OpenAI: enviamos uma lista de mensagens
(instruções do sistema + pergunta) e recebemos o texto da resposta.
Pedimos a resposta em JSON para conseguir ler os campos com segurança.
"""
from __future__ import annotations

import json

import httpx


class LLMError(Exception):
    """Qualquer problema ao falar com o modelo: rede, chave, modelo inexistente ou resposta inválida."""


class GroqClient:
    def __init__(self, api_key: str, model: str, base_url: str = "https://api.groq.com/openai/v1",
                 timeout_s: float = 10, transport: httpx.BaseTransport | None = None):
        self.name = model
        self.model = model
        self.url = base_url.rstrip("/") + "/chat/completions"
        # A chave vai no header (nunca na URL, para não aparecer em logs).
        self.http = httpx.Client(timeout=timeout_s, headers={"Authorization": f"Bearer {api_key}"},
                                 transport=transport)

    def generate_json(self, system: str, user: str) -> dict:
        """Envia as instruções e a pergunta; devolve a resposta do modelo já convertida em dicionário."""
        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "response_format": {"type": "json_object"},  # pede ao modelo uma resposta em JSON
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
    """Converte o texto do modelo em dicionário. Aceita JSON com ```cercas``` ou com texto em volta."""
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
    """Mensagem curta do provedor (ex.: "model does not exist") para o log. Não contém a chave."""
    try:
        erro = resp.json().get("error")
        msg = erro.get("message") if isinstance(erro, dict) else erro
    except (ValueError, AttributeError):
        msg = None
    return str(msg or resp.text or "sem detalhe")[:200]


def build_llm(s) -> GroqClient | None:
    """Cria o cliente se houver chave e modelo configurados. Sem eles, o serviço funciona em modo template."""
    if not s.llm_api_key or not s.llm_model:
        return None
    return GroqClient(s.llm_api_key, s.llm_model, s.llm_base_url, s.llm_timeout_s)
