from app.explain import Explainer
from app.llm import LLMError
from app.models import Profile
from app.scoring import score_route
from tests.conftest import NOW, FakeLLM


def facts_for(catalog, store, routes, route_id, profile):
    route = next(r for r in routes if r.id == route_id)
    from app.scoring import route_place_ids
    return score_route(route, profile, catalog, store.active_for(route_place_ids(route), NOW)).facts


def test_resposta_fiel_do_llm_e_aceita(catalog, store, routes, retriever):
    facts = facts_for(catalog, store, routes, "r1-metro-se", Profile.GESTANTE)
    llm = FakeLLM({"resumo": "São 22 min, com 600 m a pé. O elevador da Sé está fora, então há 3 lances de escada.",
                   "pontos_de_atencao": ["Elevador da Estação Sé fora de operação"], "dica": "Use o corrimão."})
    exp = Explainer(retriever, llm).explain(Profile.GESTANTE, facts)
    assert exp.source == "llm" and exp.kb_refs


def test_numero_inventado_cai_no_fallback(catalog, store, routes, retriever):
    facts = facts_for(catalog, store, routes, "r1-metro-se", Profile.GESTANTE)
    llm = FakeLLM({"resumo": "Rota rápida, só 150 m de caminhada e 10 min.", "pontos_de_atencao": [], "dica": None})
    exp = Explainer(retriever, llm).explain(Profile.GESTANTE, facts)
    assert exp.source == "template_fallback" and exp.fallback_reason.startswith("numero_nao_fundamentado")
    assert "600 m" in exp.resumo  # o cidadão recebe os números reais


def test_contradicao_com_bloqueio_cai_no_fallback(catalog, store, routes, retriever):
    facts = facts_for(catalog, store, routes, "r1-metro-se", Profile.CADEIRANTE)
    llm = FakeLLM({"resumo": "Rota totalmente acessível, com elevador funcionando.", "pontos_de_atencao": []})
    exp = Explainer(retriever, llm).explain(Profile.CADEIRANTE, facts)
    assert exp.source == "template_fallback" and "contradiz" in exp.fallback_reason


def test_llm_fora_do_ar_cai_no_fallback(catalog, store, routes, retriever):
    facts = facts_for(catalog, store, routes, "r2-onibus-direto", Profile.IDOSO)
    exp = Explainer(retriever, FakeLLM(error=LLMError("timeout"))).explain(Profile.IDOSO, facts)
    assert exp.source == "template_fallback" and exp.fallback_reason == "llm_indisponivel" and exp.resumo


def test_formato_invalido_cai_no_fallback(catalog, store, routes, retriever):
    facts = facts_for(catalog, store, routes, "r2-onibus-direto", Profile.IDOSO)
    exp = Explainer(retriever, FakeLLM({"texto": "oi"})).explain(Profile.IDOSO, facts)
    assert exp.source == "template_fallback" and exp.fallback_reason == "formato_invalido"


def test_cache_evita_segunda_chamada_e_nao_guarda_fallback(catalog, store, routes, retriever):
    facts = facts_for(catalog, store, routes, "r2-onibus-direto", Profile.GESTANTE)
    ok = FakeLLM({"resumo": "Boa opção: 31 min e 350 m a pé.", "pontos_de_atencao": []})
    ex = Explainer(retriever, ok)
    ex.explain(Profile.GESTANTE, facts); ex.explain(Profile.GESTANTE, facts)
    assert ok.calls == 1
    bad = FakeLLM(error=LLMError("x"))
    ex2 = Explainer(retriever, bad)
    ex2.explain(Profile.GESTANTE, facts); ex2.explain(Profile.GESTANTE, facts)
    assert bad.calls == 2


def test_prompt_nao_leva_dados_pessoais(catalog, store, routes, retriever):
    facts = facts_for(catalog, store, routes, "r2-onibus-direto", Profile.GESTANTE)
    llm = FakeLLM({"resumo": "ok", "pontos_de_atencao": []})
    Explainer(retriever, llm).explain(Profile.GESTANTE, facts)
    for campo in ("nome", "email", "cpf", "user_id", "telefone"):
        assert campo not in llm.last_user.lower()
