"""Converte a resposta da Google Directions API (mode=transit, alternatives=true) no modelo Route.

O roteamento NÃO é feito aqui: a Directions API gera as rotas candidatas e este serviço
apenas avalia e reordena (camada de acessibilidade). Paradas são casadas com o catálogo pelo nome;
sem correspondência => place=None, que o score trata como "sem dados" (penaliza e avisa, não inventa).
"""
from __future__ import annotations

from ..catalog import Catalog
from ..models import Leg, Route

VEHICLE_MODE = {
    "SUBWAY": "SUBWAY", "METRO_RAIL": "SUBWAY", "HEAVY_RAIL": "TRAIN", "COMMUTER_TRAIN": "TRAIN",
    "RAIL": "TRAIN", "MONORAIL": "SUBWAY", "TRAM": "TRAIN", "BUS": "BUS", "INTERCITY_BUS": "BUS",
    "TROLLEYBUS": "BUS",
}


def routes_from_directions(payload: dict, catalog: Catalog) -> list[Route]:
    if payload.get("status") not in (None, "OK"):
        return []
    routes: list[Route] = []
    for idx, r in enumerate(payload.get("routes", []), start=1):
        legs: list[Leg] = []
        total_s = 0
        lines: list[str] = []
        for g_leg in r.get("legs", []):
            total_s += g_leg.get("duration", {}).get("value", 0)
            for step in g_leg.get("steps", []):
                dist = int(step.get("distance", {}).get("value", 0))
                mins = round(step.get("duration", {}).get("value", 0) / 60)
                if step.get("travel_mode") == "TRANSIT":
                    td = step.get("transit_details", {})
                    line = td.get("line", {})
                    vtype = line.get("vehicle", {}).get("type", "BUS")
                    name = line.get("short_name") or line.get("name")
                    if name:
                        lines.append(name)
                    legs.append(Leg(
                        mode=VEHICLE_MODE.get(vtype, "BUS"),
                        distance_m=dist,
                        duration_min=mins,
                        from_place=_match(catalog, td.get("departure_stop", {}).get("name")),
                        to_place=_match(catalog, td.get("arrival_stop", {}).get("name")),
                        line=name,
                        num_stops=td.get("num_stops"),
                    ))
                elif step.get("travel_mode") == "WALKING":
                    legs.append(Leg(mode="WALK", distance_m=dist, duration_min=mins))
        if not legs:
            continue
        summary = " + ".join(dict.fromkeys(lines)) or "A pé"
        routes.append(Route(id=f"gdir-{idx}", summary=summary, duration_min=round(total_s / 60), legs=legs))
    return routes


def _match(catalog: Catalog, name: str | None) -> str | None:
    if not name:
        return None
    # Mantém o nome original quando não há correspondência, para aparecer no aviso "sem dados".
    return catalog.match_name(name) or f"desconhecido:{name}"
