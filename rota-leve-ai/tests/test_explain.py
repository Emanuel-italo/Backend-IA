"""Testes da explicação das rotas. O FakeLLM (conftest.py) faz o papel do modelo, com respostas fixas."""
from app.explain import Explainer
from app.llm import LLMError
from app.models import Profile
from app.scoring import route_place_ids, score_route
from tests.conftest import NOW, FakeLLM


def fatos_da_rota(catalog, store, routes, route_id, profile):
    route = next(r for r in routes if r.id == route_id)
    return score_route(route, profile, catalog, store.active_for(route_place_ids(route), NOW)).facts


def test_resposta_correta_do_modelo_e_aceita(catalog, store, routes, retriever):
    fatos = fatos_da_rota(catalog, store, routes, "r1-metro-se", Profile.GESTANTE)
    llm = FakeLLM({"resumo": "São 22 min, com 600 m a pé. O elevador da Sé está fora, então há 3 lances de escada.",
                   "pontos_de_atencao": ["Elevador da Estação Sé fora de operação"], "dica": "Use o corrimão."})
    exp = Explainer(retriever, llm).explain(Profile.GESTANTE, fatos)
    assert exp.source == "llm"


def test_modelo_inventa_numero_e_a_pessoa_recebe_o_texto_pronto(catalog, store, routes, retriever):
    fatos = fatos_da_rota(catalog, store, routes, "r1-metro-se", Profile.GESTANTE)
    llm = FakeLLM({"resumo": "Rota rápida, só 150 m de caminhada e 10 min.", "pontos_de_atencao": []})
    exp = Explainer(retriever, llm).explain(Profile.GESTANTE, fatos)
    assert exp.source == "template_fallback"
    assert "600 m" in exp.resumo  # o texto pronto usa os números verdadeiros


def test_modelo_fora_do_ar_e_a_pessoa_recebe_o_texto_pronto(catalog, store, routes, retriever):
    fatos = fatos_da_rota(catalog, store, routes, "r2-onibus-direto", Profile.IDOSO)
    exp = Explainer(retriever, FakeLLM(error=LLMError("timeout"))).explain(Profile.IDOSO, fatos)
    assert exp.source == "template_fallback" and exp.fallback_reason == "llm_indisponivel" and exp.resumo
