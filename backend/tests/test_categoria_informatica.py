"""Un notebook no es un producto industrial.

Caso real (2026-08-27): al pedir 10 computadores para programadores, los tres
ítems quedaron con `categoria: "industrial"` — la única que el modelo encontraba
medianamente aplicable, porque no existía ninguna para informática. Y `industrial`
rutea a TODAS las fuentes especializadas, así que Baiyer le preguntó a Mouser y a
Sodimac por un MacBook y devolvió cables y herramientas. El comparador terminó en $0.

La corrección no es "clasificar mejor": es que exista la categoría, y que cuando
Baiyer no tiene fuentes especializadas para un rubro consulte SÓLO las genéricas
en vez de todas las industriales.
"""
import pytest

from app.services.categoria_mapper import (
    CATEGORIA_FUENTES, TODAS_ESPECIFICAS, fuentes_para_categoria,
)


def test_informatica_existe_como_categoria():
    assert "informatica" in CATEGORIA_FUENTES


def test_informatica_no_consulta_fuentes_industriales():
    """Mouser vende resistencias, Sodimac cemento. Ninguno vende notebooks."""
    assert fuentes_para_categoria("informatica") == set()


@pytest.mark.parametrize("fuente", ["mouser", "digikey", "sodimac", "dartel", "clcsa"])
def test_ninguna_fuente_especializada_recibe_una_busqueda_de_notebooks(fuente):
    assert fuente not in fuentes_para_categoria("informatica")


def test_sigue_el_patron_de_insumos_medicos():
    """Ya existía el caso "sin fuentes especializadas": no se inventa uno nuevo."""
    assert fuentes_para_categoria("informatica") == fuentes_para_categoria("insumos_medicos")


# ─── No romper lo que ya funcionaba ──────────────────────────────────────────

@pytest.mark.parametrize("categoria,fuente_esperada", [
    ("carpinteria", "clcsa"),
    ("construccion", "sodimac"),
    ("electrico", "dartel"),
    ("electronica", "mouser"),
])
def test_las_categorias_existentes_conservan_sus_fuentes(categoria, fuente_esperada):
    assert fuente_esperada in fuentes_para_categoria(categoria)


def test_industrial_sigue_consultando_todo():
    """Maquinaria e insumos de planta sí justifican el barrido completo."""
    assert fuentes_para_categoria("industrial") == TODAS_ESPECIFICAS


def test_una_categoria_desconocida_conserva_el_comportamiento_v1():
    assert fuentes_para_categoria("no_existe") == TODAS_ESPECIFICAS
    assert fuentes_para_categoria(None) == TODAS_ESPECIFICAS


# ─── El prompt tiene que ofrecerla ───────────────────────────────────────────

def test_el_prompt_de_identificacion_incluye_informatica():
    """La categoría sin la opción en el prompt es letra muerta: el modelo no
    puede elegir algo que no se le ofrece."""
    from pathlib import Path

    fuente = Path("app/routers/identificar.py").read_text()
    assert fuente.count("informatica") >= 3, "falta en algún prompt o en la guía"


def test_el_prompt_desaconseja_industrial_como_cajon_de_sastre():
    """Era el default del modelo ante cualquier cosa que no encajara."""
    from pathlib import Path

    fuente = Path("app/routers/identificar.py").read_text()
    assert "cajón de sastre" in fuente


# ─── Ampliar no puede significar "preguntale a todos" ────────────────────────
# Caso real (2026-08-27): con la categoría ya bien asignada (`informatica`), la
# búsqueda AMPLIADA la descartaba y consultaba las 16 fuentes industriales.
# Devolvió 24 resultados: interruptores, cámaras y material eléctrico.

from app.routers.buscar import BuscarRequest, _fuentes_de_request  # noqa: E402


def _fuentes(categoria, *, ampliada):
    return _fuentes_de_request(BuscarRequest(
        descripcion="x", cotizacion_id="c1", categoria=categoria,
        busqueda_expandida=ampliada,
    ))


@pytest.mark.parametrize("categoria", ["informatica", "insumos_medicos"])
def test_ampliar_no_agrega_ruido_industrial(categoria):
    """Sin fuentes especializadas para el rubro, sumar las 16 industriales no
    aporta un solo resultado relevante."""
    assert _fuentes(categoria, ampliada=True) == set()


def test_ampliar_si_abre_el_abanico_en_una_categoria_con_fuentes():
    """Ése es el propósito de ampliar y no se rompe."""
    normal = _fuentes("construccion", ampliada=False)
    ampliada = _fuentes("construccion", ampliada=True)
    assert normal < ampliada
    assert "dartel" in ampliada and "dartel" not in normal


def test_sin_categoria_ampliar_consulta_todo():
    assert _fuentes(None, ampliada=True) == TODAS_ESPECIFICAS
