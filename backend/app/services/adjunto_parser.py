"""De un adjunto de correo a algo que Gemini pueda leer.

POR QUÉ EXISTE
--------------
En Chile la cotización viene adjunta: el cuerpo dice "estimado, adjunto valores"
y el precio está en un PDF o en una planilla. Hasta ahora el agente de Gmail
guardaba sólo metadata del adjunto (`gmail_attachments`), así que ese correo
entraba al sistema como una respuesta sin datos y alguien transcribía el PDF a
mano.

QUÉ DECIDE ESTE MÓDULO
----------------------
Sólo la parte cara y peligrosa: **qué se descarga y qué no**. Cada adjunto que
pasa de acá es una llamada paga a Gemini, y el cron de correo corre cada minuto
sobre todos los usuarios — un filtro flojo no da un bug de correctitud, da una
factura. Por eso el criterio es allowlist y no denylist: un formato que no
sabemos leer no se descarga siquiera.

La interpretación del contenido NO vive acá: eso sigue siendo
`email_understanding.extraer_actualizaciones()`, el mismo camino que ya usa el
cuerpo del correo. Este módulo entrega el material y se va.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Optional

# Mismo tope que `purchase_invoice_service.preview_invoice_import`. No hay razón
# para que un adjunto de correo tenga un límite distinto al de un archivo subido
# a mano, y dos números distintos sólo se desincronizan.
MAX_BYTES = 15 * 1024 * 1024

# Gemini acepta PDF e imágenes como bytes; Office no, por eso ese grupo pasa
# antes por `documentos.texto_office()`.
MIMES_BINARIOS = frozenset({
    "application/pdf",
    "image/png", "image/jpeg", "image/jpg", "image/webp",
})
EXTENSIONES_BINARIAS = (".pdf", ".png", ".jpg", ".jpeg", ".webp")

# Word queda deliberadamente afuera: casi nadie cotiza en .docx, y cada formato
# admitido es superficie de ataque y costo. `texto_office` igual lo soporta si
# algún día se decide agregarlo — es una línea.
EXTENSIONES_OFFICE = (".xlsx", ".xlsm", ".xls")


@dataclass(frozen=True)
class Documento:
    """Un adjunto listo para que lo lea el modelo.

    Trae exactamente una de las dos formas: `parte` (bytes + mime, para PDF e
    imágenes) o `texto` (para planillas ya convertidas).
    """

    filename: str
    sha256: str
    parte: Optional[dict] = None      # {"mime_type": str, "data": bytes}
    texto: Optional[str] = None

    @property
    def resumen_auditoria(self) -> str:
        """Lo que se guarda en `gmail_attachments.texto_extraido`.

        Para una planilla es el texto real; para un PDF no tenemos el texto (lo
        leyó el modelo directamente), así que se deja constancia de que se
        procesó y con qué hash. Sirve para dos cosas distintas y las dos
        importan: auditar de dónde salió un precio, y saber que este adjunto ya
        se parseó.
        """
        if self.texto is not None:
            return self.texto[:20_000]
        return f"[procesado como {self.parte['mime_type']} · sha256:{self.sha256[:16]}]"


def es_parseable(filename: Optional[str], mime_type: Optional[str]) -> bool:
    """¿Vale la pena gastar una descarga y una llamada al modelo en esto?

    Se mira el mime y la extensión porque ninguno de los dos es confiable solo:
    Gmail manda `application/octet-stream` para adjuntos que sí son PDF, y hay
    clientes de correo que mandan la extensión correcta con un mime genérico.
    """
    nombre = (filename or "").lower()
    mime = (mime_type or "").lower().split(";")[0].strip()
    if mime in MIMES_BINARIOS:
        return True
    return nombre.endswith(EXTENSIONES_BINARIAS) or nombre.endswith(EXTENSIONES_OFFICE)


def _mime_para_gemini(filename: str, mime_type: Optional[str]) -> str:
    mime = (mime_type or "").lower().split(";")[0].strip()
    if mime in MIMES_BINARIOS:
        return "image/jpeg" if mime == "image/jpg" else mime
    nombre = filename.lower()
    if nombre.endswith(".pdf"):
        return "application/pdf"
    if nombre.endswith(".png"):
        return "image/png"
    if nombre.endswith(".webp"):
        return "image/webp"
    return "image/jpeg"


def _tiene_contenido(texto: str) -> bool:
    """¿Esta planilla dice algo, o son sólo los encabezados de hoja?

    `texto_office` emite una línea `[HOJA: x]` por hoja aunque estén todas
    vacías, así que un `.strip()` a secas da verdadero para un libro en blanco —
    y eso es una llamada paga a Gemini a cambio de nada.
    """
    return any(
        linea.strip() and not linea.startswith("[HOJA:")
        for linea in texto.splitlines()
    )


def preparar_adjunto(service, gmail_message_id: str, adjunto: dict) -> Optional[Documento]:
    """Descarga y normaliza un adjunto. Devuelve None si no corresponde procesarlo.

    `adjunto` es una fila de `gmail_attachments` (se lee de la tabla y no de la
    respuesta de la API a propósito: el insert de adjuntos sólo corre para
    mensajes nuevos, así que depender de la memoria haría que un mensaje
    guardado a medias nunca se recupere).

    Nunca lanza. Un adjunto ilegible no puede tumbar la sincronización del
    correo entero — el cuerpo del mensaje todavía tiene que procesarse. Mismo
    criterio que `_registrar_lineas` en `routers/gmail.py`.
    """
    filename = adjunto.get("filename") or ""
    if not es_parseable(filename, adjunto.get("mime_type")):
        return None
    attachment_id = adjunto.get("gmail_attachment_id")
    if not attachment_id:
        return None

    try:
        from app.services.gmail_service import descargar_adjunto

        data = descargar_adjunto(service, gmail_message_id, attachment_id)
    except Exception as exc:  # noqa: BLE001 — ver docstring
        print(f"[adjunto_parser] no se pudo descargar {filename}: {type(exc).__name__}: {exc}")
        return None

    if not data or len(data) > MAX_BYTES:
        # El tope se comprueba después de descargar porque el `size` que trae
        # Gmail es del cuerpo codificado y no del archivo real. Igual corta
        # antes de Gemini, que es donde está el costo.
        if data:
            print(f"[adjunto_parser] {filename} supera {MAX_BYTES} bytes; se omite")
        return None

    sha256 = hashlib.sha256(data).hexdigest()
    nombre = filename.lower()

    if nombre.endswith(EXTENSIONES_OFFICE):
        try:
            from app.services.documentos import texto_office

            texto = texto_office(data, filename)
        except Exception as exc:  # noqa: BLE001 — incluye el HTTPException de texto_office
            print(f"[adjunto_parser] no se pudo leer la planilla {filename}: {exc}")
            return None
        if not _tiene_contenido(texto):
            return None
        return Documento(filename=filename, sha256=sha256, texto=texto)

    return Documento(
        filename=filename,
        sha256=sha256,
        parte={"mime_type": _mime_para_gemini(filename, adjunto.get("mime_type")), "data": data},
    )
