"""Registro auditable de un campo extraído de un correo de proveedor.

Existe para que la auditoría (`item_field_updates`) no pueda afirmar que un
valor se aplicó si la escritura en `resultados` no ocurrió.

El orden importa y es el punto entero del módulo: no hay transacción disponible
sobre PostgREST, así que se elige el orden cuyo modo de falla es inocuo.

    insertar como propuesta → aplicar en `resultados` → marcar "aplicado"

Si el paso del medio falla, la fila queda como `propuesta` pendiente de revisión
humana: subestima lo hecho, que es recuperable. El orden inverso (marcar
"aplicado" antes de aplicar, que es como estaba en `gmail.py` y `outlook.py`)
deja la auditoría mintiendo sobre un dato que nunca se escribió, y eso ya
ocurrió con datos reales en producción.

Vive acá y no en un router porque el agente de Gmail y el de Outlook tenían el
mismo bloque duplicado —por eso el bug existía dos veces— y cualquier arreglo
que toque sólo uno vuelve a desincronizarlos.
"""
from typing import Any, Callable, Optional


def registrar_actualizacion_campo(
    sb,
    fila: dict,
    *,
    auto_aplicar: bool,
    agente: str,
    cuando_iso: str,
    aplicar: Callable[[], Any],
) -> Optional[str]:
    """Inserta la propuesta y, si corresponde auto-aplicarla, la aplica y recién
    entonces la marca como aplicada.

    `fila` no debe traer `estado`/`reviewed_*`: los pone esta función. La tabla
    tiene `estado NOT NULL DEFAULT 'propuesta'`, así que insertar sin ese campo
    deja la fila en el estado honesto por defecto.

    `aplicar` es la escritura real en `resultados` (distinta en cada router).
    Si lanza, la excepción se propaga sin haber marcado nada como aplicado.

    Devuelve el id de la propuesta, o None si el insert no lo devolvió — en ese
    caso no se marca nada, porque marcar a ciegas es justamente lo que se está
    corrigiendo.
    """
    insercion = sb.table("item_field_updates").insert(fila).execute()
    filas = getattr(insercion, "data", None) or [{}]
    propuesta_id = (filas[0] or {}).get("id")

    if not auto_aplicar:
        return propuesta_id

    aplicar()

    if propuesta_id:
        sb.table("item_field_updates").update({
            "estado": "aplicado",
            "updated_by": agente,
            "reviewed_at": cuando_iso,
            "reviewed_by": f"{agente}_auto",
        }).eq("id", propuesta_id).execute()

    return propuesta_id
