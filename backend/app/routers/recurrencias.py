from typing import Optional
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/recurrencias", tags=["recurrencias"])


class RecurrenciaRequest(BaseModel):
    user_id: str
    nombre: str
    items: str
    frecuencia: str  # diaria|semanal|mensual|bimestral|trimestral|anual
    dia_ejecucion: Optional[int] = None
    proveedor_id: Optional[str] = None
    cotizar_antes: bool = True
    monto_maximo: Optional[float] = None
    dias_aviso: int = 3
    # v2 — modo explícito: re_cotizar | oc_directa | a_aprobacion
    modo: Optional[str] = None


@router.get("")
async def listar_recurrencias(user_id: str):
    from app.services.supabase import get_supabase
    sb = get_supabase()
    res = sb.table("recurrencias").select("*, proveedores(nombre)").eq("user_id", user_id).order("created_at", desc=True).execute()
    return res.data


@router.post("")
async def crear_recurrencia(req: RecurrenciaRequest):
    from app.services.supabase import get_supabase
    from app.services.recurrencia_service import calcular_proxima_ejecucion
    sb = get_supabase()

    frecuencias_validas = {"diaria", "semanal", "mensual", "bimestral", "trimestral", "anual"}
    if req.frecuencia not in frecuencias_validas:
        raise HTTPException(status_code=400, detail=f"Frecuencia inválida. Usa: {frecuencias_validas}")

    proxima = calcular_proxima_ejecucion(req.frecuencia, req.dia_ejecucion, datetime.now(timezone.utc))

    # Modo explícito v2 → traduce a los flags existentes
    cotizar_antes = req.cotizar_antes
    if req.modo:
        if req.modo not in ("re_cotizar", "oc_directa", "a_aprobacion"):
            raise HTTPException(status_code=400, detail="modo debe ser re_cotizar, oc_directa o a_aprobacion")
        cotizar_antes = req.modo == "re_cotizar"
        # a_aprobacion = OC directa que siempre pasa por aprobación (monto_maximo=0)
        if req.modo == "a_aprobacion" and req.monto_maximo is None:
            req.monto_maximo = 0

    row = {
        "user_id": req.user_id,
        "nombre": req.nombre,
        "items": req.items,
        "frecuencia": req.frecuencia,
        "dia_ejecucion": req.dia_ejecucion,
        "proveedor_id": req.proveedor_id,
        "cotizar_antes": cotizar_antes,
        "monto_maximo": req.monto_maximo,
        "dias_aviso": req.dias_aviso,
        "proxima_ejecucion": proxima.isoformat(),
        "activa": True,
    }
    if req.modo:
        row["modo"] = req.modo

    try:
        res = sb.table("recurrencias").insert(row).execute()
    except Exception:
        # columna modo aún no migrada
        row.pop("modo", None)
        res = sb.table("recurrencias").insert(row).execute()
    return res.data[0]


@router.put("/{recurrencia_id}")
async def actualizar_recurrencia(recurrencia_id: str, req: RecurrenciaRequest):
    from app.services.supabase import get_supabase
    from app.services.recurrencia_service import calcular_proxima_ejecucion
    sb = get_supabase()

    existe = sb.table("recurrencias").select("id").eq("id", recurrencia_id).eq("user_id", req.user_id).single().execute()
    if not existe.data:
        raise HTTPException(status_code=404, detail="Recurrencia no encontrada")

    proxima = calcular_proxima_ejecucion(req.frecuencia, req.dia_ejecucion, datetime.now(timezone.utc))

    sb.table("recurrencias").update({
        "nombre": req.nombre,
        "items": req.items,
        "frecuencia": req.frecuencia,
        "dia_ejecucion": req.dia_ejecucion,
        "proveedor_id": req.proveedor_id,
        "cotizar_antes": req.cotizar_antes,
        "monto_maximo": req.monto_maximo,
        "dias_aviso": req.dias_aviso,
        "proxima_ejecucion": proxima.isoformat(),
    }).eq("id", recurrencia_id).execute()

    return {"success": True}


@router.delete("/{recurrencia_id}")
async def eliminar_recurrencia(recurrencia_id: str, user_id: str):
    from app.services.supabase import get_supabase
    sb = get_supabase()
    sb.table("recurrencias").delete().eq("id", recurrencia_id).eq("user_id", user_id).execute()
    return {"success": True}


@router.patch("/{recurrencia_id}/toggle")
async def toggle_recurrencia(recurrencia_id: str, user_id: str):
    from app.services.supabase import get_supabase
    sb = get_supabase()
    actual = sb.table("recurrencias").select("activa").eq("id", recurrencia_id).eq("user_id", user_id).single().execute()
    if not actual.data:
        raise HTTPException(status_code=404, detail="Recurrencia no encontrada")
    nueva = not actual.data["activa"]
    sb.table("recurrencias").update({"activa": nueva}).eq("id", recurrencia_id).execute()
    return {"activa": nueva}


@router.post("/{recurrencia_id}/ejecutar")
async def ejecutar_ahora(recurrencia_id: str, user_id: str):
    from app.services.supabase import get_supabase
    from app.services.recurrencia_service import ejecutar_recurrencia
    sb = get_supabase()

    existe = sb.table("recurrencias").select("id").eq("id", recurrencia_id).eq("user_id", user_id).single().execute()
    if not existe.data:
        raise HTTPException(status_code=404, detail="Recurrencia no encontrada")

    resultado = ejecutar_recurrencia(recurrencia_id)
    return resultado
