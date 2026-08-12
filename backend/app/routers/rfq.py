"""RFQs agrupadas por proveedor para listas multiítem (Fase 5).

Prepara borradores idempotentes desde la matriz revisada, permite editarlos y
envía un único correo Gmail por proveedor. Cada ítem conserva su resultado
propio para que el agente de respuestas actualice el comparador existente.
"""
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.routers.listas import _lock_de, _parse_lista
from app.services.auth_context import AuthContext, get_auth_context
from app.services.supabase import ejecutar_maybe_single

router = APIRouter(prefix="/api/listas", tags=["rfq"])


def _ids_org(user_id: str) -> list[str]:
    """Wrapper local para import perezoso (Fase B del multi-usuario)."""
    from app.services.organizacion import ids_organizacion
    return ids_organizacion(user_id)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _correo_default(nombre_lista: str, proveedor: str, items: list[dict]) -> tuple[str, str]:
    lineas = []
    for it in items:
        linea = f"- {it['cantidad']:g} {it['unidad']} · {it['nombre']}"
        if it.get("especificaciones"):
            linea += f" — {it['especificaciones']}"
        lineas.append(linea)
    subject = f"Solicitud de cotización — {nombre_lista}"
    body = (
        f"Estimados {proveedor},\n\n"
        "Junto con saludar, solicitamos su cotización para los siguientes ítems:\n\n"
        + "\n".join(lineas)
        + "\n\nAgradeceremos indicar precio unitario, moneda, disponibilidad, plazo de entrega "
          "y condiciones de pago para cada ítem.\n\nSaludos cordiales."
    )
    return subject, body


def _resultado_para_item(sb, cotizacion_id: str, proveedor: dict, email: str) -> str:
    existente = (
        sb.table("resultados").select("id")
        .eq("cotizacion_id", cotizacion_id)
        .eq("proveedor_nombre", proveedor["nombre"][:100])
        .eq("proveedor_email", email).limit(1).execute().data or []
    )
    if existente:
        return existente[0]["id"]
    fila = sb.table("resultados").insert({
        "cotizacion_id": cotizacion_id,
        "proveedor_nombre": proveedor["nombre"][:100],
        "proveedor_email": email,
        "precio": None, "moneda": "CLP", "url": "",
        "pais": proveedor.get("pais") or "CL", "fuente": "manual",
        "tipo_proveedor": "desconocido", "relevante": True, "estado": "encontrado",
    }).execute().data[0]
    return fila["id"]


class PrepararRFQRequest(BaseModel):
    pass


@router.post("/{lista_id}/rfq/preparar")
async def preparar_rfq(lista_id: str, req: PrepararRFQRequest, ctx: AuthContext = Depends(get_auth_context)):
    from app.services.supabase import get_supabase
    sb = get_supabase()
    async with _lock_de(lista_id):
        proyecto = ejecutar_maybe_single(sb.table("proyectos").select("*").eq("id", lista_id).in_("user_id", ctx.user_ids_organizacion).maybe_single()).data
        data = _parse_lista(proyecto or {})
        if not data:
            raise HTTPException(status_code=404, detail="Lista no encontrada")
        matriz = data.get("proveedores_confianza") or {}
        if not matriz.get("revisado"):
            raise HTTPException(status_code=400, detail="Primero revisa y guarda la matriz de proveedores")
        selecciones = matriz.get("selecciones") or []
        if not selecciones:
            raise HTTPException(status_code=400, detail="La matriz no tiene proveedores seleccionados")

        items_lista = {it["cotizacion_id"]: it for it in data.get("items", [])}
        cot_ids = list(items_lista)
        cotizaciones = {c["id"]: c for c in (sb.table("cotizaciones").select("id,nombre_identificado,categoria,descripcion").in_("id", cot_ids).execute().data or [])}
        preparados = []
        for seleccion in selecciones:
            proveedor_id = seleccion["proveedor_id"]
            proveedor = ejecutar_maybe_single(sb.table("proveedores").select("*").eq("id", proveedor_id).in_("user_id", ctx.user_ids_organizacion).eq("bloqueado", False).maybe_single()).data
            if not proveedor:
                continue
            contacto = None
            if seleccion.get("contacto_id"):
                contacto = ejecutar_maybe_single(sb.table("proveedor_contactos").select("*").eq("id", seleccion["contacto_id"]).eq("proveedor_id", proveedor_id).in_("user_id", ctx.user_ids_organizacion).maybe_single()).data
            if not contacto:
                principales = sb.table("proveedor_contactos").select("*").eq("proveedor_id", proveedor_id).in_("user_id", ctx.user_ids_organizacion).eq("es_principal", True).limit(1).execute().data or []
                contacto = principales[0] if principales else None
            email = (contacto or {}).get("email") or proveedor.get("email")
            if not email:
                continue

            items = []
            for cid in seleccion.get("cotizacion_ids", []):
                if cid not in items_lista:
                    continue
                base = items_lista[cid]
                cot = cotizaciones.get(cid, {})
                items.append({
                    "cotizacion_id": cid,
                    "nombre": base.get("nombre") or cot.get("nombre_identificado") or "Ítem",
                    "cantidad": float(base.get("cantidad") or 1),
                    "unidad": base.get("unidad") or "un",
                    "categoria": cot.get("categoria") or base.get("categoria") or "otro",
                    "especificaciones": (base.get("descripcion") or cot.get("descripcion") or "").strip()[:500],
                })
            if not items:
                continue

            clave = f"lista:{lista_id}:proveedor:{proveedor_id}:v1"
            respuesta_existente = (
                sb.table("rfq_batches").select("*")
                .in_("user_id", ctx.user_ids_organizacion)
                .eq("clave_idempotencia", clave).maybe_single().execute()
            )
            # Algunas versiones de postgrest-py devuelven None (no un objeto
            # con data=None) cuando maybe_single no encuentra filas.
            existente = respuesta_existente.data if respuesta_existente else None
            if existente and existente.get("estado") in ("sending", "sent", "delivery_uncertain"):
                preparados.append(existente)
                continue
            subject, body = _correo_default(proyecto.get("nombre") or "Cotización", proveedor["nombre"], items)
            row = {
                "user_id": ctx.actor_user_id, "lista_proyecto_id": lista_id,
                "proveedor_id": proveedor_id, "contacto_id": (contacto or {}).get("id"),
                # Preparar nuevamente debe retomar el trabajo guardado, no
                # pisar ediciones con la plantilla por defecto.
                "destinatario_email": existente.get("destinatario_email") if existente else email,
                "subject": existente.get("subject") if existente else subject,
                "body": existente.get("body") if existente else body,
                "estado": existente.get("estado") if existente else "draft",
                "clave_idempotencia": clave, "updated_at": _now(),
            }
            if existente:
                batch = sb.table("rfq_batches").update(row).eq("id", existente["id"]).execute().data[0]
                batch_id = existente["id"]
            else:
                batch = sb.table("rfq_batches").insert(row).execute().data[0]
                batch_id = batch["id"]

            ids_actuales = []
            for item in items:
                resultado_id = _resultado_para_item(sb, item["cotizacion_id"], proveedor, email)
                batch_item = sb.table("rfq_batch_items").upsert({
                    "rfq_batch_id": batch_id, "cotizacion_id": item["cotizacion_id"],
                    "resultado_id": resultado_id, "cantidad": item["cantidad"],
                    "unidad": item["unidad"], "updated_at": _now(),
                }, on_conflict="rfq_batch_id,cotizacion_id").execute().data[0]
                ids_actuales.append(batch_item["id"])
            existentes_items = sb.table("rfq_batch_items").select("id").eq("rfq_batch_id", batch_id).execute().data or []
            sobrantes = [it["id"] for it in existentes_items if it["id"] not in ids_actuales]
            if sobrantes:
                sb.table("rfq_batch_items").delete().in_("id", sobrantes).execute()
            preparados.append(batch)
    return {"batches": len(preparados)}


def _listar_batches(sb, lista_id: str, user_id: str) -> list[dict]:
    batches = sb.table("rfq_batches").select("*").eq("lista_proyecto_id", lista_id).in_("user_id", _ids_org(user_id)).order("created_at").execute().data or []
    if not batches:
        return []
    proveedor_ids = [b["proveedor_id"] for b in batches]
    proveedores = {p["id"]: p for p in (sb.table("proveedores").select("id,nombre,score,preferido").in_("id", proveedor_ids).execute().data or [])}
    batch_ids = [b["id"] for b in batches]
    items = sb.table("rfq_batch_items").select("*").in_("rfq_batch_id", batch_ids).execute().data or []
    cot_ids = [it["cotizacion_id"] for it in items]
    cots = {c["id"]: c for c in (sb.table("cotizaciones").select("id,nombre_identificado,categoria").in_("id", cot_ids).execute().data or [])} if cot_ids else {}
    por_batch: dict[str, list] = {}
    for it in items:
        cot = cots.get(it["cotizacion_id"], {})
        por_batch.setdefault(it["rfq_batch_id"], []).append({
            **it, "nombre": cot.get("nombre_identificado") or "Ítem", "categoria": cot.get("categoria") or "otro",
        })
    return [{**b, "proveedor": proveedores.get(b["proveedor_id"], {}), "items": por_batch.get(b["id"], [])} for b in batches]


@router.get("/{lista_id}/rfq")
async def listar_rfq(lista_id: str, ctx: AuthContext = Depends(get_auth_context)):
    from app.services.supabase import get_supabase
    return {"batches": _listar_batches(get_supabase(), lista_id, ctx.actor_user_id)}


class EditarRFQRequest(BaseModel):
    destinatario_email: str
    subject: str
    body: str


@router.patch("/{lista_id}/rfq/{batch_id}")
async def editar_rfq(lista_id: str, batch_id: str, req: EditarRFQRequest, ctx: AuthContext = Depends(get_auth_context)):
    from app.services.supabase import get_supabase
    sb = get_supabase()
    batch = ejecutar_maybe_single(sb.table("rfq_batches").select("id,estado").eq("id", batch_id).eq("lista_proyecto_id", lista_id).in_("user_id", ctx.user_ids_organizacion).maybe_single()).data
    if not batch:
        raise HTTPException(status_code=404, detail="Borrador no encontrado")
    if batch["estado"] not in ("draft", "ready_to_send", "failed"):
        raise HTTPException(status_code=409, detail="Este correo ya no puede editarse")
    email = req.destinatario_email.strip().lower()
    if "@" not in email or email.startswith("@") or email.endswith("@"):
        raise HTTPException(status_code=400, detail="Correo destinatario inválido")
    if not req.subject.strip() or not req.body.strip():
        raise HTTPException(status_code=400, detail="Asunto y cuerpo son obligatorios")
    return sb.table("rfq_batches").update({
        "destinatario_email": email, "subject": req.subject.strip(),
        "body": req.body.strip(), "estado": "ready_to_send", "error_detalle": None, "updated_at": _now(),
    }).eq("id", batch_id).execute().data[0]


class EnviarRFQRequest(BaseModel):
    pass


@router.post("/{lista_id}/rfq/{batch_id}/enviar")
async def enviar_rfq(lista_id: str, batch_id: str, req: EnviarRFQRequest, ctx: AuthContext = Depends(get_auth_context)):
    from app.services.gmail_service import get_gmail_service, send_email
    from app.services.supabase import get_supabase
    from app.services.supplier_capability_intelligence import registrar_evento
    sb = get_supabase()
    batch = ejecutar_maybe_single(sb.table("rfq_batches").select("*").eq("id", batch_id).eq("lista_proyecto_id", lista_id).in_("user_id", ctx.user_ids_organizacion).maybe_single()).data
    if not batch:
        raise HTTPException(status_code=404, detail="RFQ no encontrada")
    if batch["estado"] == "sent":
        return {"success": True, "already_sent": True, "thread_id": batch.get("gmail_thread_id")}
    if batch["estado"] in ("sending", "delivery_uncertain"):
        raise HTTPException(status_code=409, detail="El estado del envío requiere revisión para evitar duplicados")

    # user_integrations es personal — cada usuario conecta su propio Gmail; no se comparte a la organización.
    integration = ejecutar_maybe_single(sb.table("user_integrations").select("*").eq("user_id", ctx.actor_user_id).eq("provider", "gmail").maybe_single()).data
    if not integration or not integration.get("refresh_token"):
        raise HTTPException(status_code=400, detail="Gmail no está conectado")
    sb.table("rfq_batches").update({"estado": "sending", "error_detalle": None, "updated_at": _now()}).eq("id", batch_id).execute()
    try:
        service, creds = get_gmail_service(integration["access_token"], integration["refresh_token"])
        if creds.token != integration["access_token"]:
            sb.table("user_integrations").update({"access_token": creds.token, "token_expiry": creds.expiry.isoformat() if creds.expiry else None}).eq("user_id", ctx.actor_user_id).eq("provider", "gmail").execute()
        msg = send_email(service, batch["destinatario_email"], batch["subject"], batch["body"], integration["email"])
    except Exception as e:
        sb.table("rfq_batches").update({"estado": "delivery_uncertain", "error_detalle": str(e)[:1000], "updated_at": _now()}).eq("id", batch_id).execute()
        raise HTTPException(status_code=502, detail="No se pudo confirmar el envío. Revisa Gmail antes de reintentar para evitar duplicados.")

    now = _now()
    try:
        proveedor = ejecutar_maybe_single(sb.table("proveedores").select("nombre").eq("id", batch["proveedor_id"]).in_("user_id", ctx.user_ids_organizacion).maybe_single()).data or {}
        conv = sb.table("gmail_conversations").upsert({
            "user_id": ctx.actor_user_id, "gmail_thread_id": msg.get("threadId"),
            "proveedor_id": batch["proveedor_id"], "contacto_id": batch.get("contacto_id"),
            "proveedor_nombre": proveedor.get("nombre"),
            "proveedor_email": batch["destinatario_email"], "lista_proyecto_id": lista_id,
            "cotizacion_id": None, "resultado_id": None, "subject": batch["subject"],
            "estado": "sent", "last_message_at": now,
        }, on_conflict="user_id,gmail_thread_id").execute().data[0]
        sb.table("gmail_messages").upsert({
            "conversation_id": conv["id"], "gmail_message_id": msg.get("id"),
            "gmail_thread_id": msg.get("threadId"), "direction": "outbound",
            "from_email": integration["email"], "to_email": batch["destinatario_email"],
            "subject": batch["subject"], "body_text": batch["body"], "received_at": now, "procesado": True,
        }, on_conflict="gmail_message_id").execute()
        items = sb.table("rfq_batch_items").select("*").eq("rfq_batch_id", batch_id).execute().data or []
        try:
            from app.services.supplier_intelligence import registrar_solicitud
            registrar_solicitud(ctx.actor_user_id, proveedor.get("nombre") or "", batch["destinatario_email"])
        except Exception as e:
            print(f"[RFQ] supplier intelligence legacy: {e}")
        for item in items:
            sb.table("resultados").update({"solicitud_enviada_at": now, "estado": "contactado", "proveedor_email": batch["destinatario_email"]}).eq("id", item["resultado_id"]).execute()
            sb.table("rfq_batch_items").update({"estado": "sent", "updated_at": now}).eq("id", item["id"]).execute()
            cot = ejecutar_maybe_single(sb.table("cotizaciones").select("categoria").eq("id", item["cotizacion_id"]).maybe_single()).data or {}
            registrar_evento(ctx.actor_user_id, batch["proveedor_id"], "supplier_selected_for_rfq", resultado_id=item["resultado_id"], cotizacion_id=item["cotizacion_id"], categoria_confirmada=cot.get("categoria"), metadata={"rfq_batch_id": batch_id})
        sb.table("rfq_batches").update({
            "conversation_id": conv["id"], "gmail_message_id": msg.get("id"),
            "gmail_thread_id": msg.get("threadId"), "estado": "sent", "sent_at": now, "updated_at": now,
        }).eq("id", batch_id).execute()
    except Exception as e:
        sb.table("rfq_batches").update({"estado": "delivery_uncertain", "gmail_message_id": msg.get("id"), "gmail_thread_id": msg.get("threadId"), "error_detalle": str(e)[:1000], "updated_at": now}).eq("id", batch_id).execute()
        raise HTTPException(status_code=500, detail="El correo salió, pero falló su registro. No lo reenvíes; requiere revisión.")
    return {"success": True, "thread_id": msg.get("threadId"), "conversation_id": conv["id"]}
