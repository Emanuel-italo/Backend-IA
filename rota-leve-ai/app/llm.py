"""Clientes de IA generativa atrás de uma interface mínima (`generate_json`).

Provedor padrão: Grok (xAI), pela API compatível com o formato OpenAI (`/chat/completions`).
Gemini continua disponível como alternativa (LLM_PROVIDER=gemini).

Por que REST puro com httpx: evita acoplamento a SDK, facilita timeout/retry e troca de provedor
(basta outra classe com `generate_json`). Provedor, modelo e URL vêm de variáveis de ambiente.
"""
from __future__ import annotations

import json
import logging
import time
from typing import TYPE_CHECKING, Protocol

import httpx

if TYPE_CHECKING:
    from .config import Settings

log = logging.getLogger("rota_leve.llm")

RETRYABLE = (429, 500, 502, 503, 504)


class LLMError(Exception):
    pass


class LLMClient(Protocol):
    name: str

    def generate_json(self, system: str, user: str) -> dict: ...


class GeminiClient:
    BASE_URL = "https://generativelanguage.googleapis.com/v1beta"

    def __init__(self, api_key: str, model: str, timeout_s: float = 10, max_retries: int = 1,
                 transport: httpx.BaseTransport | None = None):
        self.name = model
        self._model = model
        self._max_retries = max_retries
        # A chave vai em header (nunca na URL, para não vazar em logs de acesso).
        self._client = httpx.Client(
            timeout=timeout_s, headers={"x-goog-api-key": api_key}, transport=transport
        )

    def generate_json(self, system: str, user: str) -> dict:
        body = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            # Sem `temperature`: os modelos Gemini mais recentes não aceitam mais parâmetros de amostragem.
            "generationConfig": {"maxOutputTokens": 2048, "responseMimeType": "application/json"},
        }
        url = f"{self.BASE_URL}/models/{self._model}:generateContent"
        last: Exception | None = None
        attempts = self._max_retries + 1
        attempt = 0
        while attempt < attempts:
            attempt += 1
            try:
                resp = self._client.post(url, json=body)
                if resp.status_code == 400 and "generationConfig" in body:
                    # Compatibilidade entre versões da API: tenta de novo só com o prompt
                    # (o prompt já exige JSON e o parser tolera cercas de código).
                    body.pop("generationConfig")
                    attempts += 1
                    continue
                if resp.status_code in RETRYABLE:
                    raise LLMError(f"HTTP {resp.status_code} do provedor")
                if resp.status_code >= 400:
                    # chave/modelo inválidos: repetir não resolve
                    last = LLMError(f"HTTP {resp.status_code} do provedor")
                    break
                return _parse(resp.json())
            except (httpx.HTTPError, LLMError, ValueError) as exc:
                last = exc
                if attempt < attempts:
                    time.sleep(0.5 * attempt)
        raise LLMError(f"Falha ao chamar o modelo: {type(last).__name__}: {last}")


class OpenAICompatibleClient:
    """Cliente para APIs no formato OpenAI `/chat/completions`. Padrão: Grok (xAI)."""

    DEFAULT_BASE_URL = "https://api.x.ai/v1"

    def __init__(self, api_key: str, model: str, base_url: str = DEFAULT_BASE_URL, timeout_s: float = 10,
                 max_retries: int = 1, transport: httpx.BaseTransport | None = None):
        self.name = model
        self._model = model
        self._url = base_url.rstrip("/") + "/chat/completions"
        self._max_retries = max_retries
        self._client = httpx.Client(
            timeout=timeout_s, headers={"Authorization": f"Bearer {api_key}"}, transport=transport
        )

    def generate_json(self, system: str, user: str) -> dict:
        body = {
            "model": self._model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "max_tokens": 2048,
            "response_format": {"type": "json_object"},
        }
        last: Exception | None = None
        attempts = self._max_retries + 1
        attempt = 0
        while attempt < attempts:
            attempt += 1
            try:
                resp = self._client.post(self._url, json=body)
                if resp.status_code == 400 and "response_format" in body:
                    # Nem todo modelo aceita `response_format`: tenta de novo só com o prompt
                    # (o prompt já exige JSON e o parser tolera cercas de código).
                    body.pop("response_format")
                    attempts += 1
                    continue
                if resp.status_code in RETRYABLE:
                    raise LLMError(f"HTTP {resp.status_code} do provedor")
                if resp.status_code >= 400:
                    # chave/modelo inválidos: repetir não resolve
                    last = LLMError(f"HTTP {resp.status_code} do provedor")
                    break
                return _parse_text(_openai_text(resp.json()))
            except (httpx.HTTPError, LLMError, ValueError) as exc:
                last = exc
                if attempt < attempts:
                    time.sleep(0.5 * attempt)
        raise LLMError(f"Falha ao chamar o modelo: {type(last).__name__}: {last}")


def build_llm(s: "Settings") -> LLMClient | None:
    """Escolhe o cliente pelo ambiente. Sem chave ou sem modelo => None (modo template)."""
    if not s.llm_api_key:
        return None
    if not s.llm_model:
        log.warning("LLM_API_KEY definida, mas LLM_MODEL vazio: IA generativa desativada (modo template).")
        return None
    if s.llm_provider == "gemini":
        return GeminiClient(s.llm_api_key, s.llm_model, s.llm_timeout_s, s.llm_max_retries)
    return OpenAICompatibleClient(s.llm_api_key, s.llm_model, s.llm_base_url, s.llm_timeout_s, s.llm_max_retries)


def _openai_text(payload: dict) -> str:
    try:
        text = payload["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise LLMError("Resposta do modelo sem conteúdo") from exc
    if not isinstance(text, str) or not text.strip():
        raise LLMError("Resposta do modelo sem conteúdo")
    return text


def _parse(payload: dict) -> dict:
    try:
        text = payload["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError, TypeError) as exc:
        raise LLMError("Resposta do modelo sem conteúdo (possível bloqueio de segurança)") from exc
    return _parse_text(text)


def _parse_text(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`").removeprefix("json").strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise LLMError("Modelo não retornou JSON válido") from exc
    if not isinstance(data, dict):
        raise LLMError("JSON do modelo não é um objeto")
    return data
