import json
from pathlib import Path

from app.adapters.directions import routes_from_directions

SAMPLE = json.loads((Path(__file__).parent / "fixtures" / "directions_sample.json").read_text(encoding="utf-8"))


def test_converte_rotas_e_casa_estacoes_pelo_nome(catalog):
    routes = routes_from_directions(SAMPLE, catalog)
    assert len(routes) == 2
    metro = routes[0].legs[1]
    assert (metro.mode, metro.from_place, metro.to_place) == ("SUBWAY", "station:santa-cecilia", "station:se")
    assert routes[0].duration_min == 22


def test_parada_sem_correspondencia_fica_marcada_como_desconhecida(catalog):
    bus = routes_from_directions(SAMPLE, catalog)[1].legs[1]
    assert bus.from_place == "desconhecido:Parada Inexistente no Catálogo" and bus.to_place == "stop:ubs-centro"


def test_status_de_erro_ou_vazio_retorna_lista_vazia(catalog):
    assert routes_from_directions({"status": "ZERO_RESULTS", "routes": []}, catalog) == []
    assert routes_from_directions({}, catalog) == []
