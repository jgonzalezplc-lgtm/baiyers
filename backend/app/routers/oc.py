import base64
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/oc", tags=["oc"])


class CrearOCRequest(BaseModel):
    cotizacion_id: str
    resultado_id: Optional[str] = None
    user_id: str
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
    user_id: str
    proveedor_nombre: str
    proveedor_email: Optional[str] = None
    numero_oc: str
    precio_total: float
    moneda: str = "CLP"


@router.post("/crear")
async def crear_oc(req: CrearOCRequest):
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
        "user_id": req.user_id,
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
    }


@router.post("/enviar")
async def enviar_oc(req: EnviarOCRequest):
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
    gmail_res = sb.table("user_integrations").select("*").eq("user_id", req.user_id).eq("provider", "gmail").single().execute()
    if not gmail_res.data:
        raise HTTPException(status_code=400, detail="Gmail no conectado")

    integration = gmail_res.data
    service, creds = get_gmail_service(integration["access_token"], integration["refresh_token"])

    if creds.token != integration["access_token"]:
        sb.table("user_integrations").update({"access_token": creds.token}).eq("user_id", req.user_id).eq("provider", "gmail").execute()

    token_oc = sb.table("ordenes_compra").select("token_confirmacion").eq("id", req.oc_id).single().execute().data["token_confirmacion"]
    confirm_url = f"{settings.frontend_url}/oc/confirmar/{token_oc}"
    total_fmt = f"${int(req.precio_total):,}".replace(",", ".")
    from_email = integration["email"]

    # Email al proveedor
    if req.proveedor_email:
        body_proveedor = (
            f"Estimado {req.proveedor_nombre},\n\n"
            f"Adjuntamos la Orden de Compra {req.numero_oc} por {total_fmt} {req.moneda}.\n\n"
            f"Para confirmar la recepción haga clic aquí:\n{confirm_url}\n\n"
            f"Saludos,\nEquipo Claria\nhola@claria.cc"
        )
        try:
            send_email_with_attachment(
                service=service,
                to=req.proveedor_email,
                subject=f"Orden de Compra {req.numero_oc} — Claria",
                body=body_proveedor,
                from_email=from_email,
                pdf_bytes=pdf_bytes,
                pdf_filename=f"{req.numero_oc}.pdf",
            )
        except Exception as e:
            print(f"[OC] Error enviando al proveedor: {e}")

    # Supplier Intelligence — registrar OC enviada
    try:
        from app.services.supplier_intelligence import registrar_oc_enviada
        registrar_oc_enviada(req.user_id, req.proveedor_nombre, req.proveedor_email)
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
