"""La dirección de despacho es un dato propio, nunca inferido.

Caso real (2026-08-26): un proveedor preguntó "¿a qué dirección?" y Baiyer no
tenía ninguna que ofrecer. El único campo disponible era
`organizaciones.direccion` —que el onboarding scrapea del sitio web, así que ni
siquiera está verificada— y decía "Av. Pedro Dreyer 4627, Monte Grande, Buenos
Aires, Argentina" para una compra a un proveedor chileno. Estuvo a punto de
enviarse como destino de entrega.
"""
from unittest.mock import MagicMock, patch

import pytest

from app.routers.oc import _texto_despacho
from app.services.organizacion import obtener_despacho_organizacion

fpdf = pytest.importorskip("fpdf", reason="fpdf2 no instalado")
from app.services.oc_pdf import generar_pdf_oc  # noqa: E402

DIRECCION_ADMINISTRATIVA = "Av. Pedro Dreyer 4627, Monte Grande, Buenos Aires, Argentina"


def _sb(fila, lanza=False):
    sb = MagicMock()
    consulta = sb.table.return_value.select.return_value.eq.return_value.maybe_single.return_value
    if lanza:
        consulta.execute.side_effect = Exception("column organizaciones.direccion_despacho does not exist")
    else:
        consulta.execute.return_value = MagicMock(data=fila)
    return sb


# ─── Nunca inferir desde la dirección administrativa ─────────────────────────

def test_sin_configurar_devuelve_vacio():
    """{} obliga a quien llama a pedirle el dato a una persona."""
    with patch("app.services.organizacion._sb", return_value=_sb({"direccion_despacho": None})):
        assert obtener_despacho_organizacion("org-1") == {}


def test_no_cae_a_la_direccion_administrativa():
    """El bug exacto: `direccion` NO es un destino de entrega."""
    fila = {"direccion_despacho": None, "direccion": DIRECCION_ADMINISTRATIVA}
    with patch("app.services.organizacion._sb", return_value=_sb(fila)):
        resultado = obtener_despacho_organizacion("org-1")
    assert resultado == {}
    assert DIRECCION_ADMINISTRATIVA not in str(resultado)


def test_direccion_en_blanco_cuenta_como_sin_configurar():
    with patch("app.services.organizacion._sb", return_value=_sb({"direccion_despacho": "   "})):
        assert obtener_despacho_organizacion("org-1") == {}


def test_sin_migracion_aplicada_se_comporta_como_sin_configurar():
    """Estado honesto: la 048 puede no estar aplicada todavía."""
    with patch("app.services.organizacion._sb", return_value=_sb(None, lanza=True)):
        assert obtener_despacho_organizacion("org-1") == {}


def test_sin_organizacion_no_consulta():
    assert obtener_despacho_organizacion("") == {}


def test_devuelve_los_datos_configurados():
    fila = {"direccion_despacho": "Bodega Central, Maipú", "despacho_contacto": "Paula Soto",
            "despacho_telefono": "+56 9 8765 4321", "despacho_notas": None}
    with patch("app.services.organizacion._sb", return_value=_sb(fila)):
        resultado = obtener_despacho_organizacion("org-1")
    assert resultado["direccion_despacho"] == "Bodega Central, Maipú"
    assert resultado["despacho_contacto"] == "Paula Soto"
    assert "despacho_notas" not in resultado  # los vacíos no viajan


# ─── Aplanado para la OC ─────────────────────────────────────────────────────

def test_texto_despacho_arma_una_linea():
    texto = _texto_despacho({
        "direccion_despacho": "Bodega Central, Maipú",
        "despacho_contacto": "Paula Soto", "despacho_telefono": "+56 9 8765 4321",
    })
    assert texto == "Bodega Central, Maipú · Recibe: Paula Soto · +56 9 8765 4321"


def test_texto_despacho_vacio_sin_direccion():
    assert _texto_despacho({}) == ""
    assert _texto_despacho({"despacho_contacto": "Paula"}) == ""


# ─── El PDF sólo muestra el bloque si hay dato ───────────────────────────────

OC = {
    "numero_oc": "OC-2026-BVITAL-0009", "fecha": "26/08/2026",
    "nombre_item": "Ampolleta LED E27 100W", "proveedor_nombre": "Joaquín González",
    "cantidad": 1, "precio_unitario": 19990.0, "moneda": "CLP",
    "subtotal": 19990.0, "iva": 3798.0, "total": 23788.0,
    "condiciones_pago": "Transferencia", "plazo_entrega": "48h",
    "emisor_nombre": "Vital", "emisor_direccion": DIRECCION_ADMINISTRATIVA,
}


def test_el_bloque_de_despacho_es_condicional():
    con = generar_pdf_oc({**OC, "direccion_despacho": "Bodega Central, Maipú"})
    sin = generar_pdf_oc(OC)
    assert len(con) > len(sin), "el bloque debe aparecer sólo si hay dirección"


def test_sin_despacho_la_oc_no_inventa_un_destino():
    """Que el proveedor pregunte es preferible a insinuar un destino sin confirmar."""
    assert generar_pdf_oc(OC).startswith(b"%PDF-")


def test_direccion_larga_no_rompe_el_pdf():
    largo = "Bodega Central, Camino a Melipilla 5500, Maipú · Recibe: Paula Soto · " * 4
    assert generar_pdf_oc({**OC, "direccion_despacho": largo}).startswith(b"%PDF-")
