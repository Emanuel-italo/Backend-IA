import pytest

from app.chat import ChatAssistant
from app.llm import LLMError
from app.models import ChatMessage, Profile
from tests.conftest import NOW, FakeLLM


def pergunta(texto):
    return [ChatMessage(role="user", content=texto)]


@pytest.fixture()
def fatos(ranker, routes):
    return ranker.route_facts(Profile.GESTANTE, routes, now=NOW)


def test_resposta_correta_e_aceita_e_cita_a_rota(retriever, fatos):
    primeira = fatos[0]
    llm = FakeLLM({"resposta": f"A melhor para você é {primeira['rota']}, com {primeira['caminhada_m']} m a pé.",
                   "rotas_citadas": [primeira["route_id"]]})
    r = ChatAssistant(retriever, llm).reply(Profile.GESTANTE, pergunta("Qual rota é melhor pra mim?"), fatos)
    assert r.source == "llm" and r.routes_cited == [primeira["route_id"]]


def test_cpf_email_e_telefone_nao_chegam_ao_modelo(retriever, fatos):
    llm = FakeLLM({"resposta": "Não preciso dos seus dados para ajudar.", "rotas_citadas": []})
    texto = "Meu email é julia@exemplo.com, CPF 123.456.789-09, tel (11) 91234-5678. Qual rota?"
    ChatAssistant(retriever, llm).reply(Profile.GESTANTE, pergunta(texto), fatos)
    for dado in ("julia@exemplo.com", "123.456.789-09", "91234-5678"):
        assert dado not in llm.last_user


def test_pergunta_fora_do_tema_e_sinalizada(retriever, fatos):
    llm = FakeLLM({"resposta": "Só consigo ajudar com rotas e acessibilidade.", "fora_do_escopo": True})
    r = ChatAssistant(retriever, llm).reply(Profile.GESTANTE, pergunta("Me passa uma receita de bolo"), fatos)
    assert r.out_of_scope


def test_emergencia_manda_ligar_192_sem_chamar_o_modelo(retriever, fatos):
    llm = FakeLLM({"resposta": "Pegue o ônibus.", "rotas_citadas": []})
    for texto in ("estou ganhando o neném", "sim e eu estou grávida ganhando o bebê o que faço",
                  "minha bolsa estourou"):
        r = ChatAssistant(retriever, llm).reply(Profile.GESTANTE, pergunta(texto), fatos)
        assert "192" in r.reply and r.fallback_reason == "emergencia"
    assert llm.calls == 0


def test_modelo_fora_do_ar_devolve_resposta_de_reserva(retriever, fatos):
    llm = FakeLLM(error=LLMError("timeout"))
    r = ChatAssistant(retriever, llm).reply(Profile.GESTANTE, pergunta("O elevador quebrou, o que faço?"), fatos)
    assert r.source == "template_fallback" and r.reply
