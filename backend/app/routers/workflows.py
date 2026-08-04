"""API del Workflow Builder de compras/autorizaciones — Fase 1 (fundación).

Solo lectura/guardado de borradores y validación de grafo. No dispara
correos ni reemplaza el flujo productivo de `aprobaciones.py`/`listas.py`.
"""
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/workflows", tags=["workflows"])


class RolIn(BaseModel):
    clave: str
    nombre: str
    descripcion: Optional[str] = None


class CrearWorkflowRequest(BaseModel):
    user_id: str
    nombre: str
    nodos: list[dict] = Field(default_factory=list)
    conexiones: list[dict] = Field(default_factory=list)
    origen: str = "visual"
    roles: Optional[list[RolIn]] = None


class InterpretarRequest(BaseModel):
    descripcion: str
    contexto: Optional[str] = None


@router.post("/interpretar")
async def interpretar_workflow(req: InterpretarRequest):
    """Solo interpreta y propone — no guarda nada. El frontend confirma con
    el usuario y recién ahí llama a POST /api/workflows con el resultado."""
    import asyncio
    from app.services.workflow_conversational import compilar_a_grafo, interpretar_descripcion

    # El SDK de Gemini es síncrono; se ejecuta fuera del event loop para no
    # congelar el resto de Baiyer mientras responde el modelo.
    propuesta = await asyncio.to_thread(interpretar_descripcion, req.descripcion, req.contexto or "")
    if propuesta["requiere_aclaracion"]:
        return {**propuesta, "nodos": [], "conexiones": []}

    nodos, conexiones = compilar_a_grafo(propuesta["etapas"], propuesta["reglas_autorizacion"])
    return {**propuesta, "nodos": nodos, "conexiones": conexiones}


@router.post("")
async def crear_workflow(req: CrearWorkflowRequest):
    from app.services.workflow_service import crear_borrador
    if req.origen not in ("conversacional", "visual", "mixto"):
        raise HTTPException(status_code=400, detail="origen inválido")
    roles = [r.model_dump() for r in req.roles] if req.roles else None
    return crear_borrador(req.user_id, req.nombre, req.nodos, req.conexiones, req.origen, roles)


@router.get("")
async def listar_workflows(user_id: str):
    from app.services.workflow_service import listar_workflows
    return listar_workflows(user_id)


@router.get("/autorizadores-sugeridos")
async def autorizadores_sugeridos(user_id: str, monto_total: float = 0):
    """Fase 4: a quién le llegaría la solicitud de autorización de una lista
    con este monto, según el ciclo activo del usuario — sin crear nada.
    Devuelve null si no hay ciclo activo o nadie asignado (el frontend cae
    al campo de email manual)."""
    from app.services.workflow_execution import previsualizar_autorizadores
    return previsualizar_autorizadores(user_id, monto_total)


@router.get("/{workflow_id}")
async def obtener_workflow(workflow_id: str, user_id: str):
    from app.services.workflow_service import obtener_workflow
    workflow = obtener_workflow(user_id, workflow_id)
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow no encontrado")
    return workflow


class ActualizarWorkflowRequest(BaseModel):
    user_id: str
    nodos: list[dict]
    conexiones: list[dict]
    nombre: Optional[str] = None


@router.put("/{workflow_id}")
async def actualizar_workflow(workflow_id: str, req: ActualizarWorkflowRequest):
    from app.services.workflow_service import actualizar_borrador
    try:
        return actualizar_borrador(req.user_id, workflow_id, req.nodos, req.conexiones, req.nombre)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{workflow_id}/validar")
async def validar_workflow(workflow_id: str, user_id: str):
    from app.services.workflow_service import validar_workflow
    try:
        errores = validar_workflow(user_id, workflow_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"valido": not errores, "errores": errores}


class ActivarWorkflowRequest(BaseModel):
    user_id: str


@router.post("/{workflow_id}/activar")
async def activar_workflow(workflow_id: str, req: ActivarWorkflowRequest):
    from app.services.workflow_service import activar_workflow
    try:
        return activar_workflow(req.user_id, workflow_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ─── Responsables ───────────────────────────────────────────────────────────

class CrearResponsableRequest(BaseModel):
    user_id: str
    nombre: str
    cargo: Optional[str] = None
    email: Optional[str] = None
    telefono: Optional[str] = None
    suplente_id: Optional[str] = None


@router.post("/responsables")
async def crear_responsable(req: CrearResponsableRequest):
    from app.services.workflow_service import crear_responsable
    if not req.nombre.strip():
        raise HTTPException(status_code=400, detail="El nombre es requerido")
    return crear_responsable(req.user_id, req.nombre.strip(), req.cargo, req.email, req.telefono, req.suplente_id)


@router.get("/responsables/listar")
async def listar_responsables(user_id: str, incluir_inactivos: bool = False):
    from app.services.workflow_service import listar_responsables
    return listar_responsables(user_id, incluir_inactivos)


class EditarResponsableRequest(BaseModel):
    user_id: str
    nombre: Optional[str] = None
    cargo: Optional[str] = None
    email: Optional[str] = None
    telefono: Optional[str] = None
    suplente_id: Optional[str] = None
    activo: Optional[bool] = None


@router.patch("/responsables/{responsable_id}")
async def editar_responsable(responsable_id: str, req: EditarResponsableRequest):
    from app.services.workflow_service import actualizar_responsable
    try:
        return actualizar_responsable(req.user_id, responsable_id, req.model_dump(exclude={"user_id"}))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


class AsignarRolRequest(BaseModel):
    user_id: str
    workflow_id: str
    rol_clave: str
    orden_autorizacion: Optional[int] = None


@router.post("/responsables/{responsable_id}/roles")
async def asignar_rol(responsable_id: str, req: AsignarRolRequest):
    from app.services.workflow_service import asignar_rol
    try:
        return asignar_rol(req.user_id, responsable_id, req.workflow_id, req.rol_clave, req.orden_autorizacion)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/responsables/{responsable_id}/roles/{workflow_id}/{rol_clave}")
async def quitar_rol(responsable_id: str, workflow_id: str, rol_clave: str, user_id: str):
    from app.services.workflow_service import quitar_rol
    try:
        quitar_rol(user_id, responsable_id, workflow_id, rol_clave)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"success": True}
