"""Frontera entre "contexto interno" y "texto que lee un tercero".

Motivo concreto (2026-08-26, hilo 64f2e851): un correo a un proveedor salió con
la frase *"No considerar el modelo de alta potencia E27/E40 de $25.000."* Eso era
una instrucción de desambiguación interna —resolver un bug de precios nuestro—
que terminó en el buzón de Joaquín. En la misma sesión estuvo a punto de irse una
dirección de Buenos Aires como destino de despacho de un proveedor chileno.

La causa de fondo: los correos transaccionales pasan por `mail_template_service`,
que sólo acepta variables declaradas en una allowlist. Pero las tools MCP dejan
al modelo escribir el cuerpo libre (`update_rfq_draft`), y ese texto sale sin que
nada lo mire.

Este módulo es puro y determinístico: no consulta la DB ni llama a un modelo.

**Alcance honesto:** esto es una red, no un muro. Detecta marcas de deliberación
interna e identificadores que nunca deberían salir. No puede detectar que una
frase perfectamente redactada revele algo que no convenía decir — eso lo decide
una persona. Por eso `advierte` existe: hay filtraciones que sólo un humano
puede juzgar, y bloquearlas automáticamente rompería usos legítimos.
"""
import re
from dataclasses import dataclass

# Severidades. `bloquea` se reserva para lo que NUNCA es legítimo en un correo a
# un tercero; todo lo demás advierte y deja decidir a la persona. Bloquear de más
# es tan dañino como no bloquear: rompe flujos reales y enseña a ignorar el aviso.
BLOQUEA = "bloquea"
ADVIERTE = "advierte"


@dataclass(frozen=True)
class Hallazgo:
    codigo: str
    severidad: str
    fragmento: str
    motivo: str


_UUID = re.compile(
    r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I
)

# Frases de alto valor de señal: son deliberación interna, no comunicación con el
# proveedor. Deliberadamente cortas y pocas — una lista larga genera falsos
# positivos y termina desactivada.
_MARCAS_INTERNAS: tuple[tuple[str, str], ...] = (
    (r"no (?:considerar|tomar en cuenta|tener en cuenta)",
     "Es una instrucción de desambiguación interna, no algo que el proveedor deba leer."),
    # `intern[oa]`: "nota interna" es tan común como "uso interno".
    (r"(?:uso|nota|comentario|observaci[oó]n) intern[oa]",
     "Marca explícita de contenido interno."),
    (r"error (?:m[ií]o|nuestro|del sistema|de baiyer)",
     "Expone un problema interno del sistema al proveedor."),
    (r"\bbaiyer\b",
     "Nombra la herramienta interna de compras; el proveedor trata con tu empresa, no con ella."),
    (r"seg[uú]n (?:el|nuestro) (?:sistema|registro interno)",
     "Revela el funcionamiento interno del proceso."),
)


def revisar(
    texto: str,
    *,
    otros_proveedores: tuple[str, ...] = (),
    direcciones_internas: tuple[str, ...] = (),
) -> list[Hallazgo]:
    """Revisa un texto antes de que salga hacia un tercero.

    `otros_proveedores` son nombres de proveedores distintos del destinatario:
    nombrarlos le revela con quién más estás cotizando. A veces es deliberado
    ("¿tenés estas dos alternativas?"), así que advierte en vez de bloquear.
    """
    hallazgos: list[Hallazgo] = []
    if not (texto or "").strip():
        return hallazgos

    for match in _UUID.finditer(texto):
        hallazgos.append(Hallazgo(
            codigo="identificador_interno", severidad=BLOQUEA, fragmento=match.group(0),
            motivo="Es un identificador interno del sistema; no significa nada para el proveedor.",
        ))

    for patron, motivo in _MARCAS_INTERNAS:
        for match in re.finditer(patron, texto, re.I):
            hallazgos.append(Hallazgo(
                codigo="deliberacion_interna", severidad=BLOQUEA,
                fragmento=_contexto(texto, match.start(), match.end()), motivo=motivo,
            ))

    for nombre in otros_proveedores:
        limpio = (nombre or "").strip()
        if len(limpio) < 3:
            continue  # un nombre de dos letras haría match con cualquier cosa
        for match in re.finditer(re.escape(limpio), texto, re.I):
            hallazgos.append(Hallazgo(
                codigo="proveedor_competidor", severidad=ADVIERTE,
                fragmento=_contexto(texto, match.start(), match.end()),
                motivo=f"Nombra a {limpio}, otro proveedor de esta cotización.",
            ))

    for direccion in direcciones_internas:
        limpia = (direccion or "").strip()
        if len(limpia) < 8:
            continue
        if limpia.lower() in texto.lower():
            hallazgos.append(Hallazgo(
                codigo="direccion_no_verificada", severidad=ADVIERTE, fragmento=limpia,
                motivo="Es la dirección administrativa del emisor, no una dirección de despacho verificada.",
            ))

    return hallazgos


def _contexto(texto: str, inicio: int, fin: int, margen: int = 30) -> str:
    """Fragmento con algo de contexto alrededor, para que el aviso sea accionable
    en vez de nombrar una palabra suelta."""
    desde, hasta = max(0, inicio - margen), min(len(texto), fin + margen)
    fragmento = texto[desde:hasta].replace("\n", " ").strip()
    return f"{'…' if desde else ''}{fragmento}{'…' if hasta < len(texto) else ''}"


def bloqueantes(hallazgos: list[Hallazgo]) -> list[Hallazgo]:
    return [h for h in hallazgos if h.severidad == BLOQUEA]


def como_dict(hallazgos: list[Hallazgo]) -> list[dict]:
    """Forma serializable, para que el cliente MCP pueda mostrarle los avisos a
    la persona en vez de que el modelo los resuma."""
    return [
        {"codigo": h.codigo, "severidad": h.severidad,
         "fragmento": h.fragmento, "motivo": h.motivo}
        for h in hallazgos
    ]
