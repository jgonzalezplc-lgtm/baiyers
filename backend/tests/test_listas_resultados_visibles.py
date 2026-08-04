from app.routers.listas import _resultados_visibles


RESULTADOS = [
    {"resultado_id": "privado", "fuente": "manual"},
    {"resultado_id": "google", "fuente": "google"},
    {"resultado_id": "mercadolibre", "fuente": "mercadolibre"},
]


def test_sin_busqueda_confirmada_solo_muestra_proveedores_directos():
    assert _resultados_visibles({"comparado": False}, RESULTADOS) == [RESULTADOS[0]]


def test_busqueda_confirmada_muestra_todos_los_resultados():
    assert _resultados_visibles({"comparado": True}, RESULTADOS) == RESULTADOS
