from app.models import Profile


def test_pergunta_sobre_elevador_encontra_o_trecho_de_elevador(retriever):
    hits = retriever.search("o elevador da estação está quebrado, o que eu faço?", Profile.CADEIRANTE, k=2)
    assert hits and hits[0].chunk.id == "kb-elevador-fora"


def test_pergunta_fora_do_tema_nao_encontra_nada(retriever):
    assert retriever.search("qual a cotação do dólar hoje?", Profile.GESTANTE) == []
