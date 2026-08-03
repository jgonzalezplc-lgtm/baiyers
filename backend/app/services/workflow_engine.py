"""
Motor de workflows de compras (Fase 1 — fundación).

Puro y determinístico: valida grafos, calcula el siguiente nodo y evalúa
condiciones estructuradas (sin `eval`, sin aritmética arbitraria). No toca la
base de datos — lo que hace falta para poder probarlo sin ejecutar compras
reales, tal como pide el criterio de aceptación.

No reemplaza `approval_requests`/`aprobaciones.py`: este motor decide CUÁNDO y
A QUIÉN corresponde autorizar; el envío del magic link y su idempotencia
siguen siendo los de siempre.
"""
from dataclasses import dataclass, field
from typing import Optional

TIPOS_NODO = {
    "inicio", "tarea_humana", "revision", "autorizacion", "decision",
    "accion_automatica", "homologacion", "emision_oc", "compra_sin_oc",
    "espera_documento", "fin",
}

# Tipos de nodo que representan trabajo de una persona — deben tener al
# menos un rol o responsable asignado, si no el grafo no es ejecutable.
TIPOS_REQUIEREN_RESPONSABLE = {"tarea_humana", "revision", "autorizacion", "homologacion"}

ROLES_BASE = {"cotizador", "revisor", "autorizador", "comprador"}

OPERADORES_VALIDOS = {">", ">=", "<", "<=", "==", "!=", "in", "not in"}
CAMPOS_CONDICION_VALIDOS = {
    "monto_total", "moneda", "categoria", "centro_costo", "proyecto",
    "proveedor_nuevo", "proveedor_homologado", "requiere_oc",
}


@dataclass
class ErrorValidacion:
    codigo: str
    mensaje: str
    nodo_id: Optional[str] = None

    def to_dict(self) -> dict:
        d = {"codigo": self.codigo, "mensaje": self.mensaje}
        if self.nodo_id:
            d["nodo_id"] = self.nodo_id
        return d


def _index_nodos(nodos: list[dict]) -> dict[str, dict]:
    return {n["id"]: n for n in nodos if n.get("id")}


def validar_grafo(nodos: list[dict], conexiones: list[dict]) -> list[dict]:
    """Devuelve una lista de errores (vacía = grafo válido). Nunca lanza —
    un grafo mal formado es un resultado a mostrar, no una excepción."""
    errores: list[ErrorValidacion] = []

    if not nodos:
        return [ErrorValidacion("sin_nodos", "El workflow no tiene ningún nodo.").to_dict()]

    por_id = _index_nodos(nodos)
    ids_repetidos = len(por_id) != len(nodos)
    if ids_repetidos:
        errores.append(ErrorValidacion("ids_duplicados", "Hay nodos con el mismo id."))

    for n in nodos:
        if n.get("tipo") not in TIPOS_NODO:
            errores.append(ErrorValidacion("tipo_invalido", f"Tipo de nodo inválido: {n.get('tipo')}", n.get("id")))

    inicios = [n for n in nodos if n.get("tipo") == "inicio"]
    fines = [n for n in nodos if n.get("tipo") == "fin"]
    if len(inicios) != 1:
        errores.append(ErrorValidacion("inicio_invalido", f"Debe existir exactamente un nodo de inicio (hay {len(inicios)})."))
    if not fines:
        errores.append(ErrorValidacion("sin_fin", "Debe existir al menos un nodo de término."))

    # Conexiones rotas: origen/destino deben existir.
    conexiones_validas = []
    for c in conexiones:
        origen, destino = c.get("origen_nodo_id"), c.get("destino_nodo_id")
        if origen not in por_id or destino not in por_id:
            errores.append(ErrorValidacion(
                "conexion_rota", f"Conexión rota: {origen} → {destino}", origen,
            ))
            continue
        conexiones_validas.append(c)

    # Responsables: todo nodo de trabajo humano necesita rol o responsable.
    for n in nodos:
        if n.get("tipo") in TIPOS_REQUIEREN_RESPONSABLE:
            tiene_rol = bool(n.get("roles"))
            tiene_responsable = bool(n.get("responsables"))
            if not tiene_rol and not tiene_responsable:
                errores.append(ErrorValidacion(
                    "nodo_sin_responsable",
                    f"El nodo '{n.get('nombre', n['id'])}' no tiene rol ni responsable asignado.",
                    n["id"],
                ))

    # Cada resultado declarado debe tener salida. decision/autorizacion
    # siempre necesitan al menos un resultado (para eso existen); cualquier
    # otro tipo de etapa puede declarar sus propios resultados también (ej:
    # una revisión con "aprobar / aprobar con cambios / rechazar") — si no
    # declara ninguno, sigue bastando con una única conexión de salida.
    salidas_por_nodo: dict[str, set[str]] = {}
    for c in conexiones_validas:
        salidas_por_nodo.setdefault(c["origen_nodo_id"], set()).add(c.get("resultado") or "default")

    for n in nodos:
        resultados_declarados = set(n.get("resultados") or [])
        if n.get("tipo") in ("decision", "autorizacion") and not resultados_declarados:
            errores.append(ErrorValidacion(
                "decision_sin_resultados",
                f"El nodo '{n.get('nombre', n['id'])}' no declara resultados posibles.",
                n["id"],
            ))
            continue
        if resultados_declarados:
            salidas = salidas_por_nodo.get(n["id"], set())
            faltantes = resultados_declarados - salidas
            if faltantes:
                errores.append(ErrorValidacion(
                    "decision_sin_salida",
                    f"El nodo '{n.get('nombre', n['id'])}' no tiene conexión de salida para: {', '.join(sorted(faltantes))}.",
                    n["id"],
                ))
        elif n.get("tipo") != "fin" and n["id"] not in salidas_por_nodo:
            errores.append(ErrorValidacion(
                "nodo_sin_salida",
                f"El nodo '{n.get('nombre', n['id'])}' no tiene ninguna conexión de salida.",
                n["id"],
            ))

    # Alcanzabilidad desde el inicio (evita nodos huérfanos).
    if len(inicios) == 1:
        adyacencia: dict[str, list[str]] = {}
        for c in conexiones_validas:
            adyacencia.setdefault(c["origen_nodo_id"], []).append(c["destino_nodo_id"])

        alcanzables = {inicios[0]["id"]}
        pila = [inicios[0]["id"]]
        while pila:
            actual = pila.pop()
            for vecino in adyacencia.get(actual, []):
                if vecino not in alcanzables:
                    alcanzables.add(vecino)
                    pila.append(vecino)

        for n in nodos:
            if n["id"] not in alcanzables:
                errores.append(ErrorValidacion("nodo_inaccesible", f"El nodo '{n.get('nombre', n['id'])}' no es alcanzable desde el inicio.", n["id"]))

        # Ciclos infinitos evidentes: todo nodo alcanzable debe poder llegar a
        # un nodo de término. Si no puede, quedó atrapado en un loop sin salida
        # (una devolución legítima SIEMPRE tiene un camino de vuelta hacia
        # adelante y eventualmente a un fin; un ciclo sin escape no).
        adyacencia_inversa: dict[str, list[str]] = {}
        for c in conexiones_validas:
            adyacencia_inversa.setdefault(c["destino_nodo_id"], []).append(c["origen_nodo_id"])
        puede_llegar_a_fin = {f["id"] for f in fines}
        pila = list(puede_llegar_a_fin)
        while pila:
            actual = pila.pop()
            for vecino in adyacencia_inversa.get(actual, []):
                if vecino not in puede_llegar_a_fin:
                    puede_llegar_a_fin.add(vecino)
                    pila.append(vecino)
        for n in nodos:
            if n["id"] in alcanzables and n["id"] not in puede_llegar_a_fin and n.get("tipo") != "fin":
                errores.append(ErrorValidacion(
                    "ciclo_sin_salida",
                    f"El nodo '{n.get('nombre', n['id'])}' queda atrapado en un ciclo que nunca llega a un término.",
                    n["id"],
                ))

    return [e.to_dict() for e in errores]


def siguiente_nodo(conexiones: list[dict], nodo_actual_id: str, resultado: Optional[str] = None) -> Optional[str]:
    """Determinístico: dado un nodo y su resultado, cuál es el próximo. Si hay
    más de una conexión con el mismo (origen, resultado) — grafo mal armado —
    devuelve la primera de forma estable (ya lo habría marcado `validar_grafo`)."""
    clave = resultado or "default"
    for c in conexiones:
        if c.get("origen_nodo_id") == nodo_actual_id and (c.get("resultado") or "default") == clave:
            return c.get("destino_nodo_id")
    return None


def evaluar_condicion(condicion: Optional[dict], contexto: dict) -> bool:
    """Condición estructurada: {"campo": "monto_total", "operador": ">", "valor": 500000}.
    Sin condición, siempre es verdadera (nodo incondicional). Nunca ejecuta
    código arbitrario — solo compara valores ya tipados."""
    if not condicion:
        return True
    campo = condicion.get("campo")
    operador = condicion.get("operador")
    valor = condicion.get("valor")
    if campo not in CAMPOS_CONDICION_VALIDOS or operador not in OPERADORES_VALIDOS:
        return False
    actual = contexto.get(campo)
    if actual is None:
        return False
    try:
        if operador == ">":
            return actual > valor
        if operador == ">=":
            return actual >= valor
        if operador == "<":
            return actual < valor
        if operador == "<=":
            return actual <= valor
        if operador == "==":
            return actual == valor
        if operador == "!=":
            return actual != valor
        if operador == "in":
            return actual in valor
        if operador == "not in":
            return actual not in valor
    except TypeError:
        return False
    return False


def resolver_autorizadores(nodo: dict, decisiones: dict[str, str]) -> dict:
    """Para un nodo tipo 'autorizacion': quién(es) deben actuar ahora.

    `decisiones` es {responsable_id: "aprobado"|"rechazado"} de lo ya
    decidido para ESTE paso del workflow. Soporta:
    - paralela (default): todos los responsables asignados pueden actuar en
      cualquier orden; el nodo se resuelve cuando todos decidieron (o al
      primer rechazo, que corta antes).
    - secuencial: los responsables tienen `orden_autorizacion`; solo puede
      actuar el de menor orden que todavía no decidió.

    Devuelve {"pendientes": [...], "resuelto": bool, "resultado": str|None}.
    """
    responsables = nodo.get("responsables") or []
    modo = nodo.get("modo_autorizacion", "paralela")

    if any(decisiones.get(r["id"]) == "rechazado" for r in responsables):
        return {"pendientes": [], "resuelto": True, "resultado": "rechazado"}

    if modo == "secuencial":
        ordenados = sorted(responsables, key=lambda r: r.get("orden_autorizacion") or 0)
        for r in ordenados:
            if decisiones.get(r["id"]) is None:
                return {"pendientes": [r["id"]], "resuelto": False, "resultado": None}
        return {"pendientes": [], "resuelto": True, "resultado": "aprobado"}

    # Paralela
    pendientes = [r["id"] for r in responsables if decisiones.get(r["id"]) is None]
    if pendientes:
        return {"pendientes": pendientes, "resuelto": False, "resultado": None}
    return {"pendientes": [], "resuelto": True, "resultado": "aprobado"}


def procesar_evento(
    eventos_procesados: set[str], evento_id: str, aplicar_fn,
) -> dict:
    """Aplica `aplicar_fn()` solo si `evento_id` no se procesó antes. Mismo
    patrón de idempotencia que `supplier_capability_events`/`rfq_batches`:
    un reintento con el mismo id nunca duplica el efecto."""
    if evento_id in eventos_procesados:
        return {"aplicado": False, "motivo": "evento_ya_procesado"}
    resultado = aplicar_fn()
    eventos_procesados.add(evento_id)
    return {"aplicado": True, "resultado": resultado}
