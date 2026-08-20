"""API del Workflow Builder de compras/autorizaciones — Fase 1 (fundación).

Solo lectura/guardado de borradores y validación de grafo. No dispara
correos ni reemplaza el flujo productivo de `aprobaciones.py`/`listas.py`.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.services.auth_context import AuthContext, get_auth_context
from app.services.llm_rate_limit import limitar_por_ip

router = APIRouter(prefix="/api/workflows", tags=["workflows"])

# Estos dos endpoints llaman a Gemini SIN autenticación, así que el único
# freno contra un loop desde afuera es la IP de origen. Los límites son
# holgados para un onboarding real (que gasta ~6-12 llamadas en total) y
# apretados frente a un script.
_limite_interpretar = limitar_por_ip("workflows_interpretar", por_minuto=10, por_hora=60)
_limite_turno = limitar_por_ip("workflows_proceso_turno", por_minuto=20, por_hora=120)


class RolIn(BaseModel):
    clave: str
    nombre: str
    descripcion: Optional[str] = None


class ResponsableSemilla(BaseModel):
    """Responsable pre-detectado desde el chat conversacional. El frontend
    lo manda con roles + email para que el backend cree el responsable,
    lo asigne a los roles indicados y (si tiene email + no es miembro
    todavía) dispare la invitación real."""
    nombre: str
    email: Optional[str] = None
    roles: list[str] = Field(default_factory=list)
    invitar: bool = True


class CrearWorkflowRequest(BaseModel):
    nombre: str
    nodos: list[dict] = Field(default_factory=list)
    conexiones: list[dict] = Field(default_factory=list)
    origen: str = "visual"
    roles: Optional[list[RolIn]] = None
    responsables: list[ResponsableSemilla] = Field(default_factory=list)


# Topes de tamaño para todo lo que termina viajando a Gemini. Con cuenta
# pagada, cada token de entrada se factura: sin tope, un solo request con
# cientos de KB de texto cuesta lo que miles de usos legítimos. Los valores
# son holgados para un uso real (una descripción de proceso de compras no
# pasa de unos pocos miles de caracteres) y el exceso devuelve 422.
MAX_DESCRIPCION = 8_000
MAX_CONTEXTO = 20_000
MAX_RESPUESTA = 4_000
MAX_SLOTS = 50


class InterpretarRequest(BaseModel):
    descripcion: str = Field(max_length=MAX_DESCRIPCION)
    contexto: Optional[str] = Field(default=None, max_length=MAX_CONTEXTO)


class RolloutRequest(BaseModel):
    execution_mode: str
    reason: str = ""


class UsuarioActual(BaseModel):
    nombre: str = Field(default="", max_length=200)
    email: str = Field(default="", max_length=320)


class ProcesoTurnoRequest(BaseModel):
    """Un turno de la entrevista por slots. La ficha (`slots`) viaja en cada
    request: el backend no persiste la entrevista, igual que /interpretar."""
    respuesta: str = Field(default="", max_length=MAX_RESPUESTA)
    slots: Optional[list[dict]] = Field(default=None, max_length=MAX_SLOTS)
    contexto: Optional[str] = Field(default=None, max_length=MAX_CONTEXTO)
    # Identidad de quien conversa, para resolver "yo me encargo" a una persona
    # concreta. Es dato del propio usuario y el endpoint no lee nada de la DB
    # con esto: sólo se inyecta al prompt.
    usuario_actual: Optional[UsuarioActual] = None


@router.get("/rollout/estado")
async def estado_rollout(ctx: AuthContext = Depends(get_auth_context)):
    from app.services.workflow_rollout import obtener_metricas_rollout
    return obtener_metricas_rollout(ctx.user_ids_organizacion, ctx.organization_id)


@router.put("/rollout/estado")
async def cambiar_estado_rollout(req: RolloutRequest, ctx: AuthContext = Depends(get_auth_context)):
    if not ctx.es_admin:
        raise HTTPException(status_code=403, detail="Solo un admin puede cambiar el modo de ejecución")
    from app.services.workflow_rollout import cambiar_rollout
    try:
        return cambiar_rollout(ctx.actor_user_id, ctx.organization_id, req.execution_mode, req.reason)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/interpretar", dependencies=[Depends(_limite_interpretar)])
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


@router.post("/proceso/turno", dependencies=[Depends(_limite_turno)])
async def turno_proceso(req: ProcesoTurnoRequest):
    """Entrevista guiada del proceso de compras: el avance lo decide el
    backend de forma determinística (primer slot pendiente, con tope de
    intentos) y el LLM sólo interpreta la respuesta. Al completarse devuelve
    el mismo contrato que /interpretar (nodos + conexiones + responsables)."""
    import asyncio
    from app.services.workflow_proceso_slots import procesar_turno

    return await asyncio.to_thread(
        procesar_turno,
        req.respuesta,
        req.slots,
        req.contexto or "",
        req.usuario_actual.model_dump() if req.usuario_actual else None,
    )


@router.post("")
async def crear_workflow(req: CrearWorkflowRequest, ctx: AuthContext = Depends(get_auth_context)):
    from app.services.workflow_service import (
        crear_borrador, crear_responsable, asignar_rol,
    )
    if req.origen not in ("conversacional", "visual", "mixto"):
        raise HTTPException(status_code=400, detail="origen inválido")
    roles = [r.model_dump() for r in req.roles] if req.roles else None
    workflow = crear_borrador(ctx.actor_user_id, req.nombre, req.nodos, req.conexiones, req.origen, roles)

    # Responsables semilla del chat conversacional: crear, asignar a roles y
    # (si corresponde) disparar la invitación. Cada resultado se reporta al
    # frontend en 'invitaciones' — no falla el POST si una invitación
    # individual falla, para no perder el workflow ya creado.
    invitaciones = []
    if req.responsables:
        from app.services.organizacion import invitar_a_organizacion
        # Un correo representa una persona. Si el chat la detectó en varias
        # etapas, acumulamos roles y enviamos una sola invitación.
        consolidados: dict[str, ResponsableSemilla] = {}
        sin_email: list[ResponsableSemilla] = []
        for r in req.responsables:
            email_key = (r.email or "").strip().lower()
            if not email_key:
                sin_email.append(r)
                continue
            if email_key not in consolidados:
                consolidados[email_key] = r.model_copy(update={"email": email_key, "roles": list(dict.fromkeys(r.roles))})
            else:
                anterior = consolidados[email_key]
                consolidados[email_key] = anterior.model_copy(update={
                    "nombre": anterior.nombre or r.nombre,
                    "roles": list(dict.fromkeys([*anterior.roles, *r.roles])),
                    "invitar": anterior.invitar or r.invitar,
                })
        for r in [*consolidados.values(), *sin_email]:
            nombre = (r.nombre or "").strip()
            email = (r.email or "").strip().lower() or None
            if not nombre and not email:
                continue
            try:
                nuevo = crear_responsable(ctx.actor_user_id, nombre or email or "Sin nombre", email=email)
            except Exception as e:
                invitaciones.append({"nombre": nombre, "email": email, "estado": "error", "detalle": f"crear responsable: {e}"})
                continue
            for rol_clave in (r.roles or []):
                try:
                    asignar_rol(ctx.actor_user_id, nuevo["id"], workflow["id"], rol_clave)
                except Exception as e:
                    print(f"[workflows] asignar_rol falló {rol_clave}: {e}")
            if not email or not r.invitar:
                invitaciones.append({"nombre": nombre, "email": email, "estado": "responsable_creado_sin_invitar"})
                continue
            try:
                res = invitar_a_organizacion(ctx.actor_user_id, email, "miembro", nuevo["id"])
                invitaciones.append({"nombre": nombre, "email": email, "estado": res.get("estado", "invitado")})
            except ValueError as e:
                invitaciones.append({"nombre": nombre, "email": email, "estado": "error", "detalle": str(e)})

    return {**workflow, "invitaciones": invitaciones}


@router.get("")
async def listar_workflows(user_id: str):
    from app.services.workflow_service import listar_workflows
    return listar_workflows(user_id)


@router.get("/estado/resumen")
async def estado_workflow(user_id: str):
    """Estado operativo del ciclo nuevo (o legado) para superficies como el
    dashboard. Distingue borrador validado de ausencia de configuración."""
    from app.services.workflow_service import obtener_estado_workflow
    return obtener_estado_workflow(user_id)


@router.get("/autorizadores-sugeridos")
async def autorizadores_sugeridos(monto_total: float = 0, ctx: AuthContext = Depends(get_auth_context)):
    """Fase 4: a quién le llegaría la solicitud de autorización de una lista
    con este monto, según el ciclo activo del usuario — sin crear nada.
    Devuelve null si no hay ciclo activo o nadie asignado (el frontend cae
    al campo de email manual)."""
    from app.services.workflow_execution import previsualizar_autorizadores
    return previsualizar_autorizadores(ctx.actor_user_id, monto_total)


# ─── Operación de instancias unificadas (PRD Fase C) ──────────────────────

@router.get("/instancias/{instance_id}/automatizacion")
async def automatizacion_instancia(instance_id: str, ctx: AuthContext = Depends(get_auth_context)):
    from app.services.workflow_scheduler import obtener_automatizacion_instancia
    try:
        return obtener_automatizacion_instancia(ctx.actor_user_id, instance_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/instancias/{instance_id}/pausar")
async def pausar_instancia(instance_id: str, ctx: AuthContext = Depends(get_auth_context)):
    if not ctx.es_admin:
        raise HTTPException(status_code=403, detail="Solo un admin puede pausar una instancia")
    from app.services.workflow_scheduler import cambiar_pausa_instancia
    try:
        return cambiar_pausa_instancia(ctx.actor_user_id, instance_id, True)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/instancias/{instance_id}/reanudar")
async def reanudar_instancia(instance_id: str, ctx: AuthContext = Depends(get_auth_context)):
    if not ctx.es_admin:
        raise HTTPException(status_code=403, detail="Solo un admin puede reanudar una instancia")
    from app.services.workflow_scheduler import cambiar_pausa_instancia
    try:
        return cambiar_pausa_instancia(ctx.actor_user_id, instance_id, False)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/instancias/{instance_id}/rfq/cerrar")
async def cerrar_rfq_instancia(instance_id: str, ctx: AuthContext = Depends(get_auth_context)):
    if not ctx.es_admin:
        raise HTTPException(status_code=403, detail="Solo un admin puede cerrar manualmente una RFQ")
    from app.services.workflow_rfq import cerrar_rfq_manualmente
    try:
        return cerrar_rfq_manualmente(ctx.actor_user_id, instance_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/instancias/{instance_id}/homologacion")
async def casos_homologacion(instance_id: str, ctx: AuthContext = Depends(get_auth_context)):
    from app.services.workflow_homologation import listar_casos
    return {"casos": listar_casos(ctx.actor_user_id, instance_id)}


@router.get("/homologacion/casos")
async def casos_homologacion_lista(lista_id: str, ctx: AuthContext = Depends(get_auth_context)):
    from app.services.workflow_homologation import listar_casos
    return {"casos": listar_casos(ctx.actor_user_id, lista_id=lista_id)}


@router.get("/homologacion/estado-items")
async def estado_homologacion_por_item(lista_id: str, ctx: AuthContext = Depends(get_auth_context)):
    from app.services.workflow_homologation import mapa_resultado_a_caso
    return {"items": mapa_resultado_a_caso(ctx.actor_user_id, lista_id)}


class DecisionHomologacionRequest(BaseModel):
    decision: str
    comentario: str = ""
    requisitos_pendientes: list[str] = Field(default_factory=list)


@router.post("/homologacion/{caso_id}/decidir")
async def decidir_homologacion(caso_id: str, req: DecisionHomologacionRequest,
                               ctx: AuthContext = Depends(get_auth_context)):
    from app.services.workflow_homologation import decidir_caso
    try:
        return decidir_caso(
            ctx.actor_user_id, ctx.es_admin, caso_id, req.decision,
            req.comentario, req.requisitos_pendientes,
        )
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{workflow_id}")
async def obtener_workflow(workflow_id: str, user_id: str):
    from app.services.workflow_service import obtener_workflow
    workflow = obtener_workflow(user_id, workflow_id)
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow no encontrado")
    return workflow


@router.delete("/{workflow_id}")
async def eliminar_workflow_endpoint(workflow_id: str, ctx: AuthContext = Depends(get_auth_context)):
    from app.services.workflow_service import eliminar_workflow
    try:
        eliminar_workflow(ctx.actor_user_id, workflow_id)
    except ValueError as e:
        codigo = 404 if "no encontrado" in str(e) else 400
        raise HTTPException(status_code=codigo, detail=str(e))
    return {"success": True}


class ActualizarWorkflowRequest(BaseModel):
    user_id: str
    nodos: list[dict]
    conexiones: list[dict]
    nombre: Optional[str] = None


class CrearVersionRequest(BaseModel):
    nodos: list[dict]
    conexiones: list[dict]


@router.post("/{workflow_id}/crear-version")
async def crear_version_workflow(workflow_id: str, req: CrearVersionRequest,
                                 ctx: AuthContext = Depends(get_auth_context)):
    if not ctx.es_admin:
        raise HTTPException(status_code=403, detail="Solo un admin puede crear versiones del ciclo")
    from app.services.workflow_service import crear_version_borrador
    try:
        return crear_version_borrador(
            ctx.actor_user_id, workflow_id, req.nodos, req.conexiones,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/{workflow_id}")
async def actualizar_workflow(workflow_id: str, req: ActualizarWorkflowRequest):
    from app.services.workflow_service import actualizar_borrador
    try:
        return actualizar_borrador(req.user_id, workflow_id, req.nodos, req.conexiones, req.nombre)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


class InterpretarCorreccionRequest(BaseModel):
    descripcion: str
    grafo_actual: dict
    contexto: Optional[str] = None


@router.post("/{workflow_id}/interpretar-correccion")
async def interpretar_correccion_endpoint(workflow_id: str, req: InterpretarCorreccionRequest, ctx: AuthContext = Depends(get_auth_context)):
    """Solo interpreta y propone operaciones sobre el grafo que manda el
    frontend — no toca la base de datos ni el workflow persistido. El
    canvas aplica las operaciones localmente y sigue necesitando
    'Guardar' explícito para persistir, igual que una edición manual."""
    import asyncio
    from app.services.workflow_conversational import interpretar_correccion

    return await asyncio.to_thread(interpretar_correccion, req.descripcion, req.grafo_actual, req.contexto or "")


@router.get("/{workflow_id}/validar")
async def validar_workflow(workflow_id: str, ctx: AuthContext = Depends(get_auth_context)):
    from app.services.workflow_service import validar_workflow
    try:
        errores = validar_workflow(ctx.actor_user_id, workflow_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"valido": not errores, "errores": errores}


@router.post("/{workflow_id}/activar")
async def activar_workflow(workflow_id: str, ctx: AuthContext = Depends(get_auth_context)):
    from app.services.workflow_service import activar_workflow
    try:
        return activar_workflow(ctx.actor_user_id, workflow_id)
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


# ─── Configuración unificada por tarjeta (PRD Fase B) ──────────────────────

@router.get("/{workflow_id}/configuracion")
async def obtener_configuracion_tarjetas(workflow_id: str, ctx: AuthContext = Depends(get_auth_context)):
    from app.services.workflow_automation_service import listar_configuracion_workflow
    try:
        return listar_configuracion_workflow(ctx.actor_user_id, workflow_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


class AsignacionNodoRequest(BaseModel):
    nodo_id: str
    rol_clave: str
    responsable_id: str
    modo: str = "individual"
    orden: Optional[int] = None
    es_propietario_excepcion: bool = False


@router.post("/{workflow_id}/asignaciones-nodo")
async def crear_asignacion_nodo(workflow_id: str, req: AsignacionNodoRequest,
                                ctx: AuthContext = Depends(get_auth_context)):
    if not ctx.es_admin:
        raise HTTPException(status_code=403, detail="Solo un admin puede configurar responsables")
    from app.services.workflow_automation_service import asignar_responsable_nodo
    try:
        return asignar_responsable_nodo(
            ctx.actor_user_id, workflow_id, req.nodo_id, req.rol_clave,
            req.responsable_id, req.modo, req.orden, req.es_propietario_excepcion,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{workflow_id}/asignaciones-nodo/{assignment_id}")
async def eliminar_asignacion_nodo(workflow_id: str, assignment_id: str,
                                   ctx: AuthContext = Depends(get_auth_context)):
    if not ctx.es_admin:
        raise HTTPException(status_code=403, detail="Solo un admin puede configurar responsables")
    from app.services.workflow_automation_service import quitar_responsable_nodo
    try:
        quitar_responsable_nodo(ctx.actor_user_id, workflow_id, assignment_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"success": True}


class ReglaComunicacionRequest(BaseModel):
    nodo_id: str
    rol_clave: Optional[str] = None
    evento_plantilla: str
    destinatario_tipo: str
    canal: str = "email"
    disparador_tipo: str = "al_entrar"
    disparador_evento: Optional[str] = None
    demora_inicial_dias: int = 0
    repetir_cada_dias: Optional[int] = None
    max_intentos: Optional[int] = None
    evento_termino: Optional[str] = None
    alcance_termino: str = "tarjeta"
    resultado_al_terminar: Optional[str] = None
    politica_agotamiento: Optional[str] = None
    resultado_agotamiento: Optional[str] = None
    activa: bool = True


@router.post("/{workflow_id}/reglas-comunicacion")
async def crear_regla_comunicacion(workflow_id: str, req: ReglaComunicacionRequest,
                                   ctx: AuthContext = Depends(get_auth_context)):
    if not ctx.es_admin:
        raise HTTPException(status_code=403, detail="Solo un admin puede configurar comunicaciones")
    from app.services.workflow_automation_service import guardar_regla_comunicacion
    try:
        return guardar_regla_comunicacion(ctx.actor_user_id, workflow_id, req.nodo_id, req.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/{workflow_id}/reglas-comunicacion/{rule_id}")
async def editar_regla_comunicacion(workflow_id: str, rule_id: str, req: ReglaComunicacionRequest,
                                    ctx: AuthContext = Depends(get_auth_context)):
    if not ctx.es_admin:
        raise HTTPException(status_code=403, detail="Solo un admin puede configurar comunicaciones")
    from app.services.workflow_automation_service import guardar_regla_comunicacion
    try:
        return guardar_regla_comunicacion(
            ctx.actor_user_id, workflow_id, req.nodo_id, req.model_dump(), rule_id=rule_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{workflow_id}/reglas-comunicacion/{rule_id}")
async def borrar_regla_comunicacion(workflow_id: str, rule_id: str,
                                    ctx: AuthContext = Depends(get_auth_context)):
    if not ctx.es_admin:
        raise HTTPException(status_code=403, detail="Solo un admin puede configurar comunicaciones")
    from app.services.workflow_automation_service import eliminar_regla_comunicacion
    try:
        eliminar_regla_comunicacion(ctx.actor_user_id, workflow_id, rule_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"success": True}
