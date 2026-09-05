"""Aislamiento entre organizaciones, probado contra Supabase real.

POR QUÉ EXISTE
--------------
`tenant_guard` cerró el **borde HTTP**: ninguna ruta `/api` corre sin un token
verificado. Eso no dice nada sobre lo que pasa *después*. El backend consulta
Supabase con la service key, así que **bypassea RLS**: dentro de un servicio, un
`.eq("id", ...)` sin su `.in_("user_id", actor.organization_user_ids)` al lado
devuelve la fila de otra empresa sin que nada se queje. Las políticas de la 031
no cubren este camino.

Es el bloqueante 2 de `CLAUDE.md` y el prerrequisito de la §6 del
`PRD_EMPLEADO_DIGITAL.md`. El empleado digital lo vuelve mucho más grave que hoy:
encadena decenas de llamadas sin que nadie mire los resultados intermedios, y
después redacta una respuesta en prosa. Una fila filtrada no aparece como una fila
filtrada — aparece como una frase.

QUÉ PRUEBA, EXACTAMENTE
-----------------------
Crea dos organizaciones reales, siembra datos en B, y ejecuta contra ellos las
capacidades que el agente va a usar **con la identidad de A**. Cada sonda tiene
que terminar en 404/403 o devolver vacío. Si alguna devuelve el centinela de B,
falla nombrando la capacidad.

Se prueba en la capa de **servicios/routers con `ApplicationActorContext`**, que
es donde el agente entra (§4.1: las tools son las capacidades MCP existentes), y
no por HTTP: `_actor()` de `streamable.py` sólo traduce un token MCP a ese mismo
contexto. Probar acá cubre a los dos clientes y no necesita emitir tokens OAuth.

Las sondas incluyen escrituras a propósito. Una lectura que filtra es una fuga;
una escritura que filtra es que A puede *modificar* datos de B, y esa no se
detecta leyendo.

POR QUÉ ES OPT-IN
-----------------
Escribe en la Supabase real (no hay otra: el proyecto no tiene entorno de test).
Crea dos usuarios de Auth y sus filas, y los borra al terminar. No corre en CI ni
con un `pytest` a secas — hay que pedirlo:

    BAIYER_TEST_AISLAMIENTO=1 .venv/bin/pytest tests/test_aislamiento_organizaciones.py -v

Si el proceso muere entre el seed y el cleanup quedan filas huérfanas; todas
llevan el prefijo `AISLAMIENTO-` en el nombre y el correo, para poder encontrarlas.
"""
from __future__ import annotations

import asyncio
import inspect
import os
import uuid

import pytest
from fastapi import HTTPException

from app.services.mcp_context import ApplicationActorContext

pytestmark = pytest.mark.skipif(
    not os.getenv("BAIYER_TEST_AISLAMIENTO"),
    reason="Escribe en la Supabase real; se corre a mano con BAIYER_TEST_AISLAMIENTO=1",
)

# Aparece en el nombre de cada fila sembrada en B. Si el string sale por
# cualquier sonda ejecutada como A, hubo fuga: no hay forma de que A lo conozca.
CENTINELA = f"AISLAMIENTO-CENTINELA-{uuid.uuid4().hex[:12]}"


class Organizacion:
    """Una organización de prueba: su usuario de Auth, su contexto y sus datos."""

    def __init__(self, user_id: str, email: str, actor: ApplicationActorContext):
        self.user_id = user_id
        self.email = email
        self.actor = actor
        self.ids: dict[str, str] = {}


def _sb():
    from app.services.supabase import get_supabase

    return get_supabase()


def _crear_organizacion(sb, etiqueta: str) -> Organizacion:
    from app.services.organizacion import obtener_organizacion, resolver_organizacion

    email = f"aislamiento-{etiqueta}-{uuid.uuid4().hex[:10]}@example.com"
    creado = sb.auth.admin.create_user(
        {"email": email, "password": uuid.uuid4().hex, "email_confirm": True}
    )
    user_id = creado.user.id
    # Misma red de seguridad que usa `get_auth_context`: crea la organización
    # personal del usuario recién registrado.
    obtener_organizacion(user_id)
    ctx = resolver_organizacion(user_id)
    assert ctx, f"la organización de {etiqueta} no quedó resuelta"
    actor = ApplicationActorContext(
        actor_user_id=user_id,
        organization_id=ctx.organizacion_id,
        organization_name=ctx.nombre,
        organization_user_ids=tuple(ctx.user_ids_miembros),
        is_admin=ctx.es_admin,
        scopes=frozenset(),  # las sondas llaman servicios, que no chequean scope
    )
    return Organizacion(user_id, email, actor)


def _sembrar(sb, org: Organizacion) -> None:
    """Deja en `org` una fila de cada tipo que las sondas van a intentar leer.

    Se usan los servicios reales donde existen (`create_list` valida pertenencia
    de las cotizaciones, y esa validación es justamente parte de lo que se prueba);
    donde no hay servicio de creación se inserta directo.
    """
    from app.services.lista_service import ListItemInput, create_list

    cotizacion = sb.table("cotizaciones").insert({
        "user_id": org.user_id,
        "descripcion": f"{CENTINELA} descripción",
        "nombre_identificado": f"{CENTINELA} ítem",
        "categoria": "consumible",
        "estado": "identificado",
    }).execute().data[0]
    org.ids["cotizacion"] = cotizacion["id"]

    lista = create_list(
        sb, org.actor, f"{CENTINELA} lista",
        [ListItemInput(cotizacion["id"], f"{CENTINELA} ítem", cantidad=1)],
    )
    org.ids["lista"] = lista["id"]

    proveedor = sb.table("proveedores").insert({
        "user_id": org.user_id,
        "nombre": f"{CENTINELA} proveedor",
        "email": f"proveedor-{uuid.uuid4().hex[:8]}@example.com",
    }).execute().data[0]
    org.ids["proveedor"] = proveedor["id"]

    oc = sb.table("ordenes_compra").insert({
        "user_id": org.user_id,
        "cotizacion_id": cotizacion["id"],
        "numero_oc": f"{CENTINELA}-OC",
        "estado": "borrador",
        "precio_total": 1000,
        "moneda": "CLP",
        "token_confirmacion": uuid.uuid4().hex,
        "nombre_item": f"{CENTINELA} ítem",
        "proveedor_nombre": f"{CENTINELA} proveedor",
    }).execute().data[0]
    org.ids["oc"] = oc["id"]

    factura = sb.table("facturas").insert({
        "user_id": org.user_id,
        "proveedor_nombre": f"{CENTINELA} proveedor",
        "numero_factura": f"{CENTINELA}-F",
        "monto_total": 1000,
        "moneda": "CLP",
        "estado": "pendiente",
    }).execute().data[0]
    org.ids["factura"] = factura["id"]

    job = sb.table("integration_jobs").insert({
        "organization_id": org.actor.organization_id,
        "actor_user_id": org.user_id,
        "client_id": "aislamiento-test",
        "job_type": "web_quote",
        "status": "queued",
        "progress": 0,
        "input": {"centinela": CENTINELA},
        "idempotency_key": f"{CENTINELA}-job",
    }).execute().data[0]
    org.ids["job"] = job["id"]


def _borrar(sb, org: Organizacion) -> None:
    """Best-effort: cada borrado se intenta aunque el anterior falle.

    El orden respeta las dependencias (OC y factura antes que la cotización).
    Si algo queda, lleva el centinela en el nombre.
    """
    borrados = [
        ("ordenes_compra", "id", org.ids.get("oc")),
        ("facturas", "id", org.ids.get("factura")),
        ("integration_jobs", "id", org.ids.get("job")),
        ("proveedores", "id", org.ids.get("proveedor")),
        ("proyectos", "id", org.ids.get("lista")),
        ("cotizaciones", "id", org.ids.get("cotizacion")),
        ("membresias_organizacion", "user_id", org.user_id),
        ("organizaciones", "owner_user_id", org.user_id),
    ]
    for tabla, columna, valor in borrados:
        if not valor:
            continue
        try:
            sb.table(tabla).delete().eq(columna, valor).execute()
        except Exception as exc:  # noqa: BLE001 — limpieza, no queremos enmascarar el fallo real
            print(f"[aislamiento] no se pudo borrar {tabla}.{columna}={valor}: {exc}")
    try:
        sb.auth.admin.delete_user(org.user_id)
    except Exception as exc:  # noqa: BLE001
        print(f"[aislamiento] no se pudo borrar el usuario {org.email}: {exc}")


@pytest.fixture(scope="module")
def dos_organizaciones():
    sb = _sb()
    a = _crear_organizacion(sb, "a")
    b = _crear_organizacion(sb, "b")
    assert a.actor.organization_id != b.actor.organization_id
    assert b.user_id not in a.actor.organization_user_ids, (
        "A y B no quedaron separadas: la fixture no prueba nada"
    )
    try:
        _sembrar(sb, b)
        yield a, b
    finally:
        _borrar(sb, b)
        _borrar(sb, a)


def _sondas(actor, ids):
    """(nombre, invocable) por cada capacidad que el agente puede usar con un id.

    El nombre es el de la tool MCP, para que un fallo se lea como "get_list filtró"
    y no como el nombre interno del servicio.
    """
    from app.routers import proveedores as r_proveedores
    from app.routers import suppliers as r_suppliers
    from app.services import comparison_approval_service as comparacion
    from app.services import lista_service as listas
    from app.services import mcp_jobs as jobs
    from app.services import purchase_invoice_service as compras
    from app.services import rfq_mcp_service as rfq
    from app.services import web_quote_service as web

    sb = _sb()
    auth = actor.to_auth_context()
    lista, cotizacion = ids["lista"], ids["cotizacion"]
    oc, factura, proveedor, job = ids["oc"], ids["factura"], ids["proveedor"], ids["job"]

    return [
        # ── Lecturas ────────────────────────────────────────────────────────
        ("get_list", lambda: listas.get_list(sb, actor, lista)),
        ("get_item_quotes", lambda: web.get_item_quotes(sb, actor, cotizacion)),
        ("get_list_coverage", lambda: web.get_list_coverage(sb, actor, lista)),
        ("get_job", lambda: jobs.get_job(sb, actor, job)),
        ("get_purchase_order", lambda: compras.get_purchase_order(sb, actor, oc)),
        ("get_purchase_order_tracking", lambda: compras.get_purchase_order_tracking(sb, actor, oc)),
        ("get_invoice", lambda: compras.get_invoice(sb, actor, factura)),
        ("reconcile_invoice_po", lambda: compras.reconcile_invoice_po(sb, actor, factura, oc)),
        ("compare_list", lambda: comparacion.compare_list(sb, actor, lista)),
        ("compare_item", lambda: comparacion.compare_item(sb, actor, lista, cotizacion)),
        ("explain_quote_recommendation",
         lambda: comparacion.explain_quote_recommendation(sb, actor, lista, cotizacion)),
        ("get_approval_status", lambda: comparacion.get_approval_status(sb, actor, lista)),
        ("get_approval_route", lambda: comparacion.get_approval_route(sb, actor, lista)),
        ("list_workflow_events", lambda: comparacion.list_workflow_events(sb, actor, lista)),
        ("get_supplier_matrix", lambda: rfq.get_supplier_matrix(actor, lista)),
        ("get_rfq_status", lambda: rfq.get_rfq_status(actor, lista)),
        ("get_supplier", lambda: r_proveedores.ficha_proveedor(proveedor, auth)),
        ("get_supplier_history", lambda: r_suppliers.historial_supplier(proveedor, auth)),
        # ── Escrituras: una fuga acá no es leer datos ajenos, es modificarlos ─
        ("rename_list", lambda: listas.rename_list(sb, actor, lista, "renombrada por A")),
        ("remove_list_item", lambda: listas.remove_list_item(sb, actor, lista, cotizacion)),
        ("update_purchase_order",
         lambda: compras.update_purchase_order(sb, actor, oc, {"notas": "tocada por A"}, confirmed=True)),
        ("prepare_purchase_order", lambda: compras.prepare_purchase_order(sb, actor, lista, cotizacion)),
    ]


def _ejecutar(invocable):
    resultado = invocable()
    if inspect.isawaitable(resultado):
        resultado = asyncio.run(resultado)
    return resultado


def test_ninguna_capacidad_devuelve_datos_de_otra_organizacion(dos_organizaciones):
    """A ejecuta cada capacidad sobre los ids de B. Ninguna puede devolver B."""
    a, b = dos_organizaciones
    fugas = []

    for nombre, invocable in _sondas(a.actor, b.ids):
        try:
            resultado = _ejecutar(invocable)
        except HTTPException as exc:
            # Lo esperado. 404 y no 403 a propósito: un 403 confirma que el id
            # existe en otra organización, que ya es información.
            if exc.status_code not in (403, 404):
                fugas.append(f"{nombre}: HTTP {exc.status_code} inesperado ({exc.detail})")
            continue
        except Exception as exc:  # noqa: BLE001
            # Un error distinto tampoco filtra datos, pero sí tapa el resultado
            # real de la sonda: se reporta para revisarlo, no como fuga.
            fugas.append(f"{nombre}: excepción no-HTTP {type(exc).__name__}: {exc}")
            continue

        if CENTINELA in str(resultado):
            fugas.append(f"{nombre}: DEVOLVIÓ DATOS DE LA OTRA ORGANIZACIÓN")

    assert not fugas, "Fugas entre organizaciones:\n  - " + "\n  - ".join(fugas)


def test_los_listados_de_a_no_incluyen_nada_de_b(dos_organizaciones):
    """Las capacidades sin id son la otra mitad: filtran por organización o listan todo."""
    from app.services import lista_service as listas
    from app.services import mcp_jobs as jobs
    from app.services import purchase_invoice_service as compras

    a, _ = dos_organizaciones
    sb = _sb()
    listados = {
        "list_lists": lambda: listas.list_lists(sb, a.actor),
        "list_purchase_orders": lambda: compras.list_purchase_orders(sb, a.actor),
        "list_jobs": lambda: jobs.list_jobs(sb, a.actor),
    }
    fugas = [nombre for nombre, fn in listados.items() if CENTINELA in str(fn())]
    assert not fugas, f"Listados que incluyen datos de otra organización: {fugas}"


def test_b_si_ve_sus_propios_datos(dos_organizaciones):
    """Control negativo: sin esto, un servicio roto que devuelve vacío siempre
    haría pasar el test de fugas por el motivo equivocado."""
    from app.services.lista_service import get_list

    _, b = dos_organizaciones
    assert CENTINELA in str(get_list(_sb(), b.actor, b.ids["lista"])), (
        "B no ve su propia lista: la siembra no quedó donde el test cree"
    )
