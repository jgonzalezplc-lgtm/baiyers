"""Una fuente caída no puede verse igual que una fuente sin resultados.

Caso real (2026-08-27): MercadoLibre devolvía HTTP 403 y Serper "Not enough
credits" desde hacía días. Cada fuente atrapaba su excepción y devolvía lista
vacía, así que la búsqueda respondía cero en silencio.

El costo fue un día entero de diagnósticos equivocados: se culpó a la categoría
del ítem, después al ruteo de la búsqueda ampliada, y recién al probar las APIs a
mano apareció que las dos fuentes generales estaban muertas.
"""
import pytest

from app.routers.buscar import FuenteCaida, _diagnosticar


def test_una_fuente_con_resultados_queda_ok():
    d = _diagnosticar(["mercadolibre"], [[{"titulo": "Monitor"}]])
    assert d["por_fuente"]["mercadolibre"] == {"estado": "ok", "n": 1}
    assert d["con_resultados"] == 1
    assert "aviso" not in d


def test_una_fuente_caida_reporta_el_motivo():
    """El 403 real de MercadoLibre."""
    error = FuenteCaida('MercadoLibre HTTP 403: {"message":"forbidden"}')
    d = _diagnosticar(["mercadolibre"], [error])
    assert d["por_fuente"]["mercadolibre"]["estado"] == "error"
    assert "403" in d["por_fuente"]["mercadolibre"]["detalle"]
    assert d["caidas"] == ["mercadolibre"]


def test_distingue_caida_de_vacia():
    """Las dos daban cero; ahora se pueden separar."""
    d = _diagnosticar(
        ["mercadolibre", "sodimac"],
        [FuenteCaida("HTTP 403"), []],
    )
    assert d["por_fuente"]["mercadolibre"]["estado"] == "error"
    assert d["por_fuente"]["sodimac"]["estado"] == "sin_resultados"


def test_el_aviso_nombra_las_fuentes_caidas():
    d = _diagnosticar(
        ["mercadolibre", "google_cl_precio"],
        [FuenteCaida("HTTP 403"), FuenteCaida("Not enough credits")],
    )
    assert "mercadolibre" in d["aviso"]
    assert "google_cl_precio" in d["aviso"]


def test_todo_vacio_sin_errores_dice_otra_cosa():
    """Sin caídas, cero puede significar que el término no existe en esas fuentes."""
    d = _diagnosticar(["sodimac", "easy"], [[], []])
    assert "falló" not in d["aviso"]
    assert "vacío" in d["aviso"]


def test_con_al_menos_un_resultado_no_hay_aviso():
    """Si el camino feliz avisa, se aprende a ignorar los avisos."""
    d = _diagnosticar(["mercadolibre", "sodimac"], [[{"x": 1}], FuenteCaida("HTTP 500")])
    assert "aviso" not in d
    assert d["caidas"] == ["sodimac"], "la caída se registra igual"


def test_cuenta_las_fuentes_consultadas():
    d = _diagnosticar(["a", "b", "c"], [[], [], []])
    assert d["consultadas"] == 3


def test_una_respuesta_rara_no_rompe_el_diagnostico():
    d = _diagnosticar(["rara"], ["no soy una lista"])
    assert d["por_fuente"]["rara"]["estado"] == "respuesta_inesperada"


def test_el_detalle_se_trunca():
    """Un HTML de error de 200 KB no puede viajar en la respuesta."""
    d = _diagnosticar(["x"], [FuenteCaida("z" * 5000)])
    assert len(d["por_fuente"]["x"]["detalle"]) <= 160


# ─── La excepción se propaga a propósito ─────────────────────────────────────

def test_fuente_caida_es_una_excepcion():
    """Los llamadores usan gather(return_exceptions=True) y filtran por
    isinstance(list): el comportamiento degradado se conserva."""
    assert issubclass(FuenteCaida, Exception)


@pytest.mark.parametrize("resultado", [None, 0, {}, ""])
def test_solo_las_listas_cuentan_como_resultados(resultado):
    d = _diagnosticar(["x"], [resultado])
    assert d["con_resultados"] == 0
