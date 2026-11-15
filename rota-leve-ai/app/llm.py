"""Cliente de IA generativa (Gemini via REST) atrás de uma interface mínima.

Por que REST puro com httpx: evita acoplamento a SDK, facilita timeout/retry e troca de provedor
(basta outra classe com `generate_json`). O nome do modelo vem de LLM_MODEL (env).
"""
from __future__ import annotations

import json
import time
from typing import Protocol

import httpx


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
                if resp.status_code in (429, 500, 502, 503, 504):
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


def _parse(payload: dict) -> dict:
    try:
        text = payload["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError, TypeError) as exc:
        raise LLMError("Resposta do modelo sem conteúdo (possível bloqueio de segurança)") from exc
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
