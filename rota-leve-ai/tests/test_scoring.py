"""Testes da nota de acessibilidade (regras por perfil, sem IA)."""
from app.models import Profile
from tests.conftest import NOW


def por_id(resp):
    return {r.route_id: r for r in resp.routes}


def test_gestante_recebe_onibus_direto_primeiro_e_nao_a_rota_mais_rapida(ranker, routes):
    resp = ranker.rank(Profile.GESTANTE, routes, now=NOW, explain=False)
    mais_rapida = min(routes, key=lambda r: r.duration_min).id
    assert resp.routes[0].route_id == "r2-onibus-direto"
    assert mais_rapida == "r1-metro-se"


def test_elevador_quebrado_bloqueia_a_rota_para_cadeirante_e_ela_vai_para_o_fim(ranker, routes):
    resp = ranker.rank(Profile.CADEIRANTE, routes, now=NOW, explain=False)
    se = por_id(resp)["r1-metro-se"]
    assert se.blocking and se.label == "nao_recomendada"
    assert resp.routes[-1].route_id == "r1-metro-se"


def test_relato_expirado_e_ignorado(ranker, routes):
    # O relato da estação República expirou: a rota r3 não pode perder pontos por ele
    r3 = por_id(ranker.rank(Profile.CADEIRANTE, routes, now=NOW, explain=False))["r3-metro-onibus"]
    assert not r3.blocking
    assert all(b.code != "elevador_incerto" for b in r3.breakdown)
