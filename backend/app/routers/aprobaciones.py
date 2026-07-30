"""
Flujo de aprobaciones con magic link (Fase 6, Smart Procurement).

- approval_workflows: define la cadena de aprobación por empresa/usuario.
- approval_requests: solicitud con token único; el aprobador decide desde el
  correo vía GET /api/aprobaciones/authorize/{token}?decision=aprobar|rechazar
  (magic link, sin login). El envío del correo usa el Gmail OAuth existente
  desde el frontend.
"""
import secrets
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

router = APIRouter(prefix="/api/aprobaciones", tags=["aprobaciones"])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _texto_notificacion_lista(decision: str, nombre: str) -> tuple[str, str, str]:
    if decision == "rechazar":
        return "cotizacion_rechazada", "Cotización rechazada", f"Se rechazó la lista '{nombre}'."
    if decision == "aprobar_con_observaciones":
        return "cotizacion_observada", "Cotización aprobada con observaciones", f"La lista '{nombre}' fue aprobada con observaciones."
    return "cotizacion_aprobada", "Cotización aprobada", f"Se aprobó la lista '{nombre}'."


# ─── Workflows ─────────────────────────────────────────────────────────────

class WorkflowRequest(BaseModel):
    user_id: str
    nombre: str = "Flujo por defecto"
    pasos: list[dict] = []          # [{orden, rol, nombre, email}]
    monto_minimo: float = 0


@router.post("/workflows")
async def crear_workflow(req: WorkflowRequest):
    from app.services.supabase import get_supabase
    sb = get_supabase()
    ins = sb.table("approval_workflows").insert({
        "user_id": req.user_id,
        "nombre": req.nombre,
        "pasos": req.pasos,
        "monto_minimo": req.monto_minimo,
    }).execute()
    return ins.data[0]


@router.get("/workflows")
async def listar_workflows(user_id: str):
    from app.services.supabase import get_supabase
    sb = get_supabase()
    res = sb.table("approval_workflows").select("*").eq("user_id", user_id).eq("activo", True).execute()
    return res.data or []


# ─── Solicitudes de aprobación ─────────────────────────────────────────────

class SolicitudRequest(BaseModel):
    user_id: str
    referencia: str                  # "quote_supplier:<id>" | "oc:<id>"
    resumen: dict = {}               # snapshot de comparativa/OC para el correo
    aprobador_email: Optional[str] = None
    workflow_id: Optional[str] = None
    dias_expiracion: int = 7


@router.post("/solicitar")
async def solicitar_aprobacion(req: SolicitudRequest):
    """Crea la solicitud y devuelve el magic link para incluir en el correo."""
    from app.config import settings
    from app.services.supabase import get_supabase
    sb = get_supabase()

    token = secrets.token_urlsafe(32)
    expira = (datetime.now(timezone.utc) + timedelta(days=req.dias_expiracion)).isoformat()

    ins = sb.table("approval_requests").insert({
        "user_id": req.user_id,
        "workflow_id": req.workflow_id,
        "referencia": req.referencia,
        "resumen": req.resumen,
        "token": token,
        "aprobador_email": req.aprobador_email,
        "expira_at": expira,
    }).execute()

    base = settings.frontend_url.rstrip("/")
    return {
        "id": ins.data[0]["id"],
        "token": token,
        # Un solo link: la página /authorize/{token} ya deja elegir aprobar,
        # aprobar con observaciones o rechazar (con comentario) desde ahí.
        "magic_link": f"{base}/authorize/{token}",
        "expira_at": expira,
    }


@router.get("/solicitudes")
async def listar_solicitudes(user_id: str, estado: Optional[str] = None):
    from app.services.supabase import get_supabase
    sb = get_supabase()
    q = sb.table("approval_requests").select("*").eq("user_id", user_id)
    if estado:
        q = q.eq("estado", estado)
    res = q.order("created_at", desc=True).limit(100).execute()
    return res.data or []


# ─── Magic link — decisión sin login ───────────────────────────────────────

class DecisionRequest(BaseModel):
    decision: str  # "aprobar" | "aprobar_con_observaciones" | "rechazar"
    comentario: Optional[str] = None
    # Para listas, una decisión por ítem. Se guarda dentro del snapshot para no
    # requerir una tabla nueva y para que el historial sea inmutable.
    item_decisions: dict[str, dict] = {}


@router.get("/token/{token}")
async def info_token(token: str):
    """El frontend /authorize/{token} consulta esto para mostrar el resumen."""
    from app.services.supabase import get_supabase
    sb = get_supabase()
    res = sb.table("approval_requests").select(
        "id, referencia, resumen, estado, aprobador_email, expira_at, created_at"
    ).eq("token", token).limit(1).execute()
    row = (res.data or [None])[0]
    if not row:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada")
    if row["estado"] == "pendiente" and row.get("expira_at") and row["expira_at"] < _now():
        sb.table("approval_requests").update({"estado": "expirado"}).eq("id", row["id"]).execute()
        row["estado"] = "expirado"
    return row


@router.post("/token/{token}/decidir")
async def decidir(token: str, req: DecisionRequest):
    from app.services.supabase import get_supabase
    sb = get_supabase()

    if req.decision not in ("aprobar", "aprobar_con_observaciones", "rechazar"):
        raise HTTPException(status_code=400, detail="Decisión inválida")

    res = sb.table("approval_requests").select("*").eq("token", token).limit(1).execute()
    row = (res.data or [None])[0]
    if not row:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada")
    if row["estado"] != "pendiente":
        raise HTTPException(status_code=409, detail=f"Solicitud ya está en estado '{row['estado']}'")
    if row.get("expira_at") and row["expira_at"] < _now():
        sb.table("approval_requests").update({"estado": "expirado"}).eq("id", row["id"]).execute()
        raise HTTPException(status_code=410, detail="El enlace de aprobación expiró")

    decisiones_items = req.item_decisions or {}
    # Los rechazos por ítem son observaciones de una aprobación parcial. El
    # solicitante corrige sólo esos ítems y vuelve a enviar la lista.
    hay_rechazados = any(d.get("estado") == "rechazado" for d in decisiones_items.values())
    if hay_rechazados and req.decision == "aprobar":
        raise HTTPException(status_code=400, detail="Hay ítems rechazados: envía 'Aprobar con observaciones'")
    nuevo = "rechazado" if req.decision == "rechazar" else "aprobado"
    update_data: dict = {"estado": nuevo, "decidido_at": _now()}
    if req.comentario:
        update_data["comentario"] = req.comentario
    if decisiones_items:
        resumen = row.get("resumen") or {}
        resumen["decisiones_items"] = decisiones_items
        if req.decision == "aprobar_con_observaciones":
            resumen["resultado"] = "aprobado_con_observaciones"
        update_data["resumen"] = resumen
    elif req.decision == "aprobar_con_observaciones":
        resumen = row.get("resumen") or {}
        resumen["resultado"] = "aprobado_con_observaciones"
        update_data["resumen"] = resumen
    sb.table("approval_requests").update(update_data).eq("id", row["id"]).execute()

    from app.services.notificaciones import crear_notificacion

    # Si la referencia es un quote_supplier y fue aprobado, marcarlo seleccionado
    if nuevo == "aprobado" and row["referencia"].startswith("quote_supplier:"):
        qs_id = row["referencia"].split(":", 1)[1]
        try:
            sb.table("quote_suppliers").update({"estado": "seleccionado", "updated_at": _now()}).eq("id", qs_id).execute()
            qs = sb.table("quote_suppliers").select("proveedor_nombre, quote_item_id").eq("id", qs_id).maybe_single().execute()
            if qs.data and row.get("user_id"):
                item_nombre = qs.data.get("proveedor_nombre") or "ítem"
                if qs.data.get("quote_item_id"):
                    it = sb.table("quote_items").select("nombre").eq("id", qs.data["quote_item_id"]).maybe_single().execute()
                    item_nombre = (it.data or {}).get("nombre") or item_nombre
                proveedor_nombre = qs.data.get("proveedor_nombre") or "proveedor"
                crear_notificacion(
                    sb, row["user_id"], "cotizacion_aprobada",
                    "Cotización aprobada",
                    f"Se aprobó {proveedor_nombre} para '{item_nombre}'.",
                    {"quote_supplier_id": qs_id, "proveedor_nombre": proveedor_nombre, "item_nombre": item_nombre},
                )
        except Exception:
            pass

    # Si la referencia es una lista, actualizar su estado de aprobación
    if row["referencia"].startswith("lista:"):
        import json
        lista_id = row["referencia"].split(":", 1)[1]
        try:
            proy = sb.table("proyectos").select("nombre, descripcion, user_id").eq("id", lista_id).single().execute()
            if proy.data:
                data = json.loads(proy.data.get("descripcion") or "{}")
                if data.get("tipo") == "lista_cotizacion":
                    aprobacion = data.get("aprobacion", {})
                    aprobacion["estado"] = "aprobado_con_observaciones" if req.decision == "aprobar_con_observaciones" else nuevo
                    if req.decision == "aprobar_con_observaciones":
                        aprobacion["resultado"] = "aprobado_con_observaciones"
                    aprobacion["decidido_at"] = _now()
                    if decisiones_items:
                        aprobacion["decisiones_items"] = decisiones_items
                        aprobacion["observaciones_items"] = {
                            item_id: decision.get("motivo", "")
                            for item_id, decision in decisiones_items.items()
                            if decision.get("estado") == "rechazado"
                        }
                    if req.comentario:
                        aprobacion["comentario_observaciones" if req.decision == "aprobar_con_observaciones" else "comentario_rechazo"] = req.comentario
                    data["aprobacion"] = aprobacion
                    sb.table("proyectos").update({
                        "descripcion": json.dumps(data, ensure_ascii=False),
                    }).eq("id", lista_id).execute()

                    lista_nombre = proy.data.get("nombre") or "cotización"
                    tipo_notificacion, titulo, cuerpo = _texto_notificacion_lista(req.decision, lista_nombre)
                    crear_notificacion(
                        sb, proy.data["user_id"], tipo_notificacion,
                        titulo,
                        cuerpo,
                        {"lista_id": lista_id, "lista_nombre": lista_nombre},
                    )

                    # Aprobación limpia (sin observaciones): el proveedor
                    # elegido para cada ítem queda seleccionado y autorizado
                    # → el agente arranca la etapa de compra por correo.
                    if req.decision == "aprobar":
                        resultado_ids = [
                            d["resultado_id"] for d in (data.get("definitivos") or {}).values()
                            if d.get("resultado_id")
                        ]
                        try:
                            from app.services.gmail_conversation_agent import iniciar_proceso_compra_resultados
                            iniciar_proceso_compra_resultados(proy.data["user_id"], resultado_ids)
                        except Exception as e:
                            print(f"[Aprobaciones] inicio de compra agrupado falló: {e}")
                        try:
                            from app.services.supplier_capability_intelligence import registrar_evento_para_resultado
                            for resultado_id in resultado_ids:
                                registrar_evento_para_resultado(
                                    proy.data["user_id"], resultado_id, "purchase_approved", {"lista_id": lista_id},
                                )
                        except Exception as e:
                            print(f"[Aprobaciones] evidencia de aprobación falló: {e}")
        except Exception:
            pass

    estado_publico = "aprobado_con_observaciones" if req.decision == "aprobar_con_observaciones" else nuevo
    return {"ok": True, "estado": estado_publico}
