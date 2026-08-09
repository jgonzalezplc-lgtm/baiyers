"""
API de plantillas de correo (Fase 4). Solo modelo/renderer/CRUD — todavía
no reemplaza ningún emisor real (eso es la Fase 6) ni tiene UI (Fase 5).
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.services.auth_context import AuthContext, get_auth_context
from app.services.mail_events import EVENTOS

router = APIRouter(prefix="/api/mail-templates", tags=["mail-templates"])


@router.get("/eventos")
async def listar_eventos():
    return [
        {
            "evento": evento, "audiencia": d.audiencia, "descripcion": d.descripcion,
            "variables_permitidas": d.variables_permitidas,
        }
        for evento, d in EVENTOS.items()
    ]


@router.get("")
async def listar_plantillas(
    workflow_id: Optional[str] = None, nodo_id: Optional[str] = None,
    ctx: AuthContext = Depends(get_auth_context),
):
    from app.services.mail_template_service import listar_plantillas as _listar
    return _listar(ctx.organization_id, workflow_id, nodo_id)


class PreviewRequest(BaseModel):
    evento: str
    subject: str
    body: str
    variables_declaradas: list[str] = []


@router.post("/preview")
async def preview_plantilla(req: PreviewRequest, ctx: AuthContext = Depends(get_auth_context)):
    from app.services.mail_template_service import preview as _preview
    try:
        return _preview(req.evento, req.subject, req.body, req.variables_declaradas)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


class GuardarPlantillaRequest(BaseModel):
    evento: str
    subject: str
    body: str
    variables_declaradas: list[str] = []
    origen: str = "user_edit"
    workflow_id: Optional[str] = None
    nodo_id: Optional[str] = None


@router.post("")
async def guardar_plantilla(req: GuardarPlantillaRequest, ctx: AuthContext = Depends(get_auth_context)):
    if not ctx.es_admin:
        raise HTTPException(status_code=403, detail="Solo un admin de la organización puede editar plantillas")
    from app.services.mail_template_service import guardar_version
    try:
        return guardar_version(
            ctx.organization_id, req.evento, req.subject, req.body, req.variables_declaradas,
            ctx.actor_user_id, origen=req.origen, workflow_id=req.workflow_id, nodo_id=req.nodo_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


class RestaurarDefaultRequest(BaseModel):
    evento: str
    workflow_id: Optional[str] = None
    nodo_id: Optional[str] = None


@router.post("/restaurar-default")
async def restaurar_default_endpoint(req: RestaurarDefaultRequest, ctx: AuthContext = Depends(get_auth_context)):
    if not ctx.es_admin:
        raise HTTPException(status_code=403, detail="Solo un admin de la organización puede restaurar plantillas")
    from app.services.mail_template_service import restaurar_default
    try:
        return restaurar_default(ctx.organization_id, req.evento, ctx.actor_user_id, workflow_id=req.workflow_id, nodo_id=req.nodo_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
