"""Fachada MCP para matriz, RFQ y respuestas del agente de correo existente."""
from typing import Any, Optional

from fastapi import HTTPException

from app.services.mcp_context import ApplicationActorContext


def _confirmed(value: bool, action: str) -> None:
    if value is not True:
        raise HTTPException(status_code=409, detail=f"Se requiere confirmación explícita para {action}")


async def get_supplier_matrix(actor: ApplicationActorContext, list_id: str) -> dict:
    from app.routers.listas import matriz_proveedores_confianza
    return await matriz_proveedores_confianza(list_id, actor.to_auth_context())


async def suggest_suppliers(actor: ApplicationActorContext, list_id: str) -> dict:
    """Devuelve la recomendación completa que ve la aplicación web.

    La matriz de confianza contiene solamente proveedores privados con una
    capacidad aprendida. El banco global curado por Baiyer se incorpora en
    ``detalle_lista`` y no debe copiarse masivamente al directorio privado.
    Exponer ese mismo resultado evita que MCP y la web recomienden universos
    distintos.
    """
    from app.routers.listas import detalle_lista

    detail = await detalle_lista(list_id, actor.to_auth_context())
    items = []
    total_directorio = 0
    for item in detail.get("items", []):
        recommendations = item.get("proveedores_recomendados") or []
        # Las dos listas van SEPARADAS, no aplanadas: "ya trabajo con ellos" y
        # "Baiyer los propone" son cosas distintas para quien decide a quién
        # cotizar, y antes el cliente tenía que deducirlo del campo `origen`.
        del_directorio = [_proveedor(p) for p in recommendations if p.get("origen") == "proveedor"]
        sugeridos = [_proveedor(p) for p in recommendations if p.get("origen") != "proveedor"]
        total_directorio += len(del_directorio)
        items.append({
            "cotizacion_id": item.get("cotizacion_id"),
            "nombre": item.get("nombre"),
            "cantidad": float(item.get("cantidad") or 1),
            "unidad": item.get("unidad") or "un",
            "categoria": item.get("categoria") or "otro",
            "n_candidatos": len(recommendations),
            "del_directorio": del_directorio,
            "sugeridos_por_baiyer": sugeridos,
            # Se conserva la lista plana: había clientes leyéndola.
            "proveedores_recomendados": recommendations,
        })

    hay_candidatos = any(item["n_candidatos"] for item in items)
    salida = {
        "list_id": list_id,
        "items": items,
        "resumen": {
            "items": len(items),
            "items_sin_candidatos": sum(1 for i in items if not i["n_candidatos"]),
            "proveedores_del_directorio": total_directorio,
        },
    }
    if hay_candidatos:
        # La pregunta viaja como dato y no como prosa del modelo: es el punto
        # donde el flujo pasa de leer a escribirle a un tercero, y quien decide
        # eso es una persona.
        salida["pregunta_al_usuario"] = "¿Envío los correos cotizando a estos proveedores?"
        salida["antes_de_enviar"] = (
            "Ningún correo sale de acá. `prepare_rfq` arma los borradores para revisarlos y "
            "`send_rfq` los envía, y ése exige confirmación explícita."
        )
    else:
        salida["aviso"] = (
            "Ningún ítem tiene proveedores candidatos. Podés agregar proveedores al directorio "
            "con create_supplier, o revisar la categoría de los ítems."
        )
    return salida


def _proveedor(p: dict) -> dict:
    """Forma mínima y explicada de un candidato: quién es, por qué calza y si ya
    está elegido. `motivo` es lo que evita que el cliente tenga que inventarlo."""
    return {
        "id": p.get("id"),
        "nombre": p.get("nombre"),
        "email": p.get("email"),
        "origen_label": p.get("origen_label"),
        "motivo": p.get("match_label"),
        "score": p.get("match_score"),
        "sitio_web": p.get("sitio_web"),
        "seleccionado": bool(p.get("seleccionado")),
    }


async def select_supplier_for_item(
    actor: ApplicationActorContext, list_id: str, cotizacion_id: str, *,
    origin: str, supplier_id: Optional[str] = None, email: Optional[str] = None,
    selected: bool = True,
) -> dict:
    """Selecciona tanto proveedores privados como sugeridos del banco Baiyer.

    El router existente materializa un sugerido sólo al seleccionarlo y
    sincroniza la matriz RFQ; así no se contamina el directorio de la empresa
    con todo el catálogo global.
    """
    from app.routers.listas import SeleccionarProveedorItemRequest, seleccionar_proveedor_item

    request = SeleccionarProveedorItemRequest(
        cotizacion_id=cotizacion_id, origen=origin, proveedor_id=supplier_id,
        email=email, seleccionado=selected,
    )
    return await seleccionar_proveedor_item(list_id, request, actor.to_auth_context())


async def set_supplier_matrix(actor: ApplicationActorContext, list_id: str, selections: list[dict[str, Any]]) -> dict:
    from app.routers.listas import GuardarMatrizConfianzaRequest, guardar_matriz_proveedores_confianza
    try:
        request = GuardarMatrizConfianzaRequest(selecciones=selections)
    except Exception as exc:
        raise HTTPException(status_code=422, detail="Selecciones de proveedor inválidas") from exc
    return await guardar_matriz_proveedores_confianza(list_id, request, actor.to_auth_context())


async def prepare_rfq(actor: ApplicationActorContext, list_id: str) -> dict:
    from app.routers.rfq import PrepararRFQRequest, preparar_rfq
    return await preparar_rfq(list_id, PrepararRFQRequest(), actor.to_auth_context())


async def get_rfq_preview(actor: ApplicationActorContext, list_id: str) -> dict:
    from app.routers.rfq import listar_rfq
    return await listar_rfq(list_id, actor.to_auth_context())


async def update_rfq_draft(
    actor: ApplicationActorContext, list_id: str, batch_id: str,
    *, recipient_email: str, subject: str, body: str,
) -> dict:
    from app.routers.rfq import EditarRFQRequest, editar_rfq
    request = EditarRFQRequest(destinatario_email=recipient_email, subject=subject, body=body)
    return await editar_rfq(list_id, batch_id, request, actor.to_auth_context())


async def send_rfq(
    actor: ApplicationActorContext, list_id: str, batch_id: str, *, confirmed: bool,
) -> dict:
    _confirmed(confirmed, "enviar la RFQ")
    from app.routers.rfq import EnviarRFQRequest, enviar_rfq
    return await enviar_rfq(list_id, batch_id, EnviarRFQRequest(), actor.to_auth_context())


async def get_rfq_status(actor: ApplicationActorContext, list_id: str) -> dict:
    from app.routers.rfq import listar_rfq
    from app.routers.gmail import listar_conversaciones
    preview = await listar_rfq(list_id, actor.to_auth_context())
    conversations = await listar_conversaciones(actor.to_auth_context())
    related = [row for row in conversations if row.get("lista_proyecto_id") == list_id]
    batches = preview.get("batches") or []
    raw_states = [row.get("estado") for row in batches]
    replied = sum(1 for row in related if row.get("estado") in {
        "supplier_replied", "partially_answered", "complete", "closed"
    })
    if not batches: canonical = "draft"
    elif any(state == "delivery_uncertain" for state in raw_states): canonical = "delivery_uncertain"
    elif any(state in {"draft", "ready_to_send"} for state in raw_states): canonical = "ready"
    elif any(state == "sending" for state in raw_states): canonical = "sending"
    elif replied == len(batches) and batches: canonical = "answered"
    elif replied: canonical = "partially_answered"
    elif all(state == "sent" for state in raw_states): canonical = "sent"
    elif any(state == "failed" for state in raw_states): canonical = "failed"
    else: canonical = "draft"
    return {"list_id": list_id, "canonical_status": canonical, "batches": batches,
            "conversations": related, "replied": replied}


async def sync_supplier_replies(actor: ApplicationActorContext, *, confirmed: bool) -> dict:
    _confirmed(confirmed, "sincronizar el correo")
    from app.routers.gmail import sincronizar_respuestas
    return await sincronizar_respuestas(actor.to_auth_context())


async def list_supplier_replies(actor: ApplicationActorContext, list_id: Optional[str] = None) -> dict:
    from app.routers.gmail import listar_conversaciones
    rows = await listar_conversaciones(actor.to_auth_context())
    if list_id is not None:
        rows = [row for row in rows if row.get("lista_proyecto_id") == list_id]
    return {"total": len(rows), "replies": rows}


async def get_supplier_reply(actor: ApplicationActorContext, conversation_id: str) -> dict:
    from app.routers.gmail import detalle_conversacion
    return await detalle_conversacion(conversation_id, actor.to_auth_context())


async def apply_reply_proposal(
    actor: ApplicationActorContext, proposal_id: str, *, confirmed: bool,
) -> dict:
    _confirmed(confirmed, "aplicar la propuesta")
    from app.routers.gmail import RevisarPropuestaRequest, aplicar_propuesta
    return await aplicar_propuesta(proposal_id, RevisarPropuestaRequest(), actor.to_auth_context())


async def reject_reply_proposal(
    actor: ApplicationActorContext, proposal_id: str, *, confirmed: bool,
) -> dict:
    _confirmed(confirmed, "rechazar la propuesta")
    from app.routers.gmail import RevisarPropuestaRequest, rechazar_propuesta
    return await rechazar_propuesta(proposal_id, RevisarPropuestaRequest(), actor.to_auth_context())
