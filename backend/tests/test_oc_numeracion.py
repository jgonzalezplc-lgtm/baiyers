"""Numeración de OC por empresa: OC-2026-BVITAL-0007.

Antes era `OC-{año}-{len(filas)+1:04d}`. Tres bugs verificados en producción:
contaba filas en vez del máximo (borrar una OC reutilizaba su número), no
filtraba por organización (faltan la 0001 y la 0006 en los datos reales, las
consumió otra empresa) y no había unicidad garantizada.

El código de empresa cumple además un requisito del negocio: Baiyer se integra a
empresas que ya emiten sus propias OC, y `OC-2026-0007` de Baiyer podría
confundirse con el `OC-2026-0007` del ERP del cliente.
"""
import pytest

from app.services.oc_numeracion import (
    LARGO_TOKEN, derivar_token, desambiguar, formatear, prefijo, siguiente_correlativo,
)


# ─── Token de empresa ────────────────────────────────────────────────────────

@pytest.mark.parametrize("nombre,esperado", [
    ("Vital", "VITAL"),
    ("Vital SpA", "VITAL"),
    ("Vital Ltda", "VITAL"),
    ("Vital S.A.", "VITAL"),
    ("Constructora Andes EIRL", "CONSTRU"),
    ("Claria", "CLARIA"),
])
def test_deriva_token_legible(nombre, esperado):
    assert derivar_token(nombre) == esperado


def test_quita_acentos_y_puntuacion():
    """El número va en un PDF y en el asunto de un correo: sólo A-Z0-9."""
    token = derivar_token("Añón & Cía.")
    assert token.isalnum() and token.isupper()
    assert token.startswith("ANON")


def test_respeta_el_largo_maximo():
    assert len(derivar_token("Compañía Manufacturera Metalúrgica Nacional")) == LARGO_TOKEN


@pytest.mark.parametrize("nombre", [None, "", "   ", "!!!", "···"])
def test_nombre_inutil_cae_a_un_fallback(nombre):
    """Sin código, el número deja de cumplir su propósito de marcar origen."""
    assert derivar_token(nombre) == "EMPRESA"


def test_nombre_que_es_solo_forma_societaria():
    """Sacar el sufijo dejaría el token vacío: se prefiere conservarlo."""
    assert derivar_token("SpA") == "SPA"


# ─── Desambiguación entre empresas ───────────────────────────────────────────

def test_agrega_el_prefijo_de_origen():
    assert desambiguar("VITAL", set()) == "BVITAL"


def test_dos_empresas_con_el_mismo_token_no_chocan():
    """'Vital SpA' y 'Vital Ltda' derivan el mismo token."""
    assert desambiguar("VITAL", {"BVITAL"}) == "BVITAL2"
    assert desambiguar("VITAL", {"BVITAL", "BVITAL2"}) == "BVITAL3"


def test_el_sufijo_no_desborda_el_largo():
    largo = "ABCDEFG"  # ya usa los 7 caracteres
    codigo = desambiguar(largo, {f"B{largo}"})
    assert len(codigo) <= 1 + LARGO_TOKEN
    assert codigo.endswith("2")


# ─── Correlativo ─────────────────────────────────────────────────────────────

def test_toma_el_maximo_no_la_cantidad():
    """El bug original: con 3 filas y máximo 0007, daba 0004 y repetía números."""
    numeros = ["OC-2026-BVITAL-0002", "OC-2026-BVITAL-0005", "OC-2026-BVITAL-0007"]
    assert siguiente_correlativo(numeros, 2026, "BVITAL") == 8


def test_borrar_una_oc_no_reutiliza_su_numero():
    """Se emitió la 0007 y se borró: la siguiente NO puede ser 0007 otra vez."""
    assert siguiente_correlativo(["OC-2026-BVITAL-0007"], 2026, "BVITAL") == 8


def test_ignora_las_ocs_de_otra_empresa():
    """La causa de que faltaran la 0001 y la 0006."""
    numeros = ["OC-2026-BOTRA-0009", "OC-2026-BOTRA-0010", "OC-2026-BVITAL-0002"]
    assert siguiente_correlativo(numeros, 2026, "BVITAL") == 3


def test_ignora_otro_anio():
    numeros = ["OC-2025-BVITAL-0099", "OC-2026-BVITAL-0001"]
    assert siguiente_correlativo(numeros, 2026, "BVITAL") == 2


def test_ignora_los_numeros_legado_sin_codigo():
    """`OC-2026-0007` es del formato viejo: no participa de la serie nueva."""
    assert siguiente_correlativo(["OC-2026-0007", "OC-2026-0005"], 2026, "BVITAL") == 1


def test_primera_oc_de_la_empresa():
    assert siguiente_correlativo([], 2026, "BVITAL") == 1
    assert siguiente_correlativo(None, 2026, "BVITAL") == 1


def test_tolera_valores_nulos_o_rotos():
    numeros = [None, "", "cualquier cosa", "OC-2026-BVITAL-0003"]
    assert siguiente_correlativo(numeros, 2026, "BVITAL") == 4


def test_un_prefijo_no_matchea_a_otro_mas_largo():
    """'BVITAL' no debe contar las OCs de 'BVITAL2'."""
    numeros = ["OC-2026-BVITAL2-0050"]
    assert siguiente_correlativo(numeros, 2026, "BVITAL") == 1


# ─── Formato final ───────────────────────────────────────────────────────────

def test_formato_completo():
    assert formatear(2026, "BVITAL", 7) == "OC-2026-BVITAL-0007"


def test_prefijo_es_el_usado_para_filtrar():
    assert prefijo(2026, "BVITAL") == "OC-2026-BVITAL"
    assert formatear(2026, "BVITAL", 7).startswith(prefijo(2026, "BVITAL") + "-")


def test_pasa_de_cuatro_digitos_sin_romperse():
    assert formatear(2026, "BVITAL", 12345) == "OC-2026-BVITAL-12345"


def test_coincide_con_el_regex_del_indice_unico():
    """El índice parcial de la 047 sólo cubre este formato."""
    import re
    patron = re.compile(r"^OC-[0-9]{4}-B[A-Z0-9]+-[0-9]+$")
    assert patron.match(formatear(2026, desambiguar(derivar_token("Vital SpA"), set()), 7))
    assert not patron.match("OC-2026-0007")  # legado, fuera del índice
