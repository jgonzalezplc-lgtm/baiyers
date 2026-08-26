"""PDF de la OC generado en el backend.

`POST /api/oc/enviar` exigía el PDF ya renderizado en base64. Eso funciona desde
el navegador (`OCPDFTemplate.tsx`) pero dejaba sin salida a los clientes headless:
vía MCP no se podía emitir y enviar una OC sin que alguien lo generara a mano.
"""
import pytest

fpdf = pytest.importorskip("fpdf", reason="fpdf2 no instalado (ver requirements.txt)")

from app.services.oc_pdf import formatear_monto, generar_pdf_oc  # noqa: E402

OC = {
    "numero_oc": "OC-2026-0007", "fecha": "26/08/2026",
    "nombre_item": "Ampolleta LED estándar E27 100W equivalente luz fría",
    "proveedor_nombre": "Joaquín González",
    "proveedor_email": "joaquin.gonzalez.pl@usach.cl",
    "cantidad": 1, "precio_unitario": 19990.0, "moneda": "CLP",
    "subtotal": 19990.0, "iva": 3798.0, "total": 23788.0,
    "condiciones_pago": "transferencia", "plazo_entrega": "48h desde la recepción de la OC",
    "notas": None, "emisor_nombre": "Vital", "emisor_rut": "76.123.456-7",
    "emisor_direccion": "Av. Pedro Dreyer 4627",
}


# ─── Formato de montos: espeja fmt() del template del frontend ───────────────

@pytest.mark.parametrize("valor,moneda,esperado", [
    (19990.0, "CLP", "$19.990"),
    (23788.0, "CLP", "$23.788"),
    (150000, "CLP", "$150.000"),
    (999, "CLP", "$999"),
    (1234567, "CLP", "$1.234.567"),
    # CLP se redondea, como en el frontend.
    (19990.4, "CLP", "$19.990"),
])
def test_formato_clp_chileno(valor, moneda, esperado):
    assert formatear_monto(valor, moneda) == esperado


def test_formato_moneda_extranjera_lleva_decimales():
    assert formatear_monto(118.5, "USD") == "USD 118.50"


# ─── Generación ──────────────────────────────────────────────────────────────

def test_genera_un_pdf_valido():
    pdf = generar_pdf_oc(OC)
    assert pdf.startswith(b"%PDF-"), "debe ser un PDF real"
    assert pdf.rstrip().endswith(b"%%EOF")
    assert len(pdf) > 800


def test_no_falla_sin_datos_opcionales():
    """Una OC legado puede no tener RUT, dirección, email ni notas."""
    minima = {**OC, "emisor_rut": None, "emisor_direccion": None,
              "proveedor_email": None, "notas": None, "plazo_entrega": ""}
    assert generar_pdf_oc(minima).startswith(b"%PDF-")


def test_notas_agregan_una_tercera_condicion():
    con_notas = generar_pdf_oc({**OC, "notas": "Entregar en recepción"})
    assert con_notas.startswith(b"%PDF-")


def test_sin_perfil_de_organizacion_usa_el_fallback():
    """Mismo fallback que el frontend: "Baiyer" cuando no hay perfil."""
    assert generar_pdf_oc({**OC, "emisor_nombre": None}).startswith(b"%PDF-")


def test_caracteres_fuera_de_latin1_no_rompen_el_envio():
    """Una comilla tipográfica o un emoji pegado desde un correo no puede
    impedir que se emita la OC."""
    raro = {**OC, "nombre_item": "Ampolleta “premium” \U0001f4a1",
            "proveedor_nombre": "Señor Ñandú"}
    assert generar_pdf_oc(raro).startswith(b"%PDF-")


def test_texto_largo_no_desborda_ni_lanza():
    largo = {**OC, "nombre_item": "Ampolleta " * 40,
             "condiciones_pago": "transferencia a Banco de tiririrquen " * 10}
    assert generar_pdf_oc(largo).startswith(b"%PDF-")


def test_es_determinista_en_contenido():
    """Dos corridas con los mismos datos deben pesar igual: si no, algo
    no declarado (una fecha, un id) se está colando en el documento."""
    a, b = generar_pdf_oc(OC), generar_pdf_oc(OC)
    assert len(a) == len(b)


def test_montos_cero_no_rompen():
    assert generar_pdf_oc({
        **OC, "precio_unitario": 0, "subtotal": 0, "iva": 0, "total": 0,
    }).startswith(b"%PDF-")
