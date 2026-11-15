"""Orquestração: score por perfil -> reordenação -> explicação (RAG + LLM)."""
from __future__ import annotations

from datetime import datetime

from .catalog import Catalog
from .explain import Explainer
from .models import Profile, RankedRoute, RankResponse, Report, Route
from .reports import ReportStore, filter_active, utcnow
from .scoring import label_for, route_place_ids, score_route


class RouteRanker:
    def __init__(self, catalog: Catalog, report_store: ReportStore, explainer: Explainer):
        self.catalog = catalog
        self.report_store = report_store
        self.explainer = explainer

    def rank(self, profile: Profile, routes: list[Route], reports: list[Report] | None = None,
             explain: bool = True, now: datetime | None = None, max_explained: int = 3) -> RankResponse:
        now = now or utcnow()
        scored = []
        for route in routes:
            ids = route_place_ids(route)
            active = filter_active(reports, ids, now) if reports is not None else self.report_store.active_for(ids, now)
            scored.append((route, score_route(route, profile, self.catalog, active)))

        # Rotas bloqueadas vão para o fim; depois maior score; empate => mais rápida.
        scored.sort(key=lambda rs: (rs[1].blocking, -rs[1].score, rs[0].duration_min))

        out: list[RankedRoute] = []
        for pos, (route, res) in enumerate(scored):
            explanation = None
            if explain and pos < max_explained:  # limita custo/latência de LLM
                explanation = self.explainer.explain(profile, res.facts)
            out.append(RankedRoute(
                route_id=route.id,
                summary=route.summary,
                score=res.score,
                label=label_for(res.score, res.blocking),  # type: ignore[arg-type]
                blocking=res.blocking,
                duration_min=route.duration_min,
                walk_m=res.walk_m,
                breakdown=res.breakdown,
                explanation=explanation,
            ))
        return RankResponse(profile=profile, routes=out, generated_at=now)
