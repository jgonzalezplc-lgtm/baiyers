"""
Configuración conversacional del workflow de compras (Fase 2). Traduce una
descripción en lenguaje natural a un grafo de nodos/conexiones que el motor
de `workflow_engine.py` puede validar — nunca genera el grafo "a mano" con
el LLM: Gemini solo propone una lista simple de ETAPAS (más fácil de que
salga bien), y un compilador puro y determinístico arma el grafo real.

La conversación NO guarda nada — solo interpreta y devuelve una propuesta;
el usuario confirma y recién ahí se llama a POST /api/workflows (mismo flujo
que onboarding: investigar → revisar → confirmar).
"""
import json
import re
import unicodedata
from typing import Optional

TIPOS_ETAPA_VALIDOS = {
    "tarea_humana", "revision", "autorizacion", "homologacion",
    "emision_oc", "compra_sin_oc", "espera_documento", "accion_automatica",
}

# Distinto de TIPOS_ETAPA_VALIDOS a propósito: ese set es para el flujo de
# creación inicial (interpretar_descripcion → compilar_a_grafo), donde
# "decision" JAMÁS es una etapa que el usuario describa — el compilador la
# arma solo a partir de las reglas de autorización por monto. En cambio el
# canvas manual sí deja agregar un nodo de tipo "decisión" directamente
# (ver TIPOS en canvas/[id]/page.tsx), así que la corrección por chat
# también debe poder agregarlo — bug real: antes reusaba TIPOS_ETAPA_VALIDOS
# acá y "decisión" siempre se rechazaba en silencio.
TIPOS_NODO_AGREGABLES = TIPOS_ETAPA_VALIDOS | {"decision"}

ROLES_VALIDOS = {"cotizador", "revisor", "autorizador", "homologador", "comprador"}

EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")

PROMPT_INTERPRETAR = """Eres un analista de procesos de compras B2B. Un usuario te describe, en
lenguaje informal, cómo funciona el proceso de compras de su empresa. Tu trabajo es traducirlo
a una lista ordenada de ETAPAS — no inventes un diagrama completo, solo identifica las etapas,
quién actúa en cada una, y las reglas de autorización por monto si las menciona.

Responde SOLO JSON válido, sin markdown, con esta forma exacta:
{
  "resumen": "1-3 frases en español explicando lo que entendiste, para mostrárselo al usuario",
  "etapas": [
    {
      "nombre": "nombre corto de la etapa (ej: 'Preparar comparación')",
      "tipo": "una de: tarea_humana, revision, autorizacion, homologacion, emision_oc, compra_sin_oc, espera_documento, accion_automatica",
      "roles": ["uno o más de: cotizador, revisor, autorizador, homologador, comprador"],
      "responsables": [
        {"nombre": "solo si el usuario dio el nombre real de la persona (ej: 'María Pérez')",
         "email": "solo si el usuario escribió literalmente un email en el texto (ej: 'maria@empresa.cl')"}
      ]
    }
  ],
  "reglas_autorizacion": [
    {"hasta": 500000, "desde": null, "descripcion": "quién autoriza en este tramo, en texto"},
    {"hasta": null, "desde": 500001, "descripcion": "quién autoriza en este tramo"}
  ],
  "requiere_aclaracion": false,
  "preguntas": ["máximo 3 preguntas cortas si falta información crítica (ej: quién autoriza, hasta qué monto)"]
}

Reglas:
- Conserva únicamente etapas y actores que el usuario haya mencionado explícitamente. No completes
  un ciclo "típico" de compras por tu cuenta.
- Una respuesta breve como "yo hago todo" NO autoriza a inventar identificación, comparación,
  autorización y OC. En ese caso pregunta si realmente no interviene ninguna otra persona.
- Si el usuario no menciona tramos de monto, "reglas_autorizacion" debe ser un arreglo vacío.
- Si falta información crítica para saber quién autoriza o en qué orden, pon
  requiere_aclaracion=true y haz máximo 3 preguntas concretas — no inventes responsables.
- Toda etapa de tipo autorizacion/revision/tarea_humana/homologacion necesita al menos 1 rol.
- No repitas al usuario lo que ya te dijo; solo pregunta lo que falta.
- Sobre `responsables`: JAMÁS inventes nombres ni emails. Si el usuario dice "mi jefe" o "el
  equipo de finanzas" sin nombre concreto, deja `responsables: []` para esa etapa. Solo llena
  `nombre` si el usuario escribió un nombre real de persona; solo llena `email` si aparece
  literalmente en el texto con formato usuario@dominio. Si nombra a la misma persona en varias
  etapas (ej: "María revisa y autoriza"), repítela en cada etapa correspondiente."""


def deduplicar_responsables(etapas: list[dict]) -> list[dict]:
    """Lista plana de responsables únicos detectados en las etapas (por
    email si tienen; si no, por nombre) — para que el frontend los muestre
    en un solo panel con checkbox y no repita a la misma persona.

    Si la misma persona aparece en varias etapas (ej: "María revisa y
    autoriza"), se ACUMULAN sus roles de todas esas etapas — quedarse solo
    con los de la primera etapa donde aparece deja a la persona sin
    asignar en el resto de los roles que también le correspondían."""
    detectados: list[dict] = []
    indice_por_key: dict[str, int] = {}
    for e in etapas:
        for r in e.get("responsables") or []:
            key = r["email"] or r["nombre"].lower()
            if key in indice_por_key:
                existente = detectados[indice_por_key[key]]
                for rol in e["roles"]:
                    if rol not in existente["roles"]:
                        existente["roles"].append(rol)
                continue
            indice_por_key[key] = len(detectados)
            detectados.append({
                "nombre": r["nombre"], "email": r["email"],
                "roles": list(e["roles"]),
            })
    return detectados


def interpretar_descripcion(descripcion: str, contexto: str = "") -> dict:
    """Llama a Gemini para traducir texto libre a etapas. Nunca lanza: ante
    cualquier falla devuelve requiere_aclaracion=True pidiendo que lo intente
    de nuevo, sin inventar un workflow."""
    from app.config import settings

    vacio_seguro = {
        "resumen": "", "etapas": [], "reglas_autorizacion": [],
        "requiere_aclaracion": True,
        "preguntas": ["La interpretación tardó más de lo esperado. Tu descripción está bien; vuelve a intentarlo en unos segundos."],
    }

    texto = (descripcion or "").strip()
    if not texto:
        return vacio_seguro

    def simple(value: str) -> str:
        normalized = unicodedata.normalize("NFD", value.lower())
        return " ".join(re.sub(r"[^a-z0-9 ]", " ", "".join(c for c in normalized if unicodedata.category(c) != "Mn")).split())

    texto_simple = simple(texto)
    contexto_simple = simple(contexto)
    frases_solo = (
        "yo hago todo", "todo lo hago yo", "me encargo de todo", "lo hago todo yo", "solo yo",
        "todo pasa por mi", "todo debe pasar por mi", "yo todo", "todo yo",
    )
    declaracion_solo = len(texto_simple.split()) <= 10 and any(phrase in texto_simple for phrase in frases_solo)
    if declaracion_solo:
        return {
            "resumen": "", "etapas": [], "reglas_autorizacion": [],
            "requiere_aclaracion": True,
            "preguntas": ["¿Quieres decir que tú realizas todas las etapas, o que otras personas participan pero tú das la aprobación final?"],
        }

    contexto_solo = any(phrase in contexto_simple for phrase in frases_solo)
    confirma_todas = any(phrase in texto_simple for phrase in (
        "todas las etapas", "las hago yo", "nadie mas participa", "nadie mas interviene",
        "solo participo yo", "yo realizo todo", "yo hago el proceso completo", "de principio a fin",
    ))
    if contexto_solo and confirma_todas:
        return {
            "resumen": "Tú gestionas personalmente la compra completa y no requiere revisión ni autorización independiente.",
            "etapas": [{
                "nombre": "Gestionar compra",
                "tipo": "tarea_humana",
                "roles": ["cotizador", "revisor", "autorizador", "comprador"],
            }],
            "reglas_autorizacion": [], "requiere_aclaracion": False, "preguntas": [],
        }

    confirma_aprobacion_final = any(phrase in texto_simple for phrase in (
        "aprobacion final", "autorizacion final", "yo doy la aprobacion", "yo doy la autorizacion",
        "yo apruebo al final", "yo autorizo al final", "otros participan", "otros hacen el proceso",
    ))
    if contexto_solo and confirma_aprobacion_final:
        return {
            "resumen": "", "etapas": [], "reglas_autorizacion": [],
            "requiere_aclaracion": True,
            "preguntas": ["Entendido: tú das la aprobación final. ¿Quién prepara o compara las cotizaciones antes de enviártelas?"],
        }

    if not settings.gemini_api_key:
        return vacio_seguro

    import google.generativeai as genai
    genai.configure(api_key=settings.gemini_api_key)
    model = genai.GenerativeModel("gemini-2.5-flash")

    prompt = PROMPT_INTERPRETAR + f"\n\nDescripción del usuario:\n{texto}"
    if contexto:
        prompt += f"\n\nConversación previa (preguntas ya hechas y respuestas del usuario):\n{contexto}"

    try:
        # Los procesos con varias bifurcaciones y responsables suelen tardar
        # más de 12 s en Gemini. El frontend espera 40 s para dejar margen a
        # este timeout sin cortar una respuesta válida antes del backend.
        resp = model.generate_content(prompt, request_options={"timeout": 30})
        text = resp.text.strip()
        if "```" in text:
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        data = json.loads(text.strip())
    except Exception as e:
        print(f"[WorkflowConversational] error interpretando: {e}")
        return vacio_seguro

    etapas = [
        e for e in (data.get("etapas") or [])
        if e.get("tipo") in TIPOS_ETAPA_VALIDOS and e.get("nombre")
    ]
    for e in etapas:
        e["roles"] = [r for r in (e.get("roles") or []) if r in ROLES_VALIDOS] or ["cotizador"]
        # Validar responsables detectados: descartar los que no tienen ni
        # nombre ni email válido — Gemini a veces devuelve objetos vacíos.
        responsables_limpios = []
        for r in (e.get("responsables") or []):
            nombre = (r.get("nombre") or "").strip()
            email = (r.get("email") or "").strip().lower()
            if email and not EMAIL_RE.match(email):
                email = ""
            if not nombre and not email:
                continue
            responsables_limpios.append({"nombre": nombre, "email": email})
        e["responsables"] = responsables_limpios

    responsables_detectados = deduplicar_responsables(etapas)

    return {
        "resumen": data.get("resumen") or "",
        "etapas": etapas,
        "reglas_autorizacion": data.get("reglas_autorizacion") or [],
        "requiere_aclaracion": bool(data.get("requiere_aclaracion")) and not etapas,
        "preguntas": (data.get("preguntas") or [])[:3],
        "responsables_detectados": responsables_detectados,
    }


def _nodo_id(indice: int, sufijo: str = "") -> str:
    return f"n{indice}{sufijo}"


def compilar_a_grafo(etapas: list[dict], reglas_autorizacion: Optional[list[dict]] = None) -> tuple[list[dict], list[dict]]:
    """Compilador puro y determinístico: etapas simples (lista ordenada) →
    nodos/conexiones reales. Si hay ≥2 reglas por monto y la etapa es de tipo
    'autorizacion', se expande a un nodo de decisión por monto + un nodo de
    autorización por tramo. Los rechazos de autorización vuelven a la etapa
    anterior (devolución para corrección) — nunca a un tramo hermano.

    Diseño: se calcula primero el "nodo de entrada" de cada etapa (dónde
    apunta quien llega desde el paso anterior) ANTES de construir nada, para
    que cada conexión de avance apunte al destino real correcto — sin
    resolución diferida ni heurísticas de "el siguiente nodo creado"."""
    reglas = reglas_autorizacion or []

    if not etapas:
        return (
            [{"id": "inicio", "tipo": "inicio", "nombre": "Inicio"}, {"id": "fin", "tipo": "fin", "nombre": "Fin"}],
            [{"origen_nodo_id": "inicio", "destino_nodo_id": "fin"}],
        )

    def es_tramos(etapa: dict) -> bool:
        return etapa["tipo"] == "autorizacion" and len(reglas) > 1

    # Nodo de entrada de cada etapa (antes de construir nada).
    entrada = [_nodo_id(i, "_monto") if es_tramos(e) else _nodo_id(i) for i, e in enumerate(etapas)]
    # A dónde va el "avance" tras completar la etapa i (siguiente entrada, o fin).
    siguiente = entrada[1:] + ["fin"]
    # A dónde vuelve un rechazo en la etapa i (la entrada de la etapa anterior, o inicio).
    anterior_entrada = ["inicio"] + entrada[:-1]

    nodos: list[dict] = [{"id": "inicio", "tipo": "inicio", "nombre": "Inicio"}]
    conexiones: list[dict] = [{"origen_nodo_id": "inicio", "destino_nodo_id": entrada[0]}]

    for i, etapa in enumerate(etapas):
        destino_ok = siguiente[i]
        destino_rechazo = anterior_entrada[i]

        if not es_tramos(etapa):
            nid = entrada[i]
            nodo = {"id": nid, "tipo": etapa["tipo"], "nombre": etapa["nombre"], "roles": etapa["roles"]}
            if etapa["tipo"] == "autorizacion":
                nodo["resultados"] = ["aprobado", "rechazado"]
                conexiones.append({"origen_nodo_id": nid, "destino_nodo_id": destino_ok, "resultado": "aprobado"})
                conexiones.append({"origen_nodo_id": nid, "destino_nodo_id": destino_rechazo, "resultado": "rechazado"})
            else:
                conexiones.append({"origen_nodo_id": nid, "destino_nodo_id": destino_ok})
            nodos.append(nodo)
            continue

        # Autorización con tramos de monto.
        decision_id = entrada[i]
        tramos = [f"tramo_{j}" for j in range(len(reglas))]
        nodos.append({"id": decision_id, "tipo": "decision", "nombre": f"¿Monto? — {etapa['nombre']}", "resultados": tramos})

        for j, regla in enumerate(reglas):
            tramo_id = _nodo_id(i, f"_t{j}")
            condicion = {
                "campo": "monto_total",
                "operador": "<=" if regla.get("hasta") is not None else ">",
                "valor": regla.get("hasta") if regla.get("hasta") is not None else regla.get("desde"),
            }
            nodos.append({
                "id": tramo_id, "tipo": "autorizacion",
                "nombre": f"Autorización — {regla.get('descripcion') or f'tramo {j + 1}'}",
                "roles": etapa["roles"], "condicion_entrada": condicion,
                "resultados": ["aprobado", "rechazado"],
            })
            conexiones.append({"origen_nodo_id": decision_id, "destino_nodo_id": tramo_id, "resultado": tramos[j]})
            conexiones.append({"origen_nodo_id": tramo_id, "destino_nodo_id": destino_ok, "resultado": "aprobado"})
            conexiones.append({"origen_nodo_id": tramo_id, "destino_nodo_id": destino_rechazo, "resultado": "rechazado"})

    nodos.append({"id": "fin", "tipo": "fin", "nombre": "Fin"})
    return nodos, conexiones


# ─── Correcciones sobre un grafo ya existente (canvas) ──────────────────────
# A diferencia de interpretar_descripcion()/compilar_a_grafo(), que generan
# un grafo NUEVO desde cero, esto propone una lista chica de operaciones
# sobre un grafo que YA existe (con ediciones manuales del usuario) — el
# LLM nunca produce el grafo completo de nuevo, solo identifica qué cambiar.

OPERACIONES_VALIDAS = {
    "renombrar_nodo", "cambiar_roles", "cambiar_entrada", "cambiar_proceso",
    "cambiar_condicion_entrada", "agregar_nodo", "eliminar_nodo", "conectar", "desconectar",
    "asignar_responsable", "configurar_comunicacion",
}

PROMPT_CORRECCION = """Eres un asistente que ajusta un diagrama de proceso de compras ya
existente, a partir de una corrección en lenguaje natural del usuario. NUNCA rediseñes el
diagrama completo — identifica solo los cambios puntuales que pide el usuario, como una
lista de operaciones.

Responde SOLO JSON válido, sin markdown, con esta forma exacta:
{
  "resumen": "1-2 frases explicando qué vas a cambiar, para mostrárselo al usuario",
  "operaciones": [
    {"tipo": "renombrar_nodo", "nodo_id": "n1", "nombre": "nuevo nombre"},
    {"tipo": "cambiar_roles", "nodo_id": "n1", "roles": ["autorizador"]},
    {"tipo": "cambiar_entrada", "nodo_id": "n1", "entrada": "qué recibe esta etapa"},
    {"tipo": "cambiar_proceso", "nodo_id": "n1", "proceso": "qué debe hacer esta etapa"},
    {"tipo": "cambiar_condicion_entrada", "nodo_id": "n1", "condicion_entrada": {"campo": "monto_total", "operador": ">", "valor": 1000000}},
    {"tipo": "agregar_nodo", "nodo_id": "nuevo_homologacion", "tipo_nodo": "autorizacion", "nombre": "nombre de la etapa nueva", "roles": ["autorizador"]},
    {"tipo": "eliminar_nodo", "nodo_id": "n1"},
    {"tipo": "conectar", "origen_nodo_id": "n1", "destino_nodo_id": "n2", "resultado": "aprobado"},
    {"tipo": "desconectar", "origen_nodo_id": "n1", "destino_nodo_id": "n2", "resultado": "aprobado"},
    {"tipo": "asignar_responsable", "nodo_id": "n1", "rol_clave": "autorizador", "nombre": "Luis", "email": "luis@acme.cl"},
    {"tipo": "configurar_comunicacion", "nodo_id": "n1", "rol_clave": "cotizador", "evento_plantilla": "rfq_followup", "destinatario_tipo": "proveedor", "disparador_tipo": "al_entrar", "repetir_cada_dias": 2, "max_intentos": 3, "evento_termino": "rfq_completa", "alcance_termino": "proveedor", "politica_agotamiento": "descartar_entidad"}
  ],
  "requiere_aclaracion": false,
  "preguntas": ["máximo 3 preguntas cortas si la corrección es ambigua"]
}

Reglas:
- "nodo_id" en cualquier operación que NO sea "agregar_nodo" debe ser uno de los ids que
  aparecen en el grafo actual que te paso abajo — JAMÁS inventes un id que no exista ahí.
- "agregar_nodo" SÍ debe traer su propio "nodo_id" nuevo — invéntale un id corto y único
  (ej: "nuevo_homologacion") que no exista ya en el grafo. Si necesitas conectar esa etapa
  nueva (con "conectar"/"desconectar" u otra operación), usa ESE MISMO id como si ya
  existiera — y pon la operación "agregar_nodo" ANTES que las que la usan, en ese orden
  dentro de la lista "operaciones".
- "roles" solo puede tener valores de: cotizador, revisor, autorizador, homologador, comprador.
- "tipo_nodo" (para agregar_nodo) solo puede ser uno de: tarea_humana, revision,
  autorizacion, decision, homologacion, emision_oc, compra_sin_oc, espera_documento,
  accion_automatica. Usa "decision" para un punto donde el flujo se ramifica según una
  condición del proceso (ej: "¿el proveedor es nuevo?", "¿el monto supera X?") — igual que
  "autorizacion", un nodo "decision" SIEMPRE se ramifica con resultados "aprobado"/
  "rechazado" (nunca inventes otras etiquetas como "si"/"no" — el motor real solo entiende
  esas dos), aunque el significado de cada rama lo decidas vos según la pregunta (ej:
  "aprobado" = "sí es nuevo", "rechazado" = "no es nuevo" — el resumen que le muestras al
  usuario debe aclarar qué significa cada rama en este caso concreto).
- "resultado" en conectar/desconectar solo hace falta si el nodo ORIGEN (origen_nodo_id) es
  el que tiene esa rama entre sus propios resultados (ej: un nodo de autorización o decisión
  con "aprobado"/"rechazado") — si no, omite el campo. IMPORTANTE: el nodo de origen es
  siempre el que DECIDE, nunca el que recibe la decisión. Ej: si "Autorizar compra" puede
  rechazar y volver a "Preparar cotización", la conexión es origen_nodo_id="Autorizar
  compra", destino_nodo_id="Preparar cotización", resultado="rechazado" — NUNCA al revés.
- "asignar_responsable" asigna una PERSONA real (nombre + email opcional) a un rol que YA
  existe en alguna etapa del grafo actual — "rol_clave" debe ser uno de los roles que
  aparecen en el campo "roles" de algún nodo (mira el grafo actual para saber cuáles hay:
  cotizador, revisor, autorizador, homologador o comprador). Si el usuario usa un nombre coloquial para
  el rol ("el jefe", "el homologador", "quien homologa"), mapéalo al "rol_clave" real que
  tiene esa etapa en el grafo — nunca inventes una clave nueva. Si no puedes determinar con
  seguridad a qué rol_clave se refiere, pon requiere_aclaracion=true y pregunta cuál es.
  Esta operación asigna a la persona de inmediato (no espera a "Guardar").
- "configurar_comunicacion" asocia un correo a una tarjeta YA existente. Usa exclusivamente
  un evento real del catálogo: approval_requested, approval_reminder, approval_approved,
  approval_rejected, approval_returned, approval_escalated, workflow_assignment_invitation,
  rfq_requested, rfq_followup, rfq_missing_information, rfq_received_thanks,
  supplier_awarded, supplier_not_awarded, purchase_order_sent,
  purchase_order_ack_reminder o dispatch_status_request. Para audiencia interna el
  destinatario_tipo debe ser responsable_rol, solicitante, autorizador o equipo; para externa,
  proveedor o contacto_proveedor. Si hay repetición, siempre incluye repetir_cada_dias >= 1,
  max_intentos >= 1, evento_termino y politica_agotamiento (pausar, escalar,
  descartar_entidad o avanzar_timeout). Esta operación se guarda de inmediato.
- Si el usuario pide activar el ciclo u otra acción que no sea ni el grafo ni asignar una
  persona, no generes una operación para eso — es una acción separada del canvas.
- Si la corrección es ambigua o falta información para aplicarla con seguridad, pon
  requiere_aclaracion=true y pregunta — no adivines."""


def _operacion_valida(op: dict, ids_nodos: set[str], nodos_por_id: dict | None = None) -> bool:
    from app.services.workflow_engine import CAMPOS_CONDICION_VALIDOS, OPERADORES_VALIDOS

    tipo = op.get("tipo")
    if tipo not in OPERACIONES_VALIDAS:
        return False
    if tipo == "renombrar_nodo":
        return op.get("nodo_id") in ids_nodos and bool(op.get("nombre"))
    if tipo == "cambiar_roles":
        roles = op.get("roles")
        return op.get("nodo_id") in ids_nodos and isinstance(roles, list) and bool(roles) and all(r in ROLES_VALIDOS for r in roles)
    if tipo in ("cambiar_entrada", "cambiar_proceso"):
        campo = "entrada" if tipo == "cambiar_entrada" else "proceso"
        return op.get("nodo_id") in ids_nodos and isinstance(op.get(campo), str)
    if tipo == "cambiar_condicion_entrada":
        cond = op.get("condicion_entrada") or {}
        return (
            op.get("nodo_id") in ids_nodos
            and cond.get("campo") in CAMPOS_CONDICION_VALIDOS
            and cond.get("operador") in OPERADORES_VALIDOS
            and cond.get("valor") is not None
        )
    if tipo == "agregar_nodo":
        roles = op.get("roles") or []
        return (
            op.get("tipo_nodo") in TIPOS_NODO_AGREGABLES
            and bool(op.get("nombre"))
            and all(r in ROLES_VALIDOS for r in roles)
        )
    if tipo == "eliminar_nodo":
        return op.get("nodo_id") in ids_nodos
    if tipo in ("conectar", "desconectar"):
        origen_id = op.get("origen_nodo_id")
        destino_id = op.get("destino_nodo_id")
        if origen_id not in ids_nodos or destino_id not in ids_nodos:
            return False
        resultado = op.get("resultado")
        # Un "aprobado"/"rechazado" solo tiene sentido si el nodo de ORIGEN
        # es el que decide (tiene esa rama en sus propios resultados) — así
        # se evita el caso real donde el modelo conectó "rechazado" en la
        # dirección equivocada (entrando a la autorización en vez de
        # saliendo de ella).
        if resultado and nodos_por_id is not None:
            origen_nodo = nodos_por_id.get(origen_id) or {}
            if resultado not in (origen_nodo.get("resultados") or []):
                return False
        return True
    if tipo == "asignar_responsable":
        nombre = op.get("nombre")
        email = op.get("email")
        rol_clave = op.get("rol_clave")
        if not isinstance(nombre, str) or not nombre.strip():
            return False
        if rol_clave not in ROLES_VALIDOS:
            return False
        if email is not None and (not isinstance(email, str) or "@" not in email):
            return False
        # El rol debe pertenecer de verdad a alguna etapa del grafo (incluye
        # nodos agregados en esta misma corrección) — si no, la persona
        # quedaría asignada a un rol que ninguna tarjeta usa.
        if nodos_por_id is not None:
            if not any(rol_clave in (n.get("roles") or []) for n in nodos_por_id.values()):
                return False
        return True
    if tipo == "configurar_comunicacion":
        from app.services.mail_events import EVENTOS
        from app.services.workflow_automation import POLITICAS_AGOTAMIENTO
        nodo_id = op.get("nodo_id")
        evento = op.get("evento_plantilla")
        destinatario = op.get("destinatario_tipo")
        if nodo_id not in ids_nodos or evento not in EVENTOS:
            return False
        audiencia = EVENTOS[evento].audiencia
        internos = {"responsable_rol", "solicitante", "autorizador", "equipo"}
        externos = {"proveedor", "contacto_proveedor"}
        if destinatario not in (internos if audiencia == "internal" else externos):
            return False
        intervalo = op.get("repetir_cada_dias")
        if intervalo is not None:
            if not isinstance(intervalo, int) or intervalo < 1:
                return False
            if not isinstance(op.get("max_intentos"), int) or op["max_intentos"] < 1:
                return False
            if not op.get("evento_termino") or op.get("politica_agotamiento") not in POLITICAS_AGOTAMIENTO:
                return False
        return True
    return False


def interpretar_correccion(descripcion: str, grafo_actual: dict, contexto: str = "") -> dict:
    """Traduce una corrección en lenguaje natural a operaciones sobre un
    grafo YA EXISTENTE. Nunca lanza: ante cualquier falla devuelve
    requiere_aclaracion=True sin operaciones, nunca inventa un cambio."""
    from app.config import settings

    def vacio_seguro(mensaje: str) -> dict:
        return {
            "resumen": "", "operaciones": [],
            "requiere_aclaracion": True,
            "preguntas": [mensaje],
        }

    MENSAJE_GENERICO = "Tuve un problema interpretando eso. Intenta de nuevo en unos segundos."

    texto = (descripcion or "").strip()
    if not texto:
        return vacio_seguro(MENSAJE_GENERICO)
    if not settings.gemini_api_key:
        return vacio_seguro(MENSAJE_GENERICO)

    ids_nodos = {n.get("id") for n in (grafo_actual.get("nodos") or []) if n.get("id")}

    import google.generativeai as genai
    genai.configure(api_key=settings.gemini_api_key)
    model = genai.GenerativeModel("gemini-2.5-flash")

    prompt = (
        PROMPT_CORRECCION
        + f"\n\nGrafo actual:\n{json.dumps(grafo_actual, ensure_ascii=False)}"
        + f"\n\nCorrección del usuario:\n{texto}"
    )
    if contexto:
        prompt += f"\n\nConversación previa:\n{contexto}"

    try:
        resp = model.generate_content(prompt, request_options={"timeout": 35})
        text = resp.text.strip()
        if "```" in text:
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        data = json.loads(text.strip())
    except Exception as e:
        detalle = f"{type(e).__name__}: {e}"
        print(f"[WorkflowConversational] error interpretando corrección: {detalle}")
        detalle_lower = detalle.lower()
        if "quota" in detalle_lower or "429" in detalle_lower or "resourceexhausted" in detalle_lower:
            mensaje = "Se agotó la cuota gratuita de Gemini por ahora — intenta de nuevo en un rato."
        elif "timeout" in detalle_lower or "deadline" in detalle_lower:
            mensaje = "La interpretación tardó más de lo esperado. Intenta de nuevo en unos segundos."
        else:
            mensaje = MENSAJE_GENERICO
        return vacio_seguro(mensaje)

    # Filtrado secuencial: un nodo que se agrega en esta misma corrección debe
    # quedar disponible para las operaciones que le siguen (conectarlo, etc.),
    # así que el set de ids conocidos crece a medida que se procesa la lista
    # — nunca se valida contra un snapshot fijo del grafo original. También
    # se mantiene un mapa id -> nodo para poder chequear que un resultado
    # ("aprobado"/"rechazado") en una conexión pertenezca de verdad al nodo
    # de origen, incluyendo nodos agregados en esta misma respuesta.
    ids_conocidos = set(ids_nodos)
    nodos_por_id = {n.get("id"): n for n in (grafo_actual.get("nodos") or []) if n.get("id")}
    operaciones: list[dict] = []
    contador_nuevo = 0
    for op in (data.get("operaciones") or []):
        if not isinstance(op, dict):
            continue
        if op.get("tipo") == "agregar_nodo":
            nodo_id = op.get("nodo_id")
            if not isinstance(nodo_id, str) or not nodo_id or nodo_id in ids_conocidos:
                while True:
                    contador_nuevo += 1
                    candidato = f"nuevo_{contador_nuevo}"
                    if candidato not in ids_conocidos:
                        nodo_id = candidato
                        break
            op = {**op, "nodo_id": nodo_id}
            if not _operacion_valida(op, ids_conocidos, nodos_por_id):
                continue
            operaciones.append(op)
            ids_conocidos.add(nodo_id)
            tipo_nodo = op.get("tipo_nodo")
            resultados_nuevo = ["aprobado", "rechazado"] if tipo_nodo in ("decision", "autorizacion") else []
            nodos_por_id[nodo_id] = {"id": nodo_id, "tipo": tipo_nodo, "resultados": resultados_nuevo, "roles": op.get("roles") or []}
            continue
        if _operacion_valida(op, ids_conocidos, nodos_por_id):
            operaciones.append(op)

    # Si el modelo propuso operaciones pero TODAS se descartaron por validar
    # mal (rol inexistente, resultado en la dirección equivocada, etc.), no
    # hay que devolver el "resumen" original como si el cambio se hubiera
    # aplicado — eso le mostraba al usuario un mensaje de éxito aunque el
    # grafo no cambió nada. Se trata igual que requiere_aclaracion, con un
    # mensaje honesto en vez del resumen que prometía algo que no pasó.
    propuso_algo = bool(data.get("operaciones"))
    todo_descartado = propuso_algo and not operaciones
    if todo_descartado:
        return {
            "resumen": "",
            "operaciones": [],
            "requiere_aclaracion": True,
            "preguntas": ["No pude aplicar ese cambio con seguridad — algún dato no coincidía con el grafo actual (un rol que no existe en ninguna etapa, una conexión con el resultado en la dirección equivocada, etc.). ¿Puedes darme más detalle o intentarlo de nuevo con otras palabras?"],
        }

    return {
        "resumen": data.get("resumen") or "",
        "operaciones": operaciones,
        "requiere_aclaracion": bool(data.get("requiere_aclaracion")) and not operaciones,
        "preguntas": (data.get("preguntas") or [])[:3],
    }
