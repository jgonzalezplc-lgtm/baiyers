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
        "magic_link_aprobar": f"{base}/authorize/{token}?decision=aprobar",
        "magic_link_rechazar": f"{base}/authorize/{token}?decision=rechazar",
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
    decision: str  # "aprobar" | "rechazar"
    comentario: Optional[str] = None


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

    if req.decision not in ("aprobar", "rechazar"):
        raise HTTPException(status_code=400, detail="decision debe ser 'aprobar' o 'rechazar'")

    res = sb.table("approval_requests").select("*").eq("token", token).limit(1).execute()
    row = (res.data or [None])[0]
    if not row:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada")
    if row["estado"] != "pendiente":
        raise HTTPException(status_code=409, detail=f"Solicitud ya está en estado '{row['estado']}'")
    if row.get("expira_at") and row["expira_at"] < _now():
        sb.table("approval_requests").update({"estado": "expirado"}).eq("id", row["id"]).execute()
        raise HTTPException(status_code=410, detail="El enlace de aprobación expiró")

    nuevo = "aprobado" if req.decision == "aprobar" else "rechazado"
    update_data: dict = {"estado": nuevo, "decidido_at": _now()}
    if req.comentario:
        update_data["comentario"] = req.comentario
    sb.table("approval_requests").update(update_data).eq("id", row["id"]).execute()

    # Si la referencia es un quote_supplier y fue aprobado, marcarlo seleccionado
    if nuevo == "aprobado" and row["referencia"].startswith("quote_supplier:"):
        qs_id = row["referencia"].split(":", 1)[1]
        try:
            sb.table("quote_suppliers").update({"estado": "seleccionado", "updated_at": _now()}).eq("id", qs_id).execute()
        except Exception:
            pass

    # Si la referencia es una lista, actualizar su estado de aprobación
    if row["referencia"].startswith("lista:"):
        import json
        lista_id = row["referencia"].split(":", 1)[1]
        try:
            proy = sb.table("proyectos").select("descripcion").eq("id", lista_id).single().execute()
            if proy.data:
                data = json.loads(proy.data.get("descripcion") or "{}")
                if data.get("tipo") == "lista_cotizacion":
                    aprobacion = data.get("aprobacion", {})
                    aprobacion["estado"] = nuevo
                    aprobacion["decidido_at"] = _now()
                    if req.comentario:
                        aprobacion["comentario_rechazo"] = req.comentario
                    data["aprobacion"] = aprobacion
                    sb.table("proyectos").update({
                        "descripcion": json.dumps(data, ensure_ascii=False),
                    }).eq("id", lista_id).execute()
        except Exception:
            pass

    return {"ok": True, "estado": nuevo}
