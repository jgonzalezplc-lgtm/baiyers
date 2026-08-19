"""Entrevista por slots del proceso de compras (fase "proceso" del onboarding).

Divide responsabilidades a propósito, porque mezclarlas fue la causa raíz del
loop infinito que tenía el chat:

- **El avance es determinístico** (`siguiente_slot`): la próxima pregunta es
  siempre el primer slot pendiente, y cada slot tiene un tope de intentos. No
  existe forma de repetir una pregunta para siempre, aunque el LLM falle.
- **La comprensión es del LLM** (`extraer_de_respuesta`): una respuesta como
  "Coti Zamorano autoriza, cotiz@abc.cl" se interpreta por significado, nunca
  por coincidencia de substrings — que el correo contenga "cotiz" no la
  convierte en cotizadora.
- **La compilación es determinística** (`compilar_slots_a_etapas` +
  `compilar_a_grafo`): el grafo real nunca lo arma el modelo.

Una sola respuesta puede llenar varios slots: si el usuario contesta la
primera pregunta con todo el proceso, se saltan las preguntas ya cubiertas y
sólo se pregunta lo que falta.

Igual que `workflow_conversational`, acá NO se guarda nada: el estado de la
entrevista viaja en cada request y recién al confirmar se llama a
POST /api/workflows.
"""
import json
from typing import Optional

from app.services.workflow_conversational import (
    EMAIL_RE,
    compilar_a_grafo,
    deduplicar_responsables,
)

# Tope de veces que se insiste con el MISMO slot antes de darlo por saltado.
# Es la garantía dura contra loops: con 6 slots, la entrevista termina como
# máximo en 12 turnos pase lo que pase con el modelo.
MAX_INTENTOS_POR_SLOT = 2

# Orden real del proceso de compra. `rol` None = el slot no genera etapa
# propia (las reglas de monto alimentan al compilador de autorización).
SLOTS_PROCESO: list[dict] = [
    {
        "clave": "cotizador",
        "rol": "cotizador",
        "tipo_etapa": "tarea_humana",
        "nombre_etapa": "Cotizar",
        "pregunta": "¿Quién o quiénes se encargan de cotizar? Indica sus nombres y correos.",
    },
    {
        "clave": "revisor",
        "rol": "revisor",
        "tipo_etapa": "revision",
        "nombre_etapa": "Revisar cotizaciones",
        "pregunta": "¿Alguien revisa o compara las cotizaciones antes de autorizar? Indica nombre y correo, o responde que no aplica.",
    },
    {
        "clave": "autorizador",
        "rol": "autorizador",
        "tipo_etapa": "autorizacion",
        "nombre_etapa": "Autorizar compra",
        "pregunta": "¿Quién o quiénes autorizan las compras? Indica nombres y correos.",
    },
    {
        "clave": "reglas_monto",
        "rol": None,
        "tipo_etapa": None,
        "nombre_etapa": None,
        "pregunta": "¿La autorización depende del monto? Indica los tramos (ej: \"hasta 500 mil autoriza Ana, sobre eso el gerente\"), o responde que no.",
    },
    {
        "clave": "homologador",
        "rol": "homologador",
        "tipo_etapa": "homologacion",
        "nombre_etapa": "Homologar proveedor nuevo",
        "pregunta": "¿Quién revisa y aprueba a los proveedores nuevos? Indica nombre y correo, o responde que no aplica.",
    },
    {
        "clave": "comprador",
        "rol": "comprador",
        "tipo_etapa": "emision_oc",
        "nombre_etapa": "Emitir orden de compra",
        "pregunta": "¿Quién emite y envía la orden de compra al proveedor? Indica nombre y correo.",
    },
]

CLAVES_VALIDAS = {s["clave"] for s in SLOTS_PROCESO}
_DEF_POR_CLAVE = {s["clave"]: s for s in SLOTS_PROCESO}

# Esquema de salida tipada. Deliberadamente plano y sin `null`: Gemini
# responde peor con uniones/nullables, así que se usan centinelas ("" y 0) y
# se validan en Python. Sin `enum` en el schema a propósito — se valida acá
# para no depender del soporte de `format: enum` del SDK.
ESQUEMA_EXTRACCION = {
    "type": "object",
    "properties": {
        "slots": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "clave": {"type": "string"},
                    "estado": {"type": "string"},
                    "personas": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "nombre": {"type": "string"},
                                "email": {"type": "string"},
                            },
                            "required": ["nombre", "email"],
                        },
                    },
                },
                "required": ["clave", "estado", "personas"],
            },
        },
        "reglas_autorizacion": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "desde": {"type": "integer"},
                    "hasta": {"type": "integer"},
                    "descripcion": {"type": "string"},
                },
                "required": ["desde", "hasta", "descripcion"],
            },
        },
        "entendido": {"type": "boolean"},
        "aclaracion": {"type": "string"},
    },
    "required": ["slots", "reglas_autorizacion", "entendido", "aclaracion"],
}

PROMPT_EXTRACCION = """Eres un analista de procesos de compras B2B. Estás llenando una ficha del
proceso de compras de una empresa a partir de lo que responde el usuario en un chat.

La ficha tiene estos campos ("slots"):
- cotizador: quién pide/arma las cotizaciones.
- revisor: quién revisa o compara las cotizaciones antes de autorizar.
- autorizador: quién aprueba la compra.
- reglas_monto: si la autorización depende de tramos de monto.
- homologador: quién revisa y aprueba a proveedores nuevos.
- comprador: quién emite y envía la orden de compra.

Se le acaba de hacer UNA pregunta al usuario, pero su respuesta puede contener información de
VARIOS campos a la vez. Extrae todo lo que puedas de todos los campos que la respuesta cubra, no
sólo del campo preguntado.

Reglas estrictas:
- JAMÁS inventes nombres ni correos. Sólo llena "nombre" si el usuario escribió un nombre real de
  persona, y "email" sólo si aparece literalmente con formato usuario@dominio. Si no hay, usa "".
- Interpreta por SIGNIFICADO, no por parecido de palabras. Si el usuario dice "Coti Zamorano
  autoriza, su correo es cotiz@abc.cl", ella es autorizador aunque su nombre y correo se parezcan
  a la palabra "cotizar".
- Usa estado="resuelto" cuando el usuario entregó información útil para ese campo.
- Usa estado="no_aplica" cuando el usuario dice explícitamente que ese paso no existe, que no lo
  hace nadie, o que no aplica en su empresa.
- NO incluyas en "slots" los campos sobre los que el usuario no dijo nada. Es correcto devolver
  una lista con un solo campo, o incluso vacía.
- Si la persona es la misma para varios campos (ej: "yo hago todo"), repítela en cada campo que
  corresponda.
- "reglas_autorizacion" sólo si el usuario menciona montos. Usa 0 en "desde" o "hasta" cuando el
  tramo no tiene ese límite (ej: "sobre 500000" => desde=500001, hasta=0). Interpreta montos
  coloquiales chilenos ("500 lucas" = 500000, "2 palos" = 2000000).
- "entendido"=false SÓLO si la respuesta no aporta nada interpretable para ningún campo (ej: el
  usuario preguntó otra cosa, o escribió algo sin relación). En ese caso escribe en "aclaracion"
  una repregunta corta y amable sobre el campo que se estaba preguntando.
- Si "entendido" es true, "aclaracion" debe ser "".
"""


def estado_inicial() -> list[dict]:
    """Ficha vacía. El frontend la recibe en el primer turno y la devuelve
    en cada request siguiente — el backend no persiste la entrevista."""
    return [
        {"clave": s["clave"], "estado": "pendiente", "personas": [], "reglas": [], "intentos": 0}
        for s in SLOTS_PROCESO
    ]


def _sanear_slots(slots: Optional[list[dict]]) -> list[dict]:
    """Normaliza lo que llega del cliente contra la definición real: ignora
    claves desconocidas y repone slots faltantes. Nunca confía en la forma
    del payload."""
    por_clave = {}
    for s in slots or []:
        clave = s.get("clave")
        if clave not in CLAVES_VALIDAS or clave in por_clave:
            continue
        estado = s.get("estado")
        por_clave[clave] = {
            "clave": clave,
            "estado": estado if estado in ("pendiente", "resuelto", "no_aplica") else "pendiente",
            "personas": _sanear_personas(s.get("personas")),
            "reglas": _sanear_reglas(s.get("reglas")),
            "intentos": max(0, int(s.get("intentos") or 0)),
        }
    base = estado_inicial()
    return [por_clave.get(s["clave"], s) for s in base]


def _sanear_personas(personas) -> list[dict]:
    limpias: list[dict] = []
    vistos: set[str] = set()
    for p in personas or []:
        if not isinstance(p, dict):
            continue
        nombre = str(p.get("nombre") or "").strip()
        email = str(p.get("email") or "").strip().lower()
        if email and not EMAIL_RE.match(email):
            email = ""
        if not nombre and not email:
            continue
        key = email or nombre.lower()
        if key in vistos:
            continue
        vistos.add(key)
        limpias.append({"nombre": nombre, "email": email})
    return limpias


def _sanear_reglas(reglas) -> list[dict]:
    limpias: list[dict] = []
    for r in reglas or []:
        if not isinstance(r, dict):
            continue
        descripcion = str(r.get("descripcion") or "").strip()
        try:
            desde = int(r.get("desde") or 0)
            hasta = int(r.get("hasta") or 0)
        except (TypeError, ValueError):
            continue
        if desde <= 0 and hasta <= 0 and not descripcion:
            continue
        limpias.append({
            # 0 en el schema significa "sin límite"; hacia afuera se expresa
            # como None, que es lo que espera `compilar_a_grafo`.
            "desde": desde if desde > 0 else None,
            "hasta": hasta if hasta > 0 else None,
            "descripcion": descripcion,
        })
    return limpias


def siguiente_slot(slots: list[dict]) -> Optional[dict]:
    """Primer slot pendiente en el orden del proceso. Determinístico: es la
    única fuente de "cuál es la próxima pregunta"."""
    for s in slots:
        if s["estado"] == "pendiente":
            return s
    return None


def aplicar_extraccion(slots: list[dict], extraccion: dict) -> list[dict]:
    """Mezcla lo extraído sobre la ficha. Aditivo a propósito: si el usuario
    agrega otra persona a un rol ya resuelto, se suma en vez de reemplazar."""
    por_clave = {s["clave"]: s for s in slots}

    for item in extraccion.get("slots") or []:
        if not isinstance(item, dict):
            continue
        slot = por_clave.get(item.get("clave"))
        if slot is None:
            continue
        estado = item.get("estado")
        if estado not in ("resuelto", "no_aplica"):
            continue
        personas = _sanear_personas(item.get("personas"))
        if personas:
            existentes = {p["email"] or p["nombre"].lower() for p in slot["personas"]}
            slot["personas"].extend(
                p for p in personas if (p["email"] or p["nombre"].lower()) not in existentes
            )
        # "no_aplica" no puede pisar un slot que ya tiene gente asignada: si
        # el usuario nombró a alguien antes, esa información manda.
        if estado == "no_aplica" and not slot["personas"]:
            slot["estado"] = "no_aplica"
        else:
            slot["estado"] = "resuelto"

    reglas = _sanear_reglas(extraccion.get("reglas_autorizacion"))
    if reglas:
        slot_monto = por_clave["reglas_monto"]
        slot_monto["reglas"] = reglas
        slot_monto["estado"] = "resuelto"

    return slots


def compilar_slots_a_etapas(slots: list[dict]) -> tuple[list[dict], list[dict]]:
    """Ficha → (etapas, reglas_autorizacion) para `compilar_a_grafo`. Puro."""
    etapas: list[dict] = []
    reglas: list[dict] = []
    for slot in slots:
        definicion = _DEF_POR_CLAVE[slot["clave"]]
        if slot["clave"] == "reglas_monto":
            if slot["estado"] == "resuelto":
                reglas = slot["reglas"]
            continue
        if slot["estado"] != "resuelto":
            continue
        etapas.append({
            "nombre": definicion["nombre_etapa"],
            "tipo": definicion["tipo_etapa"],
            "roles": [definicion["rol"]],
            "responsables": list(slot["personas"]),
        })
    return etapas, reglas


def _resumen(etapas: list[dict], reglas: list[dict]) -> str:
    if not etapas:
        return "No alcancé a identificar etapas del proceso."
    partes = []
    for e in etapas:
        quienes = ", ".join(p["nombre"] or p["email"] for p in e["responsables"])
        partes.append(f"{e['nombre']}" + (f" ({quienes})" if quienes else ""))
    texto = "Entendí este proceso: " + " → ".join(partes) + "."
    if reglas:
        texto += f" Con {len(reglas)} tramo(s) de autorización por monto."
    return texto


def extraer_de_respuesta(respuesta: str, pregunta: str, contexto: str = "") -> dict:
    """Única parte con LLM. Ante cualquier falla devuelve una extracción
    vacía con entendido=True, para que el avance determinístico siga su
    curso en vez de trabar la entrevista."""
    from app.config import settings

    vacio = {"slots": [], "reglas_autorizacion": [], "entendido": True, "aclaracion": ""}
    if not (respuesta or "").strip() or not settings.gemini_api_key:
        return vacio

    import google.generativeai as genai

    genai.configure(api_key=settings.gemini_api_key)
    model = genai.GenerativeModel(
        "gemini-2.5-flash",
        generation_config={
            "response_mime_type": "application/json",
            "response_schema": ESQUEMA_EXTRACCION,
            "temperature": 0,
        },
    )

    prompt = PROMPT_EXTRACCION
    if contexto:
        prompt += f"\n\nConversación previa:\n{contexto}"
    prompt += f"\n\nPregunta que se le hizo al usuario:\n{pregunta}"
    prompt += f"\n\nRespuesta del usuario:\n{respuesta.strip()}"

    try:
        resp = model.generate_content(prompt, request_options={"timeout": 30})
        data = json.loads(resp.text)
    except Exception as e:  # noqa: BLE001 — nunca romper la entrevista por el modelo
        print(f"[WorkflowProcesoSlots] error extrayendo: {e}")
        return vacio

    if not isinstance(data, dict):
        return vacio
    return {
        "slots": data.get("slots") or [],
        "reglas_autorizacion": data.get("reglas_autorizacion") or [],
        "entendido": bool(data.get("entendido", True)),
        "aclaracion": str(data.get("aclaracion") or "").strip(),
    }


def procesar_turno(respuesta: str, slots: Optional[list[dict]], contexto: str = "") -> dict:
    """Un turno de la entrevista. Sin `respuesta` y sin ficha previa devuelve
    la primera pregunta sin llamar al modelo."""
    ficha = _sanear_slots(slots)
    primer_turno = not slots

    if primer_turno and not (respuesta or "").strip():
        actual = siguiente_slot(ficha)
        return {
            "slots": ficha,
            "pregunta": _DEF_POR_CLAVE[actual["clave"]]["pregunta"],
            "clave_pregunta": actual["clave"],
            "completo": False,
            "aclaracion": "",
            "etapas": [], "reglas_autorizacion": [], "responsables_detectados": [],
            "resumen": "", "nodos": [], "conexiones": [],
        }

    actual = siguiente_slot(ficha)
    pregunta_actual = _DEF_POR_CLAVE[actual["clave"]]["pregunta"] if actual else ""

    extraccion = extraer_de_respuesta(respuesta, pregunta_actual, contexto)
    aplicar_extraccion(ficha, extraccion)

    aclaracion = ""
    if actual and actual["estado"] == "pendiente":
        # El turno no resolvió el slot que se estaba preguntando. Se insiste
        # una vez; al agotar los intentos se salta, garantizando avance.
        actual["intentos"] += 1
        if actual["intentos"] >= MAX_INTENTOS_POR_SLOT:
            actual["estado"] = "no_aplica"
        elif not extraccion["entendido"]:
            aclaracion = extraccion["aclaracion"]

    siguiente = siguiente_slot(ficha)
    if siguiente:
        return {
            "slots": ficha,
            "pregunta": _DEF_POR_CLAVE[siguiente["clave"]]["pregunta"],
            "clave_pregunta": siguiente["clave"],
            "completo": False,
            "aclaracion": aclaracion,
            "etapas": [], "reglas_autorizacion": [], "responsables_detectados": [],
            "resumen": "", "nodos": [], "conexiones": [],
        }

    etapas, reglas = compilar_slots_a_etapas(ficha)
    nodos, conexiones = compilar_a_grafo(etapas, reglas) if etapas else ([], [])
    return {
        "slots": ficha,
        "pregunta": "",
        "clave_pregunta": "",
        "completo": bool(etapas),
        "aclaracion": "" if etapas else "No logré identificar ninguna etapa del proceso. ¿Quieres describirlo con tus palabras?",
        "etapas": etapas,
        "reglas_autorizacion": reglas,
        "responsables_detectados": deduplicar_responsables(etapas),
        "resumen": _resumen(etapas, reglas),
        "nodos": nodos,
        "conexiones": conexiones,
    }
