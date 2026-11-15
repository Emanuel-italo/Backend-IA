"""Catálogo de pontos (estações/paradas) com atributos de acessibilidade.

Em produção esta fonte viria de dados abertos (GTFS/SPTrans/Metrô) e de uma tabela mantida por gestores.
No repositório usamos dados SINTÉTICOS de demonstração (ver data/pontos.json).
"""
from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9 ]+", " ", text.lower()).strip()


@dataclass(frozen=True)
class Place:
    id: str
    name: str
    type: str  # station | bus_stop
    has_elevator: bool = False
    stairs_flights: int = 0  # lances de escada se não houver elevador
    covered: bool = True
    seating: bool = True
    aliases: tuple[str, ...] = field(default_factory=tuple)


class Catalog:
    def __init__(self, places: list[Place]):
        self._by_id = {p.id: p for p in places}
        self._by_name: dict[str, str] = {}
        for p in places:
            for n in (p.name, *p.aliases):
                self._by_name[normalize(n)] = p.id

    @classmethod
    def from_file(cls, path: Path) -> "Catalog":
        raw = json.loads(path.read_text(encoding="utf-8"))
        places = [
            Place(
                id=p["id"],
                name=p["name"],
                type=p["type"],
                has_elevator=p.get("has_elevator", False),
                stairs_flights=p.get("stairs_flights", 0),
                covered=p.get("covered", True),
                seating=p.get("seating", True),
                aliases=tuple(p.get("aliases", [])),
            )
            for p in raw["places"]
        ]
        return cls(places)

    def get(self, place_id: str | None) -> Place | None:
        return self._by_id.get(place_id) if place_id else None

    def name_of(self, place_id: str | None) -> str:
        p = self.get(place_id)
        if p:
            return p.name
        if place_id and place_id.startswith("desconhecido:"):
            return place_id.split(":", 1)[1]
        return place_id or "local sem dados"

    def match_name(self, name: str) -> str | None:
        """Casa um nome vindo de API externa (ex.: Google Directions) com um id do catálogo."""
        key = normalize(name)
        if key in self._by_name:
            return self._by_name[key]
        for alias_key, pid in self._by_name.items():
            if alias_key and (alias_key in key or key in alias_key):
                return pid
        return None
