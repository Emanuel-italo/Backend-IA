from __future__ import annotations

import math
from dataclasses import dataclass

from .catalog import Catalog
from .models import Profile, Report, ReportKind, Route, ScoreItem
from .reports import is_confirmed, weight


@dataclass(frozen=True)
class ProfileRules:
    label: str
    max_walk_m: int
    walk_over_per_100m: int
    stairs_per_flight: int
    needs_step_free: bool
    slope_steep: int
    no_seat: int
    no_cover: int
    bad_sidewalk: int
    transfer: int
    unknown_place: int


RULES: dict[Profile, ProfileRules] = {
    Profile.GESTANTE: ProfileRules("gestante", 500, 5, 12, False, 10, 8, 4, 10, 5, 6),
    Profile.CADEIRANTE: ProfileRules("pessoa em cadeira de rodas", 600, 4, 0, True, 20, 0, 4, 30, 6, 15),
    Profile.CARRINHO: ProfileRules("pessoa com carrinho de bebê", 700, 3, 0, True, 12, 2, 5, 20, 5, 12),
    Profile.IDOSO: ProfileRules("pessoa idosa", 400, 6, 10, False, 12, 10, 5, 12, 6, 6),
    Profile.MOBILIDADE_TEMPORARIA: ProfileRules(
        "pessoa com mobilidade reduzida temporária", 300, 7, 15, False, 15, 10, 4, 15, 7, 8
    ),
}

BLOCK_PENALTY = 60
TRANSIT = {"SUBWAY", "TRAIN", "BUS"}


@dataclass
class ScoreResult:
    score: int
    blocking: bool
    breakdown: list[ScoreItem]
    walk_m: int
    facts: dict


def route_place_ids(route: Route) -> set[str]:
    ids: set[str] = set()
    for leg in route.legs:
        for pid in (leg.from_place, leg.to_place, leg.segment_id):
            if pid:
                ids.add(pid)
    return ids


def label_for(score: int, blocking: bool) -> str:
    if blocking or score < 50:
        return "nao_recomendada"
    return "recomendada" if score >= 80 else "com_ressalvas"


def score_route(route: Route, profile: Profile, catalog: Catalog, active_reports: list[Report]) -> ScoreResult:
    rules = RULES[profile]
    items: list[ScoreItem] = []
    blocking = False
    by_place: dict[str, list[Report]] = {}
    for r in active_reports:
        by_place.setdefault(r.place_id, []).append(r)

    def add(code: str, points: float, detail: str) -> None:
        pts = int(round(points))
        if pts != 0:
            items.append(ScoreItem(code=code, points=pts, detail=detail))

    # 1 - caminhada
    walk_m = sum(l.distance_m for l in route.legs if l.mode == "WALK")
    if walk_m > rules.max_walk_m:
        over = walk_m - rules.max_walk_m
        add(
            "caminhada_longa",
            -min(30, math.ceil(over / 100) * rules.walk_over_per_100m),
            f"{walk_m} m de caminhada, acima do limite de {rules.max_walk_m} m do perfil",
        )

    # 2 - trechos a pe (subida e calcada ruim)
    for leg in route.legs:
        if leg.mode != "WALK":
            continue
        if leg.slope == "ingreme":
            add("ladeira", -rules.slope_steep, f"trecho a pé íngreme ({leg.distance_m} m)")
        elif leg.slope == "leve":
            add("ladeira", -rules.slope_steep / 2, f"trecho a pé com inclinação leve ({leg.distance_m} m)")
        for r in by_place.get(leg.segment_id or "", []):
            if r.kind == ReportKind.CALCADA_RUIM:
                status = _status(r)
                add("calcada_ruim", -rules.bad_sidewalk * weight(r), f"calçada com problema relatado ({status})")
                if rules.needs_step_free and is_confirmed(r):
                    blocking = True
                    add("bloqueio", -BLOCK_PENALTY, "calçada intransitável para este perfil (relato confirmado)")

    # 3 - estacoes e pontos
    used: list[str | None] = []
    for leg in route.legs:
        if leg.mode in TRANSIT:
            for pid in (leg.from_place, leg.to_place):
                if pid not in used:
                    used.append(pid)

    elevators_out: list[dict] = []
    unknown = 0
    for pid in used:
        place = catalog.get(pid)
        if place is None:
            unknown += 1
            add("sem_dados", -rules.unknown_place, f"sem dados de acessibilidade para {catalog.name_of(pid)}")
            continue
        reps = by_place.get(place.id, [])
        elev_reports = [r for r in reps if r.kind == ReportKind.ELEVADOR_FORA]
        confirmed_out = any(is_confirmed(r) for r in elev_reports)
        if place.type == "station":
            for r in elev_reports:
                elevators_out.append(
                    {"local": place.name, "confirmado": is_confirmed(r), "confirmacoes": r.confirmations}
                )
            elevator_ok = place.has_elevator and not confirmed_out
            if not elevator_ok and place.stairs_flights > 0:
                why = "elevador fora de operação (relato confirmado)" if place.has_elevator else "sem elevador"
                if rules.needs_step_free:
                    blocking = True
                    add("bloqueio", -BLOCK_PENALTY, f"{place.name}: {why} e acesso só por escada")
                else:
                    add(
                        "escadas",
                        -rules.stairs_per_flight * place.stairs_flights,
                        f"{place.name}: {why}, {place.stairs_flights} lances de escada",
                    )
            elif elev_reports and not confirmed_out:
                # so 1 confirmacao: tira metade dos pontos e nao bloqueia
                base = BLOCK_PENALTY / 2 if rules.needs_step_free else rules.stairs_per_flight * place.stairs_flights
                add("elevador_incerto", -base * 0.5, f"{place.name}: elevador com relato de falha ainda não confirmado")
            for r in reps:
                if r.kind == ReportKind.ESCADA_ROLANTE_FORA and not rules.needs_step_free and not place.has_elevator:
                    add("escada_rolante", -rules.stairs_per_flight * weight(r), f"{place.name}: escada rolante parada ({_status(r)})")
        else:
            no_cover = (not place.covered) or any(r.kind == ReportKind.SEM_COBERTURA for r in reps)
            if no_cover:
                add("sem_cobertura", -rules.no_cover, f"{place.name}: ponto sem cobertura")
            if not place.seating:
                add("sem_assento", -rules.no_seat, f"{place.name}: ponto sem banco")

    # 4 - baldeacoes
    transit_legs = [l for l in route.legs if l.mode in TRANSIT]
    transfers = max(0, len(transit_legs) - 1)
    if transfers:
        add("baldeacao", -rules.transfer * transfers, f"{transfers} baldeação(ões)")

    score = max(0, min(100, 100 + sum(i.points for i in items)))
    if blocking:
        score = min(score, 25)

    facts = {
        "perfil": rules.label,
        "rota": route.summary,
        "duracao_min": route.duration_min,
        "caminhada_m": walk_m,
        "limite_caminhada_m": rules.max_walk_m,
        "baldeacoes": transfers,
        "score": score,
        "classificacao": label_for(score, blocking),
        "bloqueada_para_o_perfil": blocking,
        "elevadores_com_relato": elevators_out,
        "locais_sem_dados": unknown,
        "problemas": [i.detail for i in items if i.points < 0],
        "codigos": sorted({i.code for i in items}),
    }
    return ScoreResult(score=score, blocking=blocking, breakdown=items, walk_m=walk_m, facts=facts)


def _status(r: Report) -> str:
    return f"confirmado por {r.confirmations} pessoas" if is_confirmed(r) else "ainda não confirmado"
