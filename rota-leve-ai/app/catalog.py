from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Place:
    id: str
    name: str
    type: str  # station ou bus_stop
    has_elevator: bool = False
    stairs_flights: int = 0
    covered: bool = True
    seating: bool = True


class Catalog:
    def __init__(self, places: list[Place]):
        self._by_id = {p.id: p for p in places}

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
