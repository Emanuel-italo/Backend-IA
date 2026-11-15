"""Validação de fidelidade (groundedness) da resposta do LLM.

O LLM só pode REDIGIR; os fatos vêm do score e dos relatos. Antes de mostrar ao cidadão, checamos:
1. Todo número citado existe nos fatos ou nos trechos recuperados (pega distâncias/tempos inventados).
2. O texto não contradiz fatos críticos (ex.: dizer "elevador funcionando" com relato de elevador fora).
Reprovou => descartamos a resposta e usamos o template determinístico.
É uma checagem heurística (não detecta toda alucinação); as limitações estão no README.
"""
from __future__ import annotations

import re

NUM = re.compile(r"\d+(?:[.,]\d+)?")

CONTRADICTIONS_IF_BLOCKED = (
    "totalmente acessivel", "100% acessivel", "sem nenhum problema", "sem obstaculos",
    "rota ideal", "pode ir tranquil",
)
CONTRADICTIONS_IF_ELEVATOR_OUT = ("elevador funcionando", "elevadores funcionando", "elevador em operacao")


def _numbers(obj) -> set[float]:
    found: set[float] = set()
    if isinstance(obj, bool):
        return found
    if isinstance(obj, (int, float)):
        found.add(float(obj))
    elif isinstance(obj, str):
        for m in NUM.findall(obj):
            found.add(float(m.replace(",", ".")))
    elif isinstance(obj, dict):
        for v in obj.values():
            found |= _numbers(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            found |= _numbers(v)
    return found


def _plain(text: str) -> str:
    import unicodedata

    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()


def check(text: str, facts: dict, context_texts: list[str]) -> tuple[bool, str | None]:
    """Retorna (ok, motivo_da_reprovacao)."""
    allowed = _numbers(facts) | _numbers(context_texts)
    for n in _numbers(text):
        if n not in allowed:
            return False, f"numero_nao_fundamentado:{n:g}"
    plain = _plain(text)
    if facts.get("bloqueada_para_o_perfil"):
        for phrase in CONTRADICTIONS_IF_BLOCKED:
            if phrase in plain:
                return False, f"contradiz_bloqueio:{phrase}"
    if any(e.get("confirmado") for e in facts.get("elevadores_com_relato", [])):
        for phrase in CONTRADICTIONS_IF_ELEVATOR_OUT:
            if phrase in plain:
                return False, f"contradiz_elevador:{phrase}"
    return True, None
