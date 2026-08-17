"""
Renderer y persistencia de plantillas de correo (Fase 4).

Reemplazo de placeholders `{{variable}}` por regex con allowlist por
evento — deliberadamente NO se usa Jinja2: el spec original pide evitar
"Jinja sin sandbox", y para asunto/cuerpo de correo no hace falta lógica
condicional ni loops, así que un reemplazo simple y auditable es más
seguro que traer un motor de templates completo.

Precedencia de resolución: nodo+workflow → workflow → organización →
default de sistema (vive en `mail_events.EVENTOS`, no en la DB — así una
organización sin overrides sigue recibiendo el correo de siempre).

El link de autorización (u otro link sensible) SIEMPRE llega como una
variable más en `render()` — este módulo nunca genera ni guarda links, eso
sigue siendo responsabilidad de quien arma el envío (ej. `aprobaciones.py`).
"""
import re
from typing import Optional
from uuid import uuid4

from app.services.mail_events import EVENTOS

PLACEHOLDER_RE = re.compile(r"\{\{\s*(\w+)\s*\}\}")


def _sb():
    from app.services.supabase import get_supabase
    return get_supabase()


def _maybe_single(query) -> Optional[dict]:
    """`.maybe_single().execute()` puede devolver `None` en vez de un objeto
    con `.data = None` cuando no hay filas (bug real de postgrest-py 2.x
    encontrado en producción) — todo acceso pasa por acá para no repetir el
    chequeo defensivo en cada función."""
    try:
        resp = query.maybe_single().execute()
    except Exception:
        return None
    return (resp.data if resp else None) or None


def extraer_placeholders(texto: str) -> set[str]:
    return set(PLACEHOLDER_RE.findall(texto or ""))


def validar_variables(evento: str, variables_declaradas: list[str]) -> None:
    if evento not in EVENTOS:
        raise ValueError(f"Evento desconocido: {evento}")
    permitidas = set(EVENTOS[evento].variables_permitidas)
    invalidas = set(variables_declaradas) - permitidas
    if invalidas:
        raise ValueError(f"Variables no permitidas para '{evento}': {', '.join(sorted(invalidas))}")


def _validar_placeholders_declarados(subject: str, body: str, variables_declaradas: list[str]) -> None:
    usados = extraer_placeholders(subject) | extraer_placeholders(body)
    sin_declarar = usados - set(variables_declaradas)
    if sin_declarar:
        raise ValueError(f"La plantilla usa variables no declaradas: {', '.join(sorted(sin_declarar))}")


def _reemplazar(texto: str, variables: dict) -> str:
    def sub(m: re.Match) -> str:
        clave = m.group(1)
        if clave not in variables:
            raise ValueError(f"Falta la variable requerida para renderizar: {clave}")
        return str(variables[clave])
    return PLACEHOLDER_RE.sub(sub, texto or "")


def resolver_definicion(
    organizacion_id: Optional[str], evento: str, workflow_id: Optional[str] = None,
    nodo_id: Optional[str] = None, canal: str = "email", locale: str = "es-CL",
) -> Optional[dict]:
    """Busca el override más específico aplicable, o None si debe usarse el
    default de sistema. Nunca lanza — un problema de lectura degrada al
    default en vez de romper el envío."""
    if not organizacion_id or evento not in EVENTOS:
        return None
    sb = _sb()

    candidatos = []
    if workflow_id and nodo_id:
        candidatos.append((workflow_id, nodo_id, "nodo"))
    if workflow_id:
        candidatos.append((workflow_id, None, "workflow"))
    candidatos.append((None, None, "organizacion"))

    for wf_id, nid, origen in candidatos:
        q = sb.table("mail_template_definitions").select("*").eq(
            "organizacion_id", organizacion_id
        ).eq("evento", evento).eq("estado", "activa").eq("canal", canal).eq("locale", locale)
        q = q.eq("workflow_id", wf_id) if wf_id else q.is_("workflow_id", "null")
        q = q.eq("nodo_id", nid) if nid else q.is_("nodo_id", "null")
        definicion = _maybe_single(q)
        if not definicion or not definicion.get("version_activa_id"):
            continue
        version = _maybe_single(
            sb.table("mail_template_versions").select("*").eq("id", definicion["version_activa_id"])
        )
        if version:
            return {"definicion": definicion, "version": version, "origen": origen}
    return None


def render(
    evento: str, variables: dict, organizacion_id: Optional[str] = None,
    workflow_id: Optional[str] = None, nodo_id: Optional[str] = None,
) -> dict:
    """Renderiza el asunto/cuerpo final. Lanza ValueError si falta alguna
    variable que la plantilla necesita — nunca se envía un correo a medio
    llenar."""
    if evento not in EVENTOS:
        raise ValueError(f"Evento desconocido: {evento}")
    resuelto = resolver_definicion(organizacion_id, evento, workflow_id, nodo_id)
    if resuelto:
        subject_tpl = resuelto["version"]["subject"]
        body_tpl = resuelto["version"]["body_text"]
        origen = resuelto["origen"]
    else:
        catalogo = EVENTOS[evento]
        subject_tpl, body_tpl, origen = catalogo.asunto_default, catalogo.cuerpo_default, "default"
    return {
        "subject": _reemplazar(subject_tpl, variables),
        "body": _reemplazar(body_tpl, variables),
        "origen": origen,
    }


def preview(evento: str, subject: str, body: str, variables_declaradas: list[str]) -> dict:
    """Renderiza con datos ficticios para mostrar en el editor. NUNCA
    escribe en la base de datos."""
    validar_variables(evento, variables_declaradas)
    _validar_placeholders_declarados(subject, body, variables_declaradas)
    fake = {v: f"[{v}]" for v in variables_declaradas}
    return {
        "subject": _reemplazar(subject, fake),
        "body": _reemplazar(body, fake),
        "es_preview": True,
    }


def guardar_version(
    organizacion_id: str, evento: str, subject: str, body: str, variables_declaradas: list[str],
    autor_user_id: Optional[str], origen: str = "user_edit",
    workflow_id: Optional[str] = None, nodo_id: Optional[str] = None,
    canal: str = "email", locale: str = "es-CL",
) -> dict:
    """Crea la definición si no existe y agrega una versión nueva — nunca
    sobreescribe ni borra una versión anterior."""
    if evento not in EVENTOS:
        raise ValueError(f"Evento desconocido: {evento}")
    if origen not in ("default", "ai_draft", "user_edit"):
        raise ValueError("origen inválido")
    validar_variables(evento, variables_declaradas)
    _validar_placeholders_declarados(subject, body, variables_declaradas)

    sb = _sb()
    q = sb.table("mail_template_definitions").select("*").eq(
        "organizacion_id", organizacion_id
    ).eq("evento", evento).eq("canal", canal).eq("locale", locale)
    q = q.eq("workflow_id", workflow_id) if workflow_id else q.is_("workflow_id", "null")
    q = q.eq("nodo_id", nodo_id) if nodo_id else q.is_("nodo_id", "null")
    definicion = _maybe_single(q)

    if not definicion:
        ins = sb.table("mail_template_definitions").insert({
            "organizacion_id": organizacion_id, "evento": evento,
            "audiencia": EVENTOS[evento].audiencia, "canal": canal, "locale": locale,
            "workflow_id": workflow_id, "nodo_id": nodo_id,
        }).execute()
        definicion = ins.data[0]

    ultima = sb.table("mail_template_versions").select("version").eq(
        "definition_id", definicion["id"]
    ).order("version", desc=True).limit(1).execute()
    siguiente_version = (ultima.data[0]["version"] + 1) if ultima.data else 1

    version_ins = sb.table("mail_template_versions").insert({
        "definition_id": definicion["id"], "version": siguiente_version,
        "subject": subject, "body_text": body, "variables_declaradas": variables_declaradas,
        "origen": origen, "autor_user_id": autor_user_id,
    }).execute()
    version = version_ins.data[0]

    sb.table("mail_template_definitions").update(
        {"version_activa_id": version["id"], "estado": "activa"}
    ).eq("id", definicion["id"]).execute()

    return {**definicion, "version_activa_id": version["id"], "version": version}


def restaurar_default(
    organizacion_id: str, evento: str, autor_user_id: Optional[str],
    workflow_id: Optional[str] = None, nodo_id: Optional[str] = None,
    canal: str = "email", locale: str = "es-CL",
) -> dict:
    """Restaurar el default es una versión NUEVA con origen='default', nunca
    un borrado del historial de versiones anteriores."""
    if evento not in EVENTOS:
        raise ValueError(f"Evento desconocido: {evento}")
    catalogo = EVENTOS[evento]
    variables = sorted(extraer_placeholders(catalogo.asunto_default) | extraer_placeholders(catalogo.cuerpo_default))
    return guardar_version(
        organizacion_id, evento, catalogo.asunto_default, catalogo.cuerpo_default, variables,
        autor_user_id, origen="default", workflow_id=workflow_id, nodo_id=nodo_id,
        canal=canal, locale=locale,
    )


def listar_plantillas(organizacion_id: str, workflow_id: Optional[str] = None, nodo_id: Optional[str] = None) -> list[dict]:
    """Catálogo completo fusionado con los overrides de la organización —
    para la futura UI de Fase 5 y para inspección/soporte."""
    resultado = []
    usos: dict[str, int] = {}
    try:
        sb = _sb()
        miembros = sb.table("membresias_organizacion").select("user_id").eq(
            "organizacion_id", organizacion_id
        ).execute().data or []
        user_ids = [m["user_id"] for m in miembros]
        workflows = sb.table("workflow_definitions").select("id").in_("user_id", user_ids).execute().data or [] if user_ids else []
        workflow_ids = [w["id"] for w in workflows]
        reglas = sb.table("workflow_node_communication_rules").select("evento_plantilla").in_(
            "workflow_id", workflow_ids
        ).eq("activa", True).execute().data or [] if workflow_ids else []
        for regla in reglas:
            evento_usado = regla.get("evento_plantilla")
            if evento_usado:
                usos[evento_usado] = usos.get(evento_usado, 0) + 1
    except Exception:
        # La biblioteca sigue operativa aun si el contador no está disponible.
        usos = {}
    for evento, catalogo in EVENTOS.items():
        resuelto = resolver_definicion(organizacion_id, evento, workflow_id, nodo_id)
        if resuelto:
            resultado.append({
                "evento": evento, "audiencia": catalogo.audiencia, "descripcion": catalogo.descripcion,
                "variables_permitidas": catalogo.variables_permitidas,
                "subject": resuelto["version"]["subject"], "body": resuelto["version"]["body_text"],
                "origen": resuelto["origen"], "version": resuelto["version"]["version"],
                "definition_id": resuelto["definicion"]["id"],
                "usos_en_nodos": usos.get(evento, 0),
            })
        else:
            resultado.append({
                "evento": evento, "audiencia": catalogo.audiencia, "descripcion": catalogo.descripcion,
                "variables_permitidas": catalogo.variables_permitidas,
                "subject": catalogo.asunto_default, "body": catalogo.cuerpo_default,
                "origen": "default", "version": 0, "definition_id": None,
                "usos_en_nodos": usos.get(evento, 0),
            })
    return resultado


def restaurar_herencia(
    organizacion_id: str, evento: str, workflow_id: str, nodo_id: Optional[str] = None,
    canal: str = "email", locale: str = "es-CL",
) -> dict:
    """Archiva el override de nodo/workflow sin borrar sus versiones.

    A diferencia de `restaurar_default`, esto vuelve a resolver por el nivel
    superior y por tanto hereda cambios futuros de organización/default.
    """
    sb = _sb()
    q = sb.table("mail_template_definitions").select("*").eq(
        "organizacion_id", organizacion_id
    ).eq("evento", evento).eq("workflow_id", workflow_id).eq("canal", canal).eq("locale", locale)
    q = q.eq("nodo_id", nodo_id) if nodo_id else q.is_("nodo_id", "null")
    definicion = _maybe_single(q)
    if not definicion:
        return {"heredando": True, "definition_id": None}
    sb.table("mail_template_definitions").update({"estado": "archivada"}).eq(
        "id", definicion["id"]
    ).execute()
    return {"heredando": True, "definition_id": definicion["id"]}


def registrar_envio(
    organizacion_id: str, evento: str, destinatario_email: str, idempotency_key: str,
    estado: str = "pendiente", definition_id: Optional[str] = None, version_id: Optional[str] = None,
    workflow_id: Optional[str] = None, workflow_nodo_id: Optional[str] = None,
    proveedor_id: Optional[str] = None, responsable_id: Optional[str] = None,
    gmail_message_id: Optional[str] = None, gmail_thread_id: Optional[str] = None,
    error: Optional[str] = None,
) -> dict:
    """Registra el intento de envío de forma idempotente: un reintento con
    la misma `idempotency_key` devuelve la fila existente, nunca duplica."""
    sb = _sb()
    existente = _maybe_single(sb.table("mail_delivery_events").select("*").eq("idempotency_key", idempotency_key))
    if existente:
        return existente
    try:
        ins = sb.table("mail_delivery_events").insert({
            "organizacion_id": organizacion_id, "evento": evento, "definition_id": definition_id,
            "version_id": version_id, "destinatario_email": destinatario_email,
            "workflow_id": workflow_id, "workflow_nodo_id": workflow_nodo_id,
            "proveedor_id": proveedor_id, "responsable_id": responsable_id,
            "gmail_message_id": gmail_message_id, "gmail_thread_id": gmail_thread_id,
            "estado": estado, "error": error, "idempotency_key": idempotency_key,
        }).execute()
        return ins.data[0]
    except Exception as e:
        # Condición de carrera: otro proceso ganó la misma clave — se
        # recupera esa fila en vez de lanzar.
        if "23505" in str(e) or "duplicate key" in str(e).lower():
            return _maybe_single(sb.table("mail_delivery_events").select("*").eq("idempotency_key", idempotency_key)) or {}
        raise


def reservar_envio(
    organizacion_id: str, evento: str, destinatario_email: str, idempotency_key: str,
    definition_id: Optional[str] = None, version_id: Optional[str] = None,
    workflow_id: Optional[str] = None, workflow_nodo_id: Optional[str] = None,
    proveedor_id: Optional[str] = None, responsable_id: Optional[str] = None,
    scheduled_action_id: Optional[str] = None,
) -> dict:
    """Reserva atómicamente el derecho a enviar ANTES de llamar a Gmail.

    Devuelve `{adquirida: True, entrega: ...}` sólo al proceso que insertó la
    clave. Un segundo proceso recibe la entrega existente con `adquirida`
    falsa y no debe enviar. Requiere la RPC de la migración 041; los emisores
    productivos actuales seguirán usando `registrar_envio` hasta su migración
    explícita en fases posteriores.
    """
    if evento not in EVENTOS:
        raise ValueError(f"Evento desconocido: {evento}")
    email = (destinatario_email or "").strip().lower()
    if not email or "@" not in email:
        raise ValueError("destinatario_email inválido")
    if not idempotency_key or not idempotency_key.strip():
        raise ValueError("idempotency_key es requerida")

    sb = _sb()
    token = str(uuid4())
    resp = sb.rpc("reserve_mail_delivery_event", {
        "p_organizacion_id": organizacion_id,
        "p_evento": evento,
        "p_destinatario_email": email,
        "p_idempotency_key": idempotency_key.strip(),
        "p_reservation_token": token,
        "p_definition_id": definition_id,
        "p_version_id": version_id,
        "p_workflow_id": workflow_id,
        "p_workflow_nodo_id": workflow_nodo_id,
        "p_proveedor_id": proveedor_id,
        "p_responsable_id": responsable_id,
    }).execute()
    filas = resp.data or []
    if filas:
        entrega = filas[0]
        if scheduled_action_id:
            actualizada = sb.table("mail_delivery_events").update({
                "scheduled_action_id": scheduled_action_id,
            }).eq("id", entrega["id"]).eq("reservation_token", token).execute()
            entrega = (actualizada.data or [entrega])[0]
        return {"adquirida": True, "entrega": entrega, "reservation_token": token}

    existente = _maybe_single(
        sb.table("mail_delivery_events").select("*").eq("idempotency_key", idempotency_key.strip())
    )
    return {"adquirida": False, "entrega": existente, "reservation_token": None}


def actualizar_entrega_reservada(
    entrega_id: str, reservation_token: str, estado: str, *,
    gmail_message_id: Optional[str] = None, gmail_thread_id: Optional[str] = None,
    error: Optional[str] = None,
) -> Optional[dict]:
    """Cierra una entrega sólo si el worker conserva su token de reserva."""
    if estado not in {"enviado", "fallido", "delivery_uncertain"}:
        raise ValueError("estado final de entrega inválido")
    from datetime import datetime, timezone
    payload = {
        "estado": estado, "gmail_message_id": gmail_message_id,
        "gmail_thread_id": gmail_thread_id, "error": (error or "")[:1000] or None,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    resp = _sb().table("mail_delivery_events").update(payload).eq("id", entrega_id).eq(
        "reservation_token", reservation_token
    ).execute()
    filas = resp.data or []
    return filas[0] if filas else None
