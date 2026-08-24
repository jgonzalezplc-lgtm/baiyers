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

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from app.services.auth_context import AuthContext, get_auth_context
from app.services.supabase import ejecutar_maybe_single

router = APIRouter(prefix="/api/aprobaciones", tags=["aprobaciones"])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _texto_notificacion_lista(decision: str, nombre: str, decidido_por: Optional[str] = None) -> tuple[str, str, str]:
    sufijo = f" — hecho por {decidido_por}" if decidido_por else ""
    if decision == "rechazar":
        return "cotizacion_rechazada", "Cotización rechazada", f"Se rechazó la lista '{nombre}'{sufijo}."
    if decision == "aprobar_con_observaciones":
        return "cotizacion_observada", "Cotización aprobada con observaciones", f"La lista '{nombre}' fue aprobada con observaciones{sufijo}."
    return "cotizacion_aprobada", "Cotización aprobada", f"Se aprobó la lista '{nombre}'{sufijo}."


# ─── Workflows ─────────────────────────────────────────────────────────────

class WorkflowRequest(BaseModel):
    nombre: str = "Flujo por defecto"
    pasos: list[dict] = []          # [{orden, rol, nombre, email}]
    monto_minimo: float = 0


@router.post("/workflows")
async def crear_workflow(req: WorkflowRequest, ctx: AuthContext = Depends(get_auth_context)):
    from app.services.supabase import get_supabase
    sb = get_supabase()
    ins = sb.table("approval_workflows").insert({
        "user_id": ctx.actor_user_id,
        "nombre": req.nombre,
        "pasos": req.pasos,
        "monto_minimo": req.monto_minimo,
    }).execute()
    return ins.data[0]


@router.get("/workflows")
async def listar_workflows(ctx: AuthContext = Depends(get_auth_context)):
    from app.services.supabase import get_supabase
    sb = get_supabase()
    res = sb.table("approval_workflows").select("*").in_("user_id", ctx.user_ids_organizacion).eq("activo", True).execute()
    return res.data or []


# ─── Solicitudes de aprobación ─────────────────────────────────────────────

class SolicitudRequest(BaseModel):
    referencia: str                  # "quote_supplier:<id>" | "oc:<id>"
    resumen: dict = {}               # snapshot de comparativa/OC para el correo
    aprobador_email: Optional[str] = None
    workflow_id: Optional[str] = None
    dias_expiracion: int = 7
    # Fase 4 — Workflow Builder: si esta solicitud nació de un ciclo de
    # compras activo (no del `approval_workflows` legado), queda atada al
    # nodo/instancia/responsable real que debe decidir.
    workflow_instance_id: Optional[str] = None
    workflow_nodo_id: Optional[str] = None
    responsable_id: Optional[str] = None


def _crear_solicitud_aprobacion(user_id: str, req: SolicitudRequest) -> dict:
    """Lógica real de /solicitar, separada del endpoint para poder llamarla
    directamente desde listas.py (_crear_y_enviar_solicitudes) sin pasar por
    la capa HTTP — ahí el `user_id` ya viene autorizado por el caller, así
    que no depende de AuthContext (que solo se resuelve en un request real)."""
    from app.config import settings
    from app.services.supabase import get_supabase
    sb = get_supabase()

    token = secrets.token_urlsafe(32)
    expira = (datetime.now(timezone.utc) + timedelta(days=req.dias_expiracion)).isoformat()

    ins = sb.table("approval_requests").insert({
        "user_id": user_id,
        "workflow_id": req.workflow_id,
        "referencia": req.referencia,
        "resumen": req.resumen,
        "token": token,
        "aprobador_email": req.aprobador_email,
        "expira_at": expira,
        "workflow_instance_id": req.workflow_instance_id,
        "workflow_nodo_id": req.workflow_nodo_id,
        "responsable_id": req.responsable_id,
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


@router.post("/solicitar")
async def solicitar_aprobacion(req: SolicitudRequest, ctx: AuthContext = Depends(get_auth_context)):
    """Crea la solicitud y devuelve el magic link para incluir en el correo."""
    return _crear_solicitud_aprobacion(ctx.actor_user_id, req)


@router.get("/solicitudes")
async def listar_solicitudes(estado: Optional[str] = None, ctx: AuthContext = Depends(get_auth_context)):
    from app.services.supabase import get_supabase
    sb = get_supabase()
    q = sb.table("approval_requests").select("*").in_("user_id", ctx.user_ids_organizacion)
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

    # Una decisión terminal detiene inmediatamente los recordatorios de esa
    # persona. Si el nodo completo se resuelve más abajo, se cancelan también
    # las demás acciones pendientes y se cierra su ejecución durable.
    if row.get("workflow_instance_id") and row.get("workflow_nodo_id"):
        try:
            from app.services.workflow_scheduler import cancelar_recordatorios_autorizacion
            cancelar_recordatorios_autorizacion(
                row["workflow_instance_id"], row["workflow_nodo_id"], row.get("responsable_id"),
            )
        except Exception as e:
            print(f"[Aprobaciones] cancelar recordatorio individual falló: {e}")

    # Fase 4 del Workflow Builder: si esta solicitud pertenece a un ciclo de
    # compras activo (varios responsables posibles, en paralelo o en orden),
    # el motor decide si el tramo ya quedó resuelto y, si falta gente por
    # decidir, esta llamada no debe finalizar la lista todavía. Las
    # decisiones "con observaciones" siguen siendo terminales de inmediato,
    # como en el flujo legado — no hay tramos "con observaciones".
    avance_pendiente = None
    es_decision_de_workflow = bool(row.get("workflow_instance_id")) and req.decision in ("aprobar", "rechazar") and not decisiones_items
    if es_decision_de_workflow:
        from app.services.workflow_execution import avanzar_tras_decision, registrar_evento
        try:
            registrar_evento(row["workflow_instance_id"], row["workflow_nodo_id"], row.get("responsable_id"), nuevo)
        except Exception as e:
            print(f"[Aprobaciones] registrar_evento falló: {e}")
        avance = avanzar_tras_decision({**row, **update_data})
        if not avance["resuelto"]:
            return {"ok": True, "estado": "pendiente", "mensaje": "Registrado. Falta que otros responsables de este tramo decidan."}
        try:
            from app.services.workflow_scheduler import (
                cancelar_recordatorios_autorizacion, completar_ejecucion_autorizacion,
            )
            cancelar_recordatorios_autorizacion(row["workflow_instance_id"], row["workflow_nodo_id"])
            completar_ejecucion_autorizacion(
                row["workflow_instance_id"], row["workflow_nodo_id"], avance["resultado"],
            )
        except Exception as e:
            print(f"[Aprobaciones] cierre de ejecución durable falló: {e}")
        if avance["resultado"] == "aprobado" and not avance["terminado"]:
            avance_pendiente = avance["siguiente"]
            nuevo = "aprobado"  # este tramo se resolvió aprobado; la lista sigue pendiente del próximo tramo

    from app.services.notificaciones import crear_notificacion

    # Acá vivía el manejo de referencias `quote_supplier:`. Sólo `procurement.py`
    # podía crearlas, y ese router se eliminó junto con sus tablas
    # (`quote_items`/`quote_suppliers`/`purchase_events`, que nunca llegaron a
    # existir en producción), así que la rama era inalcanzable.

    # Si la referencia es una lista, actualizar su estado de aprobación
    if row["referencia"].startswith("lista:"):
        import json
        lista_id = row["referencia"].split(":", 1)[1]
        try:
            proy = sb.table("proyectos").select("nombre, descripcion, user_id").eq("id", lista_id).single().execute()
            if proy.data:
                data = json.loads(proy.data.get("descripcion") or "{}")
                if data.get("tipo") == "lista_cotizacion" and avance_pendiente:
                    if avance_pendiente.get("tipo") == "emision_oc":
                        aprobacion = data.get("aprobacion", {})
                        aprobacion.update({
                            "estado": "aprobado", "nodo_actual_id": avance_pendiente["nodo_id"],
                            "nodo_actual_nombre": avance_pendiente["nodo_nombre"], "decidido_at": _now(),
                        })
                        data["aprobacion"] = aprobacion
                        sb.table("proyectos").update({
                            "descripcion": json.dumps(data, ensure_ascii=False),
                        }).eq("id", lista_id).execute()
                        return {"ok": True, "estado": "aprobado", "nodo_actual_nombre": avance_pendiente["nodo_nombre"]}
                    if avance_pendiente.get("tipo") == "homologacion":
                        from app.services.workflow_homologation import iniciar_homologacion
                        resultado_ids = [
                            d["resultado_id"] for d in (data.get("definitivos") or {}).values()
                            if d.get("resultado_id")
                        ]
                        try:
                            inicio = iniciar_homologacion(
                                proy.data["user_id"], lista_id, resultado_ids, avance_pendiente,
                            )
                        except Exception as e:
                            sb.table("workflow_instances").update({
                                "estado_workflow": "pausado",
                            }).eq("id", avance_pendiente["workflow_instance_id"]).execute()
                            return {
                                "ok": True, "estado": "homologacion_pausada",
                                "mensaje": f"La compra fue aprobada, pero la homologación requiere intervención: {e}",
                            }
                        aprobacion = data.get("aprobacion", {})
                        aprobacion.update({
                            "estado": "homologacion", "nodo_actual_id": avance_pendiente["nodo_id"],
                            "nodo_actual_nombre": avance_pendiente["nodo_nombre"],
                        })
                        data["aprobacion"] = aprobacion
                        sb.table("proyectos").update({
                            "descripcion": json.dumps(data, ensure_ascii=False),
                        }).eq("id", lista_id).execute()
                        return {"ok": True, "estado": "homologacion", "casos": inicio["casos"]}
                    # Este tramo aprobó, pero el workflow exige otro más
                    # (ej: jefe directo → finanzas). No finalizar: notificar
                    # al siguiente tramo y dejar la lista pendiente.
                    aprobacion = data.get("aprobacion", {})
                    aprobacion["estado"] = "pendiente"
                    aprobacion["nodo_actual_id"] = avance_pendiente["nodo_id"]
                    aprobacion["nodo_actual_nombre"] = avance_pendiente["nodo_nombre"]
                    aprobacion["aprobadores_pendientes"] = [
                        {"responsable_id": r["id"], "nombre": r["nombre"], "email": r["email"]}
                        for r in avance_pendiente["responsables_a_notificar"]
                    ]
                    data["aprobacion"] = aprobacion
                    sb.table("proyectos").update({
                        "descripcion": json.dumps(data, ensure_ascii=False),
                    }).eq("id", lista_id).execute()

                    resumen_previo = row.get("resumen") or {}
                    lista_nombre = proy.data.get("nombre") or "cotización"
                    from app.routers.listas import _crear_y_enviar_solicitudes
                    await _crear_y_enviar_solicitudes(sb, proy.data["user_id"], lista_id, lista_nombre, resumen_previo, avance_pendiente)
                    return {"ok": True, "estado": "pendiente", "nodo_actual_nombre": avance_pendiente["nodo_nombre"]}

                if data.get("tipo") == "lista_cotizacion":
                    aprobacion = data.get("aprobacion", {})
                    aprobacion["estado"] = "aprobado_con_observaciones" if req.decision == "aprobar_con_observaciones" else nuevo
                    if req.decision == "aprobar_con_observaciones":
                        aprobacion["resultado"] = "aprobado_con_observaciones"
                    aprobacion["decidido_at"] = _now()
                    # "Hecho por X": si la solicitud está atada a un responsable
                    # real (Fase 4 del Workflow Builder) queda su nombre; si no,
                    # el email al que se le envió (flujo legado).
                    decidido_por = row.get("aprobador_email")
                    if row.get("responsable_id"):
                        resp = ejecutar_maybe_single(sb.table("responsables").select("nombre").eq("id", row["responsable_id"]).maybe_single()).data
                        if resp and resp.get("nombre"):
                            decidido_por = resp["nombre"]
                    aprobacion["decidido_por"] = decidido_por
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
                    tipo_notificacion, titulo, cuerpo = _texto_notificacion_lista(req.decision, lista_nombre, aprobacion.get("decidido_por"))
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
                            print(f"[Aprobaciones] inicio de compra agrupado (Gmail) falló: {e}")
                        try:
                            # Un proveedor puede haber respondido por Gmail y
                            # otro por Outlook en la misma lista — cada agente
                            # sólo actúa sobre las conversaciones que él mismo
                            # abrió, así que ambas llamadas conviven sin pisarse.
                            from app.services.outlook_conversation_agent import iniciar_proceso_compra_resultados as iniciar_proceso_compra_resultados_outlook
                            iniciar_proceso_compra_resultados_outlook(proy.data["user_id"], resultado_ids)
                        except Exception as e:
                            print(f"[Aprobaciones] inicio de compra agrupado (Outlook) falló: {e}")
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
