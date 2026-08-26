"""Frontera entre contexto interno y texto que lee un tercero.

Caso real (2026-08-26, hilo 64f2e851): salió al proveedor un correo con
*"No considerar el modelo de alta potencia E27/E40 de $25.000."* — una
instrucción de desambiguación interna para resolver un bug de precios nuestro.
"""
from app.services.texto_saliente import (
    ADVIERTE, BLOQUEA, bloqueantes, como_dict, revisar,
)

# Cuerpo textual del correo que se envió de verdad.
CORREO_REAL = """Hola Joaquín:

Para emitir la orden correctamente, necesitamos una cotización separada por 1 ampolleta LED estándar E27 de 100 W, luz fría, para cocina.

Por favor confirma que el precio unitario es $19.990 CLP, junto con disponibilidad, plazo de despacho y condiciones de pago. No considerar el modelo de alta potencia E27/E40 de $25.000.

Gracias."""

CORREO_LIMPIO = """Hola Joaquín:

Necesitamos cotización por 1 ampolleta LED estándar E27 de 100 W, luz fría.

Por favor confirma el precio unitario, disponibilidad, plazo de despacho y condiciones de pago.

Gracias."""


# ─── El caso que motivó el módulo ────────────────────────────────────────────

def test_el_correo_real_habria_sido_bloqueado():
    hallazgos = revisar(CORREO_REAL)
    bloqueos = bloqueantes(hallazgos)
    assert bloqueos, "el correo que se filtró debe quedar bloqueado"
    assert bloqueos[0].codigo == "deliberacion_interna"
    assert "No considerar el modelo" in bloqueos[0].fragmento


def test_un_correo_normal_pasa_sin_ruido():
    """Si el módulo molesta en el caso común, se termina desactivando."""
    assert revisar(CORREO_LIMPIO) == []


def test_texto_vacio_no_rompe():
    assert revisar("") == []
    assert revisar("   ") == []


# ─── Bloqueantes ─────────────────────────────────────────────────────────────

def test_identificador_interno_bloquea():
    hallazgos = revisar("Respecto al ítem 64f2e851-72bb-4b61-8b4b-b379af54b3dc, confirmá stock.")
    assert [h.codigo for h in hallazgos] == ["identificador_interno"]
    assert hallazgos[0].severidad == BLOQUEA


def test_variantes_de_deliberacion_interna():
    for frase in [
        "No considerar la opción anterior.",
        "No tomar en cuenta el precio previo.",
        "Nota interna: revisar antes de enviar.",
        "Fue un error del sistema, disculpas.",
        "Según nuestro registro interno el precio era otro.",
    ]:
        assert bloqueantes(revisar(frase)), f"debería bloquear: {frase}"


def test_nombrar_la_herramienta_interna_bloquea():
    """El proveedor trata con tu empresa, no con tu software de compras."""
    assert bloqueantes(revisar("Te escribimos desde Baiyer para cotizar."))


def test_es_insensible_a_mayusculas():
    assert bloqueantes(revisar("NO CONSIDERAR el modelo anterior."))


# ─── Advertencias: se avisan, no se frenan ───────────────────────────────────

def test_nombrar_competidor_advierte_pero_no_bloquea():
    """Preguntarle a un proveedor por alternativas de la competencia puede ser
    deliberado; el usuario lo pidió explícitamente en la sesión real."""
    hallazgos = revisar(
        "¿Tenés estas dos alternativas? VerLuz Pro y BYP Iluminación.",
        otros_proveedores=("VerLuz Pro", "BYP Iluminación"),
    )
    assert {h.codigo for h in hallazgos} == {"proveedor_competidor"}
    assert all(h.severidad == ADVIERTE for h in hallazgos)
    assert bloqueantes(hallazgos) == []


def test_direccion_interna_advierte():
    """Casi se envía Av. Pedro Dreyer 4627, Buenos Aires, como dirección de
    despacho de un proveedor chileno."""
    hallazgos = revisar(
        "Despachar a Av. Pedro Dreyer 4627, Monte Grande, Buenos Aires.",
        direcciones_internas=("Av. Pedro Dreyer 4627, Monte Grande, Buenos Aires",),
    )
    assert [h.codigo for h in hallazgos] == ["direccion_no_verificada"]
    assert hallazgos[0].severidad == ADVIERTE


def test_nombres_muy_cortos_se_ignoran():
    """Un proveedor llamado "3M" haría match dentro de cualquier palabra."""
    assert revisar("Confirmá el precio de las 3 unidades.", otros_proveedores=("3M", "")) == []


def test_no_advierte_por_un_competidor_que_no_aparece():
    assert revisar(CORREO_LIMPIO, otros_proveedores=("Sodimac", "Vitel")) == []


# ─── Forma de salida ─────────────────────────────────────────────────────────

def test_el_fragmento_trae_contexto_accionable():
    """Señalar la palabra suelta no le sirve a nadie para corregir."""
    hallazgo = bloqueantes(revisar(CORREO_REAL))[0]
    assert len(hallazgo.fragmento) > len("No considerar")
    assert "\n" not in hallazgo.fragmento


def test_como_dict_es_serializable():
    filas = como_dict(revisar(CORREO_REAL))
    assert filas and set(filas[0]) == {"codigo", "severidad", "fragmento", "motivo"}
    assert all(isinstance(v, str) for v in filas[0].values())


def test_cada_hallazgo_explica_el_motivo():
    """El aviso tiene que decir por qué, no sólo qué."""
    for h in revisar(CORREO_REAL):
        assert len(h.motivo) > 20
