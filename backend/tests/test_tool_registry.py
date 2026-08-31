"""El registro de capacidades tiene que describir la realidad, no una foto vieja.

Mismo criterio que `test_tenant_guard.py`: el mecanismo real no es el módulo, es
este test. Una tool nueva sin clasificar rompe el CI, así que nace declarada; una
entrada que sobra también, así que el registro no acumula fantasmas.

La fuente de verdad es el AST de `app/mcp/streamable.py`, no una lista escrita a
mano acá: si se lee el código de verdad, el test no puede quedar desincronizado
sin que alguien se entere.
"""
import ast
from pathlib import Path

import pytest

from app.services.tool_registry import (
    EFECTO_ORDEN,
    TOOLS,
    Efecto,
    exige_autorizacion_humana,
    spec,
)
from app.services.workflow_engine import ROLES_BASE

SERVIDOR = Path(__file__).resolve().parents[1] / "app" / "mcp" / "streamable.py"


def _tools_declaradas_en_codigo() -> dict[str, dict]:
    """Extrae del AST cada `@mcp.tool`: nombre real, scope que pide y si lleva
    el argumento `confirmed`."""
    arbol = ast.parse(SERVIDOR.read_text())
    encontradas: dict[str, dict] = {}
    for nodo in ast.walk(arbol):
        if not isinstance(nodo, (ast.AsyncFunctionDef, ast.FunctionDef)):
            continue
        decorador = next(
            (d for d in nodo.decorator_list
             if isinstance(d, ast.Call) and getattr(d.func, "attr", "") == "tool"),
            None,
        )
        if decorador is None:
            continue

        nombre, solo_lectura = nodo.name, False
        for kw in decorador.keywords:
            if kw.arg == "name" and isinstance(kw.value, ast.Constant):
                nombre = kw.value.value
            if kw.arg == "annotations":
                for anotacion in getattr(kw.value, "keywords", []):
                    if anotacion.arg == "readOnlyHint" and getattr(anotacion.value, "value", None) is True:
                        solo_lectura = True

        scope = None
        for interno in ast.walk(nodo):
            if not isinstance(interno, ast.Call):
                continue
            es_actor = getattr(interno.func, "id", "") == "_actor"
            es_to_thread = getattr(interno.func, "attr", "") == "to_thread"
            if not (es_actor or es_to_thread):
                continue
            for arg in interno.args:
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str) and ":" in arg.value:
                    scope = arg.value

        argumentos = [a.arg for a in nodo.args.args] + [a.arg for a in nodo.args.kwonlyargs]
        encontradas[nombre] = {
            "scope": scope,
            "solo_lectura": solo_lectura,
            "tiene_confirmed": "confirmed" in argumentos,
        }
    return encontradas


CODIGO = _tools_declaradas_en_codigo()


def test_el_servidor_expone_tools():
    """Red de seguridad del propio test: si el parseo devuelve vacío, todo lo
    demás pasaría por vacuidad y no nos enteraríamos."""
    assert len(CODIGO) > 50, f"El AST sólo encontró {len(CODIGO)} tools; ¿cambió la forma del decorador?"


def test_toda_tool_del_servidor_esta_declarada():
    faltan = sorted(set(CODIGO) - set(TOOLS))
    assert not faltan, (
        "Estas tools existen en el servidor MCP pero no están clasificadas en "
        f"tool_registry.TOOLS: {faltan}. Declaralas con su efecto antes de exponerlas."
    )


def test_el_registro_no_tiene_entradas_muertas():
    sobran = sorted(set(TOOLS) - set(CODIGO))
    assert not sobran, (
        f"Estas entradas del registro no corresponden a ninguna tool real: {sobran}. "
        "Un registro con fantasmas deja de ser confiable."
    )


def test_el_scope_declarado_coincide_con_el_del_codigo():
    """Si alguien cambia el scope en el servidor y no toca el registro, el
    registro pasa a mentir en silencio. Acá se cae."""
    desincronizados = {
        nombre: (datos["scope"], TOOLS[nombre].scope)
        for nombre, datos in CODIGO.items()
        if nombre in TOOLS and datos["scope"] != TOOLS[nombre].scope
    }
    assert not desincronizados, f"Scope distinto entre código y registro (tool: (código, registro)): {desincronizados}"


def test_dinero_y_externo_exigen_autorizacion_humana():
    """Regla dura 1 del PRD: `dinero` siempre, sin monto mínimo ni modo confianza."""
    for nombre, s in TOOLS.items():
        esperado = EFECTO_ORDEN[s.efecto] >= EFECTO_ORDEN[Efecto.EXTERNO]
        assert exige_autorizacion_humana(nombre) is esperado, nombre
    for nombre in ("send_purchase_order", "mark_invoice_paid", "approve_request", "send_rfq"):
        assert exige_autorizacion_humana(nombre), f"{nombre} debe exigir autorización humana"


def test_ninguna_tool_de_solo_lectura_mueve_plata():
    """Una tool anotada `readOnlyHint` que además esté clasificada como `dinero`
    o `externo` sería una contradicción peligrosa: el cliente MCP la trataría
    como inofensiva."""
    contradicciones = [
        nombre for nombre, datos in CODIGO.items()
        if datos["solo_lectura"] and nombre in TOOLS
        and EFECTO_ORDEN[TOOLS[nombre].efecto] >= EFECTO_ORDEN[Efecto.EXTERNO]
    ]
    assert not contradicciones, (
        f"Declaradas readOnlyHint pero con efecto externo/dinero: {contradicciones}"
    )


def test_los_roles_requeridos_existen_en_el_workflow():
    """No sirve exigir un rol que el motor de workflow no conoce: nunca se
    podría satisfacer."""
    invalidos = {
        nombre: s.rol_requerido for nombre, s in TOOLS.items()
        if s.rol_requerido is not None and s.rol_requerido not in ROLES_BASE
    }
    assert not invalidos, f"Roles que no están en workflow_engine.ROLES_BASE: {invalidos}"


def test_toda_tool_de_dinero_tiene_rol_responsable():
    """Si compromete plata, tiene que poder decirse QUIÉN es el responsable
    capaz de autorizarlo. Sin rol, la autorización no sería trazable a una
    persona (regla dura 1)."""
    sin_rol = [n for n, s in TOOLS.items() if s.efecto is Efecto.DINERO and not s.rol_requerido]
    assert not sin_rol, f"Efecto `dinero` sin rol_requerido: {sin_rol}"


def test_spec_desconocida_falla_ruidosamente():
    with pytest.raises(KeyError, match="no está declarada"):
        spec("tool_que_no_existe")


def test_la_clasificacion_cubre_los_cuatro_efectos():
    """Si un efecto queda vacío es señal de que alguien colapsó la escala."""
    for efecto in Efecto:
        assert any(s.efecto is efecto for s in TOOLS.values()), f"Ningún tool clasificado como {efecto}"


# ── Deuda declarada ──────────────────────────────────────────────────────────
# `confirmed` se pide hoy de forma despareja y este test lo FIJA en vez de
# esconderlo: no falla por las inconsistencias que ya existen, pero sí falla si
# aparecen nuevas. El objetivo es que este conjunto sólo pueda achicarse cuando
# F1 reemplace `confirmed` por la barrera real.
ESCRITURAS_SIN_CONFIRMED = {
    "create_list", "rename_list", "add_list_items", "update_list_item",
    "start_project_intake", "continue_project_intake",
    "preview_document_import", "preview_invoice_import", "preview_supplier_import",
    "start_web_quote", "quote_project", "quote_new_project", "search_alternatives",
    "prepare_rfq", "update_rfq_draft", "set_supplier_matrix", "select_supplier_for_item",
}


def test_la_deuda_de_confirmed_no_crece():
    reales = {
        nombre for nombre, datos in CODIGO.items()
        if nombre in TOOLS
        and TOOLS[nombre].efecto is Efecto.ESCRITURA
        and not datos["tiene_confirmed"]
    }
    nuevas = sorted(reales - ESCRITURAS_SIN_CONFIRMED)
    assert not nuevas, (
        f"Escrituras nuevas sin `confirmed`: {nuevas}. Hoy la política es despareja "
        "y está fijada acá; no la amplíes sin decidirlo."
    )
    resueltas = sorted(ESCRITURAS_SIN_CONFIRMED - reales)
    assert not resueltas, (
        f"Estas ya no aplican y hay que sacarlas de ESCRITURAS_SIN_CONFIRMED: {resueltas}"
    )


def test_todo_lo_externo_y_de_dinero_pide_confirmed_hoy():
    """Mientras `confirmed` siga siendo el único gesto de confirmación, al menos
    tiene que estar presente en TODO lo irreversible. Cuando F1 lo reemplace,
    este test cambia junto con el mecanismo."""
    sin_gesto = [
        nombre for nombre, datos in CODIGO.items()
        if nombre in TOOLS
        and EFECTO_ORDEN[TOOLS[nombre].efecto] >= EFECTO_ORDEN[Efecto.EXTERNO]
        and not datos["tiene_confirmed"]
    ]
    assert not sin_gesto, f"Efecto externo/dinero sin ningún gesto de confirmación: {sin_gesto}"
