"""Generación del PDF de una Orden de Compra en el backend.

Existe porque `POST /api/oc/enviar` exigía que el cliente entregara el PDF ya
renderizado en base64. Eso funciona desde el navegador —el frontend lo arma con
`OCPDFTemplate.tsx`— pero deja sin salida a cualquier cliente headless: vía MCP
no había forma de emitir y enviar una OC sin que alguien generara el PDF a mano.

**Deuda que este archivo crea, a conciencia:** ahora hay DOS plantillas del mismo
documento, ésta y `frontend/components/OCPDFTemplate.tsx`. Van a divergir salvo
que se toquen juntas. Se replican acá el orden de las secciones, los rótulos y el
formato de montos; si cambiás una, cambiá la otra. La alternativa (que el backend
llamara a un render del frontend) acoplaba el envío de una OC a un salto de red
que puede fallar justo en el peor momento.

fpdf2 se eligió por ser Python puro: no necesita binarios de sistema, así que no
cambia nada del build de Railway.
"""
from typing import Any, Optional

# Paleta y medidas espejadas de OCPDFTemplate.tsx.
_INDIGO = (99, 102, 241)
_TINTA = (30, 41, 59)
_GRIS = (100, 116, 139)
_GRIS_CLARO = (148, 163, 184)
_FONDO_CAJA = (248, 250, 252)
_LINEA = (226, 232, 240)

_MARGEN = 18  # mm; equivale al padding 48pt del template del frontend


def formatear_monto(valor: float, moneda: str) -> str:
    """Espeja `fmt()` de OCPDFTemplate.tsx.

    CLP se redondea y usa punto como separador de miles (formato chileno); el
    resto va con dos decimales y coma. Se hace a mano porque `locale` depende de
    que el locale exista en el contenedor, y en Railway no está garantizado.
    """
    if moneda == "CLP":
        return "$" + f"{round(valor):,}".replace(",", ".")
    entero, _, decimal = f"{valor:,.2f}".partition(".")
    return f"{moneda} {entero}.{decimal}"


def _texto(texto: Optional[str]) -> str:
    """fpdf2 con fuentes core usa latin-1: un carácter fuera de ese rango
    (una comilla tipográfica pegada desde un correo, un emoji) haría fallar la
    generación entera. Un PDF con un carácter sustituido es infinitamente mejor
    que no poder enviar la OC."""
    return (texto or "").encode("latin-1", "replace").decode("latin-1")


def generar_pdf_oc(oc: dict[str, Any]) -> bytes:
    """Devuelve los bytes del PDF. Acepta el mismo diccionario que ya devuelve
    `POST /api/oc/crear`, para no inventar un segundo contrato de datos."""
    from fpdf import FPDF

    emisor = oc.get("emisor_nombre") or "Baiyer"
    moneda = oc.get("moneda") or "CLP"
    numero = oc.get("numero_oc") or ""
    fecha = oc.get("fecha") or ""

    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.set_margins(_MARGEN, _MARGEN, _MARGEN)
    pdf.add_page()
    pdf.set_title(f"OC {numero}")
    pdf.set_author(emisor)
    ancho = pdf.w - 2 * _MARGEN

    # ── Encabezado ───────────────────────────────────────────────────────────
    y0 = pdf.get_y()
    pdf.set_font("Helvetica", "B", 18)
    pdf.set_text_color(*_INDIGO)
    pdf.cell(ancho / 2, 9, _texto(emisor))
    pdf.set_xy(_MARGEN + ancho / 2, y0)
    pdf.set_font("Helvetica", "B", 16)
    pdf.set_text_color(*_TINTA)
    pdf.cell(ancho / 2, 9, _texto(numero), align="R")

    pdf.ln(9)
    pdf.set_font("Helvetica", "", 8)
    pdf.set_text_color(*_GRIS)
    y1 = pdf.get_y()
    pdf.cell(ancho / 2, 5, "ORDEN DE COMPRA")
    pdf.set_xy(_MARGEN + ancho / 2, y1)
    pdf.cell(ancho / 2, 5, _texto(f"Fecha: {fecha}"), align="R")

    pdf.ln(7)
    pdf.set_draw_color(*_INDIGO)
    pdf.set_line_width(0.6)
    pdf.line(_MARGEN, pdf.get_y(), _MARGEN + ancho, pdf.get_y())
    pdf.ln(6)

    # ── Emisor / Proveedor ───────────────────────────────────────────────────
    _cajas_partes(pdf, ancho, emisor, oc)

    # ── Ítem ─────────────────────────────────────────────────────────────────
    subtotal = float(oc.get("subtotal") or 0)
    _tabla_item(pdf, ancho, oc, moneda, subtotal)

    # ── Totales ──────────────────────────────────────────────────────────────
    _totales(pdf, ancho, oc, moneda, subtotal)

    # ── Condiciones ──────────────────────────────────────────────────────────
    _condiciones(pdf, ancho, oc)

    # ── Despacho ─────────────────────────────────────────────────────────────
    # Sólo si está configurada. Si no, la OC no dice nada de despacho y el
    # proveedor pregunta — que es lo correcto cuando nadie confirmó un destino.
    _despacho(pdf, ancho, oc)

    # ── Pie ──────────────────────────────────────────────────────────────────
    pdf.set_y(-18)
    pdf.set_draw_color(*_LINEA)
    pdf.set_line_width(0.2)
    pdf.line(_MARGEN, pdf.get_y(), _MARGEN + ancho, pdf.get_y())
    pdf.ln(2)
    pdf.set_font("Helvetica", "", 7)
    pdf.set_text_color(*_GRIS_CLARO)
    yf = pdf.get_y()
    pdf.cell(ancho / 2, 4, _texto(
        f"{emisor} - generado via Baiyer" if oc.get("emisor_nombre") else "Generado por Baiyer"
    ))
    pdf.set_xy(_MARGEN + ancho / 2, yf)
    pdf.cell(ancho / 2, 4, _texto(f"{numero} - {fecha}"), align="R")

    return bytes(pdf.output())


def _cajas_partes(pdf, ancho: float, emisor: str, oc: dict) -> None:
    ancho_caja = (ancho - 6) / 2
    izquierda: list[str] = []
    if oc.get("emisor_rut"):
        izquierda.append(f"RUT: {oc['emisor_rut']}")
    if oc.get("emisor_direccion"):
        izquierda.append(str(oc["emisor_direccion"]))
    derecha = [str(oc["proveedor_email"])] if oc.get("proveedor_email") else []

    alto = 12 + 4 * max(len(izquierda), len(derecha), 1)
    y = pdf.get_y()
    pdf.set_fill_color(*_FONDO_CAJA)
    pdf.rect(_MARGEN, y, ancho_caja, alto, style="F")
    pdf.rect(_MARGEN + ancho_caja + 6, y, ancho_caja, alto, style="F")

    for x, titulo, nombre, detalles in (
        (_MARGEN, "EMISOR", emisor, izquierda),
        (_MARGEN + ancho_caja + 6, "PROVEEDOR", oc.get("proveedor_nombre") or "", derecha),
    ):
        pdf.set_xy(x + 3, y + 3)
        pdf.set_font("Helvetica", "B", 7)
        pdf.set_text_color(*_INDIGO)
        pdf.cell(ancho_caja - 6, 4, titulo)
        pdf.set_xy(x + 3, y + 7)
        pdf.set_font("Helvetica", "B", 10)
        pdf.set_text_color(*_TINTA)
        pdf.cell(ancho_caja - 6, 5, _texto(nombre))
        pdf.set_font("Helvetica", "", 8)
        pdf.set_text_color(*_GRIS)
        for i, linea in enumerate(detalles):
            pdf.set_xy(x + 3, y + 12 + i * 4)
            pdf.cell(ancho_caja - 6, 4, _texto(linea))

    pdf.set_y(y + alto + 8)


def _tabla_item(pdf, ancho: float, oc: dict, moneda: str, subtotal: float) -> None:
    cols = (ancho * 0.45, ancho * 0.13, ancho * 0.21, ancho * 0.21)
    pdf.set_fill_color(*_INDIGO)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Helvetica", "B", 8)
    for texto, w, align in zip(
        ("DESCRIPCIÓN", "CANT.", "PRECIO UNIT.", "TOTAL"), cols, ("L", "C", "R", "R")
    ):
        pdf.cell(w, 7, _texto(texto), align=align, fill=True)
    pdf.ln(7)

    pdf.set_fill_color(*_FONDO_CAJA)
    pdf.set_text_color(*_TINTA)
    pdf.set_font("Helvetica", "", 9)
    cantidad = oc.get("cantidad")
    valores = (
        _texto(oc.get("nombre_item") or ""),
        f"{cantidad:g}" if isinstance(cantidad, (int, float)) else "",
        formatear_monto(float(oc.get("precio_unitario") or 0), moneda),
        formatear_monto(subtotal, moneda),
    )
    for texto, w, align in zip(valores, cols, ("L", "C", "R", "R")):
        pdf.cell(w, 8, texto, align=align, fill=True)
    pdf.ln(12)


def _totales(pdf, ancho: float, oc: dict, moneda: str, subtotal: float) -> None:
    w_label, w_valor = 40.0, 32.0
    x = _MARGEN + ancho - (w_label + w_valor)

    for etiqueta, valor in (("Subtotal", subtotal), ("IVA (19%)", float(oc.get("iva") or 0))):
        pdf.set_x(x)
        pdf.set_font("Helvetica", "", 8)
        pdf.set_text_color(*_GRIS)
        pdf.cell(w_label, 5, etiqueta, align="R")
        pdf.set_text_color(*_TINTA)
        pdf.cell(w_valor, 5, formatear_monto(valor, moneda), align="R")
        pdf.ln(5)

    pdf.set_draw_color(*_LINEA)
    pdf.set_line_width(0.2)
    pdf.line(x, pdf.get_y() + 1, _MARGEN + ancho, pdf.get_y() + 1)
    pdf.ln(3)

    pdf.set_x(x)
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(*_TINTA)
    pdf.cell(w_label, 6, "Total", align="R")
    pdf.set_text_color(*_INDIGO)
    pdf.cell(w_valor, 6, formatear_monto(float(oc.get("total") or 0), moneda), align="R")
    pdf.ln(12)


def _despacho(pdf, ancho: float, oc: dict) -> None:
    """Bloque "Despachar a". Se omite entero si no hay dirección configurada."""
    direccion = (oc.get("direccion_despacho") or "").strip()
    if not direccion:
        return

    pdf.ln(6)
    y = pdf.get_y()
    # Una línea por cada ~90 caracteres; el bloque crece con el contenido.
    lineas = max(1, (len(direccion) // 90) + 1)
    alto = 11 + lineas * 4
    pdf.set_fill_color(*_FONDO_CAJA)
    pdf.rect(_MARGEN, y, ancho, alto, style="F")

    pdf.set_xy(_MARGEN + 3, y + 3)
    pdf.set_font("Helvetica", "B", 7)
    pdf.set_text_color(*_INDIGO)
    pdf.cell(ancho - 6, 4, "DESPACHAR A")

    pdf.set_xy(_MARGEN + 3, y + 8)
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(*_TINTA)
    pdf.multi_cell(ancho - 6, 4, _texto(direccion))
    pdf.set_y(y + alto)


def _condiciones(pdf, ancho: float, oc: dict) -> None:
    campos = [
        ("CONDICIONES DE PAGO", oc.get("condiciones_pago") or ""),
        ("PLAZO DE ENTREGA", oc.get("plazo_entrega") or "A convenir"),
    ]
    if oc.get("notas"):
        campos.append(("NOTAS", str(oc["notas"])))

    y = pdf.get_y()
    alto = 16
    pdf.set_fill_color(*_FONDO_CAJA)
    pdf.rect(_MARGEN, y, ancho, alto, style="F")
    w = ancho / len(campos)
    for i, (etiqueta, valor) in enumerate(campos):
        x = _MARGEN + i * w
        pdf.set_xy(x + 3, y + 3)
        pdf.set_font("Helvetica", "B", 7)
        pdf.set_text_color(*_INDIGO)
        pdf.cell(w - 6, 4, etiqueta)
        pdf.set_xy(x + 3, y + 8)
        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(*_TINTA)
        # Sin salto de línea: el ancho de columna es fijo y un texto largo
        # (los datos bancarios completos, por ejemplo) desbordaría la caja.
        pdf.cell(w - 6, 5, _texto(valor)[:60])
    pdf.set_y(y + alto)
