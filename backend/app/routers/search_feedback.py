"""
Sesiones de búsqueda y feedback explícito (Fase 1 de Supplier Capability
Intelligence). Envuelve el buscador existente (/api/buscar, /api/buscar/stream,
/api/refinar-busqueda) con trazabilidad auditable — no reemplaza ni cambia esos
endpoints.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from app.services.auth_context import AuthContext, get_auth_context
from app.services.supabase import ejecutar_maybe_single

router = APIRouter(prefix="/api/buscar/sesiones", tags=["search-feedback"])


class CrearSesionRequest(BaseModel):
    cotizacion_id: Optional[str] = None
    lista_proyecto_id: Optional[str] = None
    item_nombre: Optional[str] = None
    categoria_predicha: Optional[str] = None
    categorias_usadas: list[str] = Field(default_factory=list)
    terminos: list[str] = Field(default_factory=list)
    modo: str = "directed"  # "directed" | "expanded"
    session_padre_id: Optional[str] = None


@router.post("")
async def crear_sesion(req: CrearSesionRequest, ctx: AuthContext = Depends(get_auth_context)):
    from app.services.supabase import get_supabase
    sb = get_supabase()

    if req.modo not in ("directed", "expanded"):
        raise HTTPException(status_code=400, detail="modo debe ser 'directed' o 'expanded'")

    ins = sb.table("search_sessions").insert({
        "user_id": ctx.actor_user_id,
        "cotizacion_id": req.cotizacion_id,
        "lista_proyecto_id": req.lista_proyecto_id,
        "item_nombre": req.item_nombre,
        "categoria_predicha": req.categoria_predicha,
        "categorias_usadas": req.categorias_usadas,
        "terminos": req.terminos,
        "modo": req.modo,
        "session_padre_id": req.session_padre_id,
    }).execute()
    return ins.data[0]


class CerrarSesionRequest(BaseModel):
    n_resultados: int


@router.post("/{session_id}/cerrar")
async def cerrar_sesion(session_id: str, req: CerrarSesionRequest, ctx: AuthContext = Depends(get_auth_context)):
    """El frontend la llama cuando el buscador termina, para dejar cuántos
    resultados trajo (evidencia de contexto para el feedback que venga después)."""
    from app.services.supabase import get_supabase
    sb = get_supabase()
    sb.table("search_sessions").update({
        "n_resultados": req.n_resultados,
    }).eq("id", session_id).eq("user_id", ctx.actor_user_id).execute()
    return {"success": True}


class FeedbackRequest(BaseModel):
    tipo: str  # wrong_products | missing_suppliers | wrong_category | expand_search | satisfactory
    categoria_predicha: Optional[str] = None
    categoria_corregida: Optional[str] = None
    comentario: Optional[str] = None


_TIPOS_VALIDOS = {"wrong_products", "missing_suppliers", "wrong_category", "expand_search", "satisfactory"}
_ESTADO_POR_TIPO = {
    "satisfactory": "satisfactoria",
    "expand_search": "expandida",
}


class PrepararComplementariaRequest(BaseModel):
    cotizacion_id: str
    lista_proyecto_id: Optional[str] = None
    comentario: str = "Faltan proveedores de confianza; iniciar búsqueda complementaria"


@router.post("/complementaria/preparar")
async def preparar_busqueda_complementaria(
    req: PrepararComplementariaRequest, ctx: AuthContext = Depends(get_auth_context),
):
    """Registra una expansión explícita sobre la última búsqueda dirigida del
    ítem. Es idempotente para el mismo comentario/sesión y devuelve el padre
    que deberá enlazar la nueva search_session de modo expanded."""
    from app.services.supabase import get_supabase
    sb = get_supabase()
    q = (
        sb.table("search_sessions").select("id,categoria_predicha")
        .eq("user_id", ctx.actor_user_id).eq("cotizacion_id", req.cotizacion_id)
        .eq("modo", "directed").order("created_at", desc=True).limit(1).execute().data or []
    )
    if not q:
        return {"session_padre_id": None, "feedback_registrado": False}
    sesion = q[0]
    existentes = (
        sb.table("search_feedback").select("id")
        .eq("session_id", sesion["id"]).eq("user_id", ctx.actor_user_id)
        .eq("tipo", "missing_suppliers").eq("comentario", req.comentario).limit(1).execute().data or []
    )
    if not existentes:
        sb.table("search_feedback").insert({
            "session_id": sesion["id"], "user_id": ctx.actor_user_id,
            "tipo": "missing_suppliers", "categoria_predicha": sesion.get("categoria_predicha"),
            "comentario": req.comentario,
        }).execute()
    sb.table("search_sessions").update({"estado": "expandida"}).eq("id", sesion["id"]).execute()
    return {"session_padre_id": sesion["id"], "feedback_registrado": not bool(existentes)}


@router.post("/{session_id}/feedback")
async def registrar_feedback(session_id: str, req: FeedbackRequest, ctx: AuthContext = Depends(get_auth_context)):
    """'No encontré lo que buscaba' y variantes (categoría equivocada, faltan
    proveedores, quiero ampliar) caen todas acá. Es la señal fuerte y
    explícita que el spec pide priorizar sobre lo inferido."""
    from app.services.supabase import get_supabase
    sb = get_supabase()

    if req.tipo not in _TIPOS_VALIDOS:
        raise HTTPException(status_code=400, detail=f"tipo inválido: {req.tipo}")

    sesion = ejecutar_maybe_single(sb.table("search_sessions").select("id, user_id, categoria_predicha").eq("id", session_id).maybe_single()).data
    if not sesion or sesion["user_id"] != ctx.actor_user_id:
        raise HTTPException(status_code=404, detail="Sesión no encontrada")

    ins = sb.table("search_feedback").insert({
        "session_id": session_id,
        "user_id": ctx.actor_user_id,
        "tipo": req.tipo,
        "categoria_predicha": req.categoria_predicha or sesion.get("categoria_predicha"),
        "categoria_corregida": req.categoria_corregida,
        "comentario": req.comentario,
    }).execute()

    nuevo_estado = _ESTADO_POR_TIPO.get(req.tipo, "insatisfactoria")
    sb.table("search_sessions").update({"estado": nuevo_estado}).eq("id", session_id).execute()

    # Corrección explícita de categoría: señal fuerte, alimenta el perfil de
    # procurement del usuario aunque no haya proveedor específico involucrado.
    if req.tipo == "wrong_category" and req.categoria_corregida:
        try:
            from app.services.procurement_profile import registrar_senal_uso
            registrar_senal_uso(ctx.actor_user_id, req.categoria_corregida, origen="search_history")
        except Exception as e:
            print(f"[SearchFeedback] no se pudo actualizar el perfil: {e}")

    return ins.data[0]
