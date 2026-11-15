from app.models import Profile


def test_recupera_trecho_de_elevador(retriever):
    hits = retriever.search("o elevador da estação está quebrado, o que eu faço?", Profile.CADEIRANTE, k=2)
    assert hits and hits[0].chunk.id == "kb-elevador-fora"


def test_tolera_erro_de_digitacao(retriever):
    hits = retriever.search("calsada esburacada com buraco", Profile.IDOSO, k=1)
    assert hits and hits[0].chunk.id == "kb-calcada-ruim"


def test_pergunta_fora_do_dominio_retorna_vazio(retriever):
    assert retriever.search("qual a cotação do dólar hoje?", Profile.GESTANTE) == []
    assert retriever.search("   ", Profile.GESTANTE) == []
