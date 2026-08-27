"""El emisor queda congelado en la OC al emitirla.

El membrete del PDF salía de `obtener_perfil_organizacion()`, leído en vivo en
cada generación, y `ordenes_compra` no guardaba nada del emisor. Si la empresa se
renombraba, regenerar el PDF de una OC vieja la mostraba con el nombre de hoy:
el documento dejaba de decir quién la emitió cuando la emitió.

Mismo criterio que `direccion_despacho` (048) y que el número de OC.

Se verifica el diccionario que recibe `generar_pdf_oc`, no los bytes del PDF: el
contenido va comprimido, así que buscar texto ahí sólo encuentra los metadatos
—y un test que pasa por el motivo equivocado es peor que uno que falla.
"""
from unittest.mock import MagicMock, patch

from app.routers.oc import _CAMPOS_EXTRA_OC, _generar_pdf_desde_fila

PERFIL_HOY = {"nombre": "Vital Energía SpA", "rut": "77.999.888-1",
              "direccion": "Nueva Providencia 2000"}

FILA_EMITIDA = {
    "numero_oc": "OC-2026-BVITAL-0008", "created_at": "2026-08-26T15:47:10Z",
    "nombre_item": "Ampolleta LED E27 100W", "proveedor_nombre": "Joaquín González",
    "proveedor_email": "joaquin.gonzalez.pl@usach.cl",
    "cantidad": 1, "precio_unitario": 19990.0, "precio_total": 23788.0, "moneda": "CLP",
    "condiciones_pago": "Transferencia", "plazo_entrega": "48h",
    # Congelado al emitir, cuando la empresa todavía se llamaba "Vital".
    "emisor_nombre": "Vital", "emisor_rut": "76.123.456-7",
    "emisor_direccion": "Av. Providencia 1234",
}


def _datos_del_pdf(fila: dict) -> dict:
    """Lo que `_generar_pdf_desde_fila` le entrega al generador."""
    ctx = MagicMock()
    ctx.organization_id = "org-1"
    with patch("app.services.organizacion.obtener_perfil_organizacion", return_value=PERFIL_HOY), \
         patch("app.services.oc_pdf.generar_pdf_oc", return_value=b"%PDF-") as generador:
        _generar_pdf_desde_fila(fila, ctx)
    return generador.call_args[0][0]


# ─── Lo guardado manda sobre el perfil vigente ───────────────────────────────

def test_usa_el_emisor_congelado_no_el_nombre_actual():
    """La empresa hoy se llama "Vital Energía SpA"; la OC debe decir "Vital"."""
    datos = _datos_del_pdf(FILA_EMITIDA)
    assert datos["emisor_nombre"] == "Vital"
    assert datos["emisor_rut"] == "76.123.456-7"
    assert datos["emisor_direccion"] == "Av. Providencia 1234"


def test_el_numero_y_el_emisor_quedan_del_mismo_momento():
    """Serie y membrete tienen que contar la misma historia."""
    datos = _datos_del_pdf(FILA_EMITIDA)
    assert datos["numero_oc"] == "OC-2026-BVITAL-0008"
    assert datos["emisor_nombre"] == "Vital"


# ─── Compatibilidad con las OC previas a la 050 ──────────────────────────────

def test_una_oc_vieja_cae_al_perfil_vigente():
    """Sin backfill: las OC previas no registran el emisor de entonces, así que
    conservan exactamente el comportamiento que ya tenían."""
    vieja = {k: v for k, v in FILA_EMITIDA.items() if not k.startswith("emisor_")}
    assert _datos_del_pdf(vieja)["emisor_nombre"] == "Vital Energía SpA"


def test_un_emisor_vacio_no_deja_el_pdf_sin_membrete():
    vacia = {**FILA_EMITIDA, "emisor_nombre": None, "emisor_rut": None,
             "emisor_direccion": None}
    datos = _datos_del_pdf(vacia)
    assert datos["emisor_nombre"] == "Vital Energía SpA"
    assert datos["emisor_rut"] == "77.999.888-1"


def test_campos_congelados_parciales_se_completan_uno_a_uno():
    """Una OC puede tener nombre guardado y RUT no (columna agregada después)."""
    parcial = {**FILA_EMITIDA, "emisor_rut": None}
    datos = _datos_del_pdf(parcial)
    assert datos["emisor_nombre"] == "Vital"
    assert datos["emisor_rut"] == "77.999.888-1"


# ─── El fallback de columnas ausentes las contempla ──────────────────────────

def test_las_columnas_nuevas_estan_en_el_fallback():
    """Si la 050 no está aplicada, el insert las omite en vez de fallar entero."""
    for columna in ("emisor_nombre", "emisor_rut", "emisor_direccion"):
        assert columna in _CAMPOS_EXTRA_OC
