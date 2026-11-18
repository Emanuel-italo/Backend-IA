from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .models import Report, ReportKind

CONFIRMED_MIN = 2


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def is_active(r: Report, now: datetime) -> bool:
    return now - r.last_confirmed_at < timedelta(hours=r.ttl_hours)


def is_confirmed(r: Report) -> bool:
    return r.confirmations >= CONFIRMED_MIN


def weight(r: Report) -> float:
    return 1.0 if is_confirmed(r) else 0.5


class ReportStore:
    def __init__(self, reports: list[Report]):
        self._reports = reports

    @classmethod
    def from_seed(cls, path: Path, now: datetime | None = None) -> "ReportStore":
        now = now or utcnow()
        raw = json.loads(path.read_text(encoding="utf-8"))
        reports = []
        for r in raw["relatos"]:
            reports.append(
                Report(
                    id=r["id"],
                    place_id=r["place_id"],
                    kind=ReportKind(r["kind"]),
                    text=r.get("text", ""),
                    reported_at=now - timedelta(hours=r["horas_desde_relato"]),
                    last_confirmed_at=now - timedelta(hours=r["horas_desde_ultima_confirmacao"]),
                    confirmations=r.get("confirmacoes", 1),
                    ttl_hours=r.get("ttl_horas", 72),
                )
            )
        return cls(reports)

    def active_for(self, place_ids: set[str], now: datetime | None = None) -> list[Report]:
        now = now or utcnow()
        return [r for r in self._reports if r.place_id in place_ids and is_active(r, now)]


def filter_active(reports: list[Report], place_ids: set[str], now: datetime) -> list[Report]:
    return [r for r in reports if r.place_id in place_ids and is_active(r, now)]
