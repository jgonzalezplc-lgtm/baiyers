import base64
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.services.auth_context import AuthContext, get_auth_context

router = APIRouter(prefix="/api/oc", tags=["oc"])


def _registrar_conversacion_oc(sb, req, user_id: str, mi_email: str, msg: dict, subject: str, body: str) -> None:
    """Engancha el envío de la OC al agente de Gmail (mismo mecanismo que las
    cotizaciones): así el cron que ya lee respuestas cada 1 min también
    detecta el acuse de recibo o el aviso de despacho de esta OC. No bloquea
    el envío si falla — la OC ya salió, esto es solo para el seguimiento."""
    from datetime import datetime, timezone as _tz
    try:
        from app.services.proveedores_matching import resolver_o_crear_proveedor, resolver_o_crear_contacto
        thread_id = msg.get("threadId")
        now_iso = datetime.now(_tz.utc).isoformat()
        proveedor_id = resolver_o_crear_proveedor(sb, user_id, req.proveedor_nombre or req.proveedor_email, req.proveedor_email)
        contacto_id = resolver_o_crear_contacto(sb, user_id, proveedor_id, req.proveedor_email, origen="gmail_agent")

        conv = sb.table("gmail_conversations").upsert({
            "user_id": user_id,
            "gmail_thread_id": thread_id,
            "proveedor_id": proveedor_id,
            "contacto_id": contacto_id,
            "proveedor_nombre": req.proveedor_nombre or None,
            "proveedor_email": req.proveedor_email,
            "oc_id": req.oc_id,
            "subject": subject,
            "estado": "sent",
            "tipo": "compra",
            "last_message_at": now_iso,
        }, on_conflict="user_id,gmail_thread_id").execute()
        conversation_id = conv.data[0]["id"]
        sb.table("gmail_messages").upsert({
            "conversation_id": conversation_id,
            "gmail_message_id": msg.get("id"),
            "gmail_thread_id": thread_id,
            "direction": "outbound",
            "from_email": mi_email,
            "to_email": req.proveedor_email,
            "subject": subject,
            "body_text": body,
            "received_at": now_iso,
            "procesado": True,
        }, on_conflict="gmail_message_id").execute()
    except Exception as e:
        print(f"[OC] No se pudo registrar la conversación para seguimiento: {e}")


class CrearOCRequest(BaseModel):
    cotizacion_id: str
    resultado_id: Optional[str] = None
    nombre_item: str
    proveedor_nombre: str
    proveedor_email: Optional[str] = None
    cantidad: int = 1
    precio_unitario: float
    moneda: str = "CLP"
    condiciones_pago: str = "30 días"
    plazo_entrega: str = ""
    notas: Optional[str] = None


class EnviarOCRequest(BaseModel):
    oc_id: str
    pdf_base64: str
    proveedor_nombre: str
    proveedor_email: Optional[str] = None
    numero_oc: str
    precio_total: float
    moneda: str = "CLP"


@router.post("/crear")
async def crear_oc(req: CrearOCRequest, ctx: AuthContext = Depends(get_auth_context)):
    from app.services.supabase import get_supabase

    sb = get_supabase()

    # Correlativo por año
    year = datetime.now().year
    res = sb.table("ordenes_compra").select("numero_oc").like("numero_oc", f"OC-{year}-%").execute()
    correlativo = len(res.data) + 1
    numero_oc = f"OC-{year}-{correlativo:04d}"

    subtotal = req.cantidad * req.precio_unitario
    iva = round(subtotal * 0.19, 0)
    total = subtotal + iva

    token = str(uuid.uuid4())

    row = {
        "cotizacion_id": req.cotizacion_id if req.cotizacion_id != "demo" else None,
        "resultado_id": req.resultado_id,
        "user_id": ctx.actor_user_id,
        "numero_oc": numero_oc,
        "estado": "borrador",
        "precio_total": total,
        "moneda": req.moneda,
        "condiciones_pago": req.condiciones_pago,
        "plazo_entrega": req.plazo_entrega,
        "token_confirmacion": token,
        # Columnas extra (requieren ALTER TABLE — ver instrucciones)
        "nombre_item": req.nombre_item[:200],
        "proveedor_nombre": req.proveedor_nombre[:200],
        "proveedor_email": req.proveedor_email,
        "cantidad": req.cantidad,
        "precio_unitario": req.precio_unitario,
        "notas": req.notas,
    }

    try:
        insert_res = sb.table("ordenes_compra").insert(row).execute()
        oc_id = insert_res.data[0]["id"]
    except Exception as e:
        # Si fallan las columnas extra, reintenta sin ellas
        row_base = {k: v for k, v in row.items() if k not in ("nombre_item", "proveedor_nombre", "proveedor_email", "cantidad", "precio_unitario", "notas")}
        insert_res = sb.table("ordenes_compra").insert(row_base).execute()
        oc_id = insert_res.data[0]["id"]

    from app.services.organizacion import obtener_perfil_organizacion
    perfil = obtener_perfil_organizacion(ctx.organization_id)

    return {
        "id": oc_id,
        "numero_oc": numero_oc,
        "token_confirmacion": token,
        "nombre_item": req.nombre_item,
        "proveedor_nombre": req.proveedor_nombre,
        "proveedor_email": req.proveedor_email,
        "cantidad": req.cantidad,
        "precio_unitario": req.precio_unitario,
        "moneda": req.moneda,
        "subtotal": subtotal,
        "iva": iva,
        "total": total,
        "condiciones_pago": req.condiciones_pago,
        "plazo_entrega": req.plazo_entrega,
        "notas": req.notas,
        "fecha": datetime.now().strftime("%d/%m/%Y"),
        "emisor_nombre": perfil.get("nombre"),
        "emisor_rut": perfil.get("rut"),
        "emisor_direccion": perfil.get("direccion"),
        "emisor_logo_url": perfil.get("logo_url"),
    }


@router.post("/enviar")
async def enviar_oc(req: EnviarOCRequest, ctx: AuthContext = Depends(get_auth_context)):
    from app.services.supabase import get_supabase
    from app.services.gmail_service import get_gmail_service, send_email_with_attachment, send_email
    from app.config import settings

    sb = get_supabase()

    pdf_bytes = base64.b64decode(req.pdf_base64)

    # Subir PDF a Supabase Storage
    filename = f"{req.oc_id}.pdf"
    pdf_url = None
    try:
        sb.storage.from_("ordenes-compra").upload(
            filename,
            pdf_bytes,
            {"content-type": "application/pdf", "upsert": "true"},
        )
        pdf_url = sb.storage.from_("ordenes-compra").get_public_url(filename)
    except Exception as e:
        print(f"[Storage] Error subiendo PDF: {e}")

    # Actualizar OC
    sb.table("ordenes_compra").update({
        "pdf_url": pdf_url,
        "estado": "enviada",
    }).eq("id", req.oc_id).execute()

    # Tokens Gmail
    gmail_res = sb.table("user_integrations").select("*").eq("user_id", ctx.actor_user_id).eq("provider", "gmail").single().execute()
    if not gmail_res.data:
        raise HTTPException(status_code=400, detail="Gmail no conectado")

    integration = gmail_res.data
    service, creds = get_gmail_service(integration["access_token"], integration["refresh_token"])

    if creds.token != integration["access_token"]:
        sb.table("user_integrations").update({"access_token": creds.token}).eq("user_id", ctx.actor_user_id).eq("provider", "gmail").execute()

    token_oc = sb.table("ordenes_compra").select("token_confirmacion").eq("id", req.oc_id).single().execute().data["token_confirmacion"]
    confirm_url = f"{settings.frontend_url}/oc/confirmar/{token_oc}"
    total_fmt = f"${int(req.precio_total):,}".replace(",", ".")
    from_email = integration["email"]

    from app.services.mail_template_service import render, registrar_envio
    from app.services.organizacion import obtener_perfil_organizacion
    empresa_nombre = obtener_perfil_organizacion(ctx.organization_id).get("nombre") or "Baiyer"

    # Email al proveedor — pide el acuse de recibo por el mismo correo (lo
    # normal para un proveedor real); el link de confirmación queda solo como
    # alternativa para quien prefiera no responder por texto.
    if req.proveedor_email:
        renderizado = render("purchase_order_sent", {
            "proveedor_nombre": req.proveedor_nombre,
            "numero_oc": req.numero_oc,
            "empresa_nombre": empresa_nombre,
            "monto": total_fmt,
            "moneda": req.moneda,
            "link_confirmacion": confirm_url,
        }, organizacion_id=ctx.organization_id)
        subject_proveedor, body_proveedor = renderizado["subject"], renderizado["body"]
        try:
            msg = send_email_with_attachment(
                service=service,
                to=req.proveedor_email,
                subject=subject_proveedor,
                body=body_proveedor,
                from_email=from_email,
                pdf_bytes=pdf_bytes,
                pdf_filename=f"{req.numero_oc}.pdf",
            )
            _registrar_conversacion_oc(sb, req, ctx.actor_user_id, integration["email"], msg, subject_proveedor, body_proveedor)
            try:
                registrar_envio(
                    ctx.organization_id, "purchase_order_sent", req.proveedor_email,
                    f"purchase_order_sent:{req.oc_id}", estado="enviado",
                )
            except Exception as e:
                print(f"[OC] registrar_envio falló (correo ya enviado, solo auditoría): {e}")
        except Exception as e:
            print(f"[OC] Error enviando al proveedor: {e}")

    # Supplier Intelligence — registrar OC enviada
    try:
        from app.services.supplier_intelligence import registrar_oc_enviada
        registrar_oc_enviada(ctx.actor_user_id, req.proveedor_nombre, req.proveedor_email)
    except Exception as e:
        print(f"[OC] SI oc_enviada error: {e}")

    # Copia al comprador
    try:
        send_email_with_attachment(
            service=service,
            to=from_email,
            subject=f"[Copia] OC {req.numero_oc} enviada a {req.proveedor_nombre}",
            body=f"Tu OC {req.numero_oc} fue enviada a {req.proveedor_nombre} ({req.proveedor_email or 'sin email'}).",
            from_email=from_email,
            pdf_bytes=pdf_bytes,
            pdf_filename=f"{req.numero_oc}.pdf",
        )
    except Exception as e:
        print(f"[OC] Error enviando copia: {e}")

    return {"success": True, "numero_oc": req.numero_oc, "pdf_url": pdf_url}


@router.get("/info/{token}")
async def info_oc(token: str):
    from app.services.supabase import get_supabase

    sb = get_supabase()
    res = sb.table("ordenes_compra").select("*").eq("token_confirmacion", token).single().execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="OC no encontrada")

    oc = res.data
    return {
        "numero_oc": oc["numero_oc"],
        "estado": oc["estado"],
        "precio_total": oc["precio_total"],
        "moneda": oc["moneda"],
        "condiciones_pago": oc.get("condiciones_pago"),
        "plazo_entrega": oc.get("plazo_entrega"),
        "nombre_item": oc.get("nombre_item", ""),
        "proveedor_nombre": oc.get("proveedor_nombre", ""),
        "cantidad": oc.get("cantidad", 1),
        "precio_unitario": oc.get("precio_unitario"),
        "created_at": oc["created_at"],
        "confirmada_at": oc.get("confirmada_at"),
    }


@router.post("/confirmar/{token}")
async def confirmar_oc(token: str):
    from app.services.supabase import get_supabase
    from app.services.gmail_service import get_gmail_service, send_email

    sb = get_supabase()
    res = sb.table("ordenes_compra").select("*").eq("token_confirmacion", token).single().execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="OC no encontrada o token inválido")

    oc = res.data

    if oc["estado"] == "confirmada":
        return {"success": True, "numero_oc": oc["numero_oc"], "ya_confirmada": True}

    now_iso = datetime.now(timezone.utc).isoformat()
    sb.table("ordenes_compra").update({
        "estado": "confirmada",
        "confirmada_at": now_iso,
    }).eq("id", oc["id"]).execute()

    # Supplier Intelligence
    try:
        from app.services.supplier_intelligence import registrar_oc_confirmada, programar_rating
        registrar_oc_confirmada(oc["id"])
        programar_rating(oc["id"])
    except Exception as e:
        print(f"[OC] SI error: {e}")

    # Notificar al comprador
    try:
        gmail_res = sb.table("user_integrations").select("*").eq("user_id", oc["user_id"]).eq("provider", "gmail").single().execute()
        if gmail_res.data:
            integration = gmail_res.data
            service, _ = get_gmail_service(integration["access_token"], integration["refresh_token"])
            proveedor_nombre = oc.get("proveedor_nombre", "El proveedor")
            numero_oc = oc["numero_oc"]
            send_email(
                service=service,
                to=integration["email"],
                subject=f"✓ {proveedor_nombre} confirmó tu OC {numero_oc}",
                body=f"{proveedor_nombre} confirmó la recepción de la Orden de Compra {numero_oc}.\n\nFecha: {datetime.now().strftime('%d/%m/%Y %H:%M')}",
                from_email=integration["email"],
            )
    except Exception as e:
        print(f"[OC] Error notificando comprador: {e}")

    return {
        "success": True,
        "numero_oc": oc["numero_oc"],
        "proveedor_nombre": oc.get("proveedor_nombre", ""),
        "ya_confirmada": False,
    }
