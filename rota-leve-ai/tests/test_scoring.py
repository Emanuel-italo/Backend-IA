from datetime import timedelta

from app.models import Leg, Profile, Report, ReportKind, Route
from tests.conftest import NOW


def by_id(resp):
    return {r.route_id: r for r in resp.routes}


def test_gestante_prefere_onibus_direto_e_nao_a_rota_mais_rapida(ranker, routes):
    resp = ranker.rank(Profile.GESTANTE, routes, now=NOW, explain=False)
    assert resp.routes[0].route_id == "r2-onibus-direto"
    fastest = min(routes, key=lambda r: r.duration_min).id
    assert fastest == "r1-metro-se" and resp.routes[0].route_id != fastest


def test_elevador_fora_confirmado_bloqueia_cadeirante_mas_nao_gestante(ranker, routes):
    cad = by_id(ranker.rank(Profile.CADEIRANTE, routes, now=NOW, explain=False))
    ges = by_id(ranker.rank(Profile.GESTANTE, routes, now=NOW, explain=False))
    assert cad["r1-metro-se"].blocking and cad["r1-metro-se"].label == "nao_recomendada"
    assert cad["r1-metro-se"].score <= 25
    assert not ges["r1-metro-se"].blocking
    assert any(b.code == "escadas" for b in ges["r1-metro-se"].breakdown)


def test_rota_bloqueada_fica_por_ultimo(ranker, routes):
    resp = ranker.rank(Profile.CARRINHO, routes, now=NOW, explain=False)
    assert resp.routes[-1].blocking and not resp.routes[0].blocking


def test_relato_expirado_e_ignorado(ranker, routes):
    # rel-004 (República) expirou: a rota r3 não pode ter penalidade de elevador
    r3 = by_id(ranker.rank(Profile.CADEIRANTE, routes, now=NOW, explain=False))["r3-metro-onibus"]
    assert not r3.blocking
    assert all(b.code not in ("bloqueio", "elevador_incerto") for b in r3.breakdown)


def test_relato_nao_confirmado_penaliza_mas_nao_bloqueia(ranker, routes):
    r4 = by_id(ranker.rank(Profile.CADEIRANTE, routes, now=NOW, explain=False))["r4-metro-ladeira"]
    assert not r4.blocking
    assert any(b.code == "elevador_incerto" for b in r4.breakdown)


def test_relato_confirmado_vira_bloqueio_quando_recebe_segunda_confirmacao(ranker, routes):
    reports = [Report(id="x", place_id="station:anhangabau", kind=ReportKind.ELEVADOR_FORA,
                      reported_at=NOW - timedelta(hours=3), last_confirmed_at=NOW - timedelta(hours=1),
                      confirmations=2)]
    r4 = by_id(ranker.rank(Profile.CADEIRANTE, routes, reports=reports, now=NOW, explain=False))["r4-metro-ladeira"]
    assert r4.blocking


def test_sem_relatos_rota_do_metro_volta_a_ser_viavel(ranker, routes):
    r1 = by_id(ranker.rank(Profile.CADEIRANTE, routes, reports=[], now=NOW, explain=False))["r1-metro-se"]
    assert not r1.blocking and r1.score == 100


def test_local_desconhecido_penaliza_e_avisa_sem_inventar(ranker):
    route = Route(id="x", summary="Ônibus desconhecido", duration_min=10, legs=[
        Leg(mode="BUS", duration_min=10, from_place="desconhecido:Ponto X", to_place="stop:ubs-centro")])
    r = ranker.rank(Profile.CADEIRANTE, [route], now=NOW, explain=False).routes[0]
    assert any(b.code == "sem_dados" and "Ponto X" in b.detail for b in r.breakdown)
    assert not r.blocking and r.score < 100


def test_nenhuma_rota_acessivel_todas_marcadas(ranker, routes):
    only_blocked = [r for r in routes if r.id == "r1-metro-se"]
    resp = ranker.rank(Profile.CADEIRANTE, only_blocked, now=NOW)
    assert all(r.blocking for r in resp.routes)
    assert "não é indicada" in resp.routes[0].explanation.resumo
    assert "kb-sem-rota-acessivel" in resp.routes[0].explanation.kb_refs


def test_score_sempre_entre_0_e_100(ranker, routes):
    for p in Profile:
        for r in ranker.rank(p, routes, now=NOW, explain=False).routes:
            assert 0 <= r.score <= 100
