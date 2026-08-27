"""Los proveedores llegan en dos listas separadas, no aplanados.

`suggest_suppliers` devolvía una sola lista `proveedores_recomendados` y el
cliente tenía que separar "ya trabajo con ellos" de "Baiyer los propone"
deduciéndolo del campo `origen`. En la sesión real del 2026-08-27 el usuario tuvo
que pedirlo tres veces: "solo me das un proveedor", "dame 10 y marca el origen",
"muéstrame al menos 5 resultados".
"""
import asyncio
from unittest.mock import patch

from app.services.mcp_context import ApplicationActorContext
from app.services.rfq_mcp_service import suggest_suppliers


def actor():
    return ApplicationActorContext("user-1", "org-1", "Vital", ("user-1",), client_id="codex")


SODIMAC = {"id": "prov-1", "nombre": "Sodimac Venta Empresa",
           "email": "venta_empresa@sodimac.cl", "origen": "proveedor",
           "origen_label": "Proveedor de tu empresa", "match_label": "Match por categoría",
           "match_score": 105.0, "seleccionado": False}
DISTEC = {"id": "sugerido:ventas@distec.cl", "nombre": "Distec Chile",
          "email": "ventas@distec.cl", "origen": "sugerido",
          "origen_label": "Sugerido por Baiyer",
          "match_label": "Soportes y monitores, audiovisual", "match_score": 40.0,
          "sitio_web": "https://distec.cl", "seleccionado": False}


def _sugerir(recomendados=None):
    detalle = {"items": [{
        "cotizacion_id": "cot-1", "nombre": "Monitor LED 24 pulgadas Full HD",
        "cantidad": 10, "unidad": "un", "categoria": "electronica",
        "proveedores_recomendados": recomendados if recomendados is not None else [SODIMAC, DISTEC],
    }]}

    async def fake_detalle(*_a, **_k):
        return detalle

    with patch("app.routers.listas.detalle_lista", fake_detalle):
        return asyncio.run(suggest_suppliers(actor(), "lista-1"))


# ─── Las dos listas ──────────────────────────────────────────────────────────

def test_separa_directorio_de_sugeridos():
    item = _sugerir()["items"][0]
    assert [p["nombre"] for p in item["del_directorio"]] == ["Sodimac Venta Empresa"]
    assert [p["nombre"] for p in item["sugeridos_por_baiyer"]] == ["Distec Chile"]


def test_cada_candidato_explica_por_que_calza():
    """Sin `motivo`, el cliente lo inventa —"match genérico"— y suena a relleno."""
    item = _sugerir()["items"][0]
    assert item["del_directorio"][0]["motivo"] == "Match por categoría"
    assert "monitores" in item["sugeridos_por_baiyer"][0]["motivo"]


def test_conserva_la_lista_plana_por_compatibilidad():
    item = _sugerir()["items"][0]
    assert len(item["proveedores_recomendados"]) == 2
    assert item["n_candidatos"] == 2


def test_el_resumen_cuenta_lo_del_directorio():
    resumen = _sugerir()["resumen"]
    assert resumen == {"items": 1, "items_sin_candidatos": 0, "proveedores_del_directorio": 1}


# ─── La pregunta ─────────────────────────────────────────────────────────────

def test_pregunta_por_el_envio_cuando_hay_candidatos():
    salida = _sugerir()
    assert salida["pregunta_al_usuario"] == "¿Envío los correos cotizando a estos proveedores?"


def test_aclara_que_todavia_no_sale_ningun_correo():
    """La pregunta sin esta aclaración suena a que el envío ya está en marcha."""
    salida = _sugerir()
    assert "prepare_rfq" in salida["antes_de_enviar"]
    assert "send_rfq" in salida["antes_de_enviar"]


def test_sin_candidatos_no_pregunta_por_el_envio():
    """Preguntar "¿los envío?" sin proveedores no tiene sentido."""
    salida = _sugerir(recomendados=[])
    assert "pregunta_al_usuario" not in salida
    assert "create_supplier" in salida["aviso"]


def test_sin_candidatos_lo_dice_en_el_resumen():
    assert _sugerir(recomendados=[])["resumen"]["items_sin_candidatos"] == 1


# ─── Casos borde ─────────────────────────────────────────────────────────────

def test_solo_sugeridos_igual_pregunta():
    salida = _sugerir(recomendados=[DISTEC])
    assert salida["items"][0]["del_directorio"] == []
    assert "pregunta_al_usuario" in salida


def test_un_proveedor_ya_seleccionado_se_marca():
    item = _sugerir(recomendados=[{**SODIMAC, "seleccionado": True}])["items"][0]
    assert item["del_directorio"][0]["seleccionado"] is True
