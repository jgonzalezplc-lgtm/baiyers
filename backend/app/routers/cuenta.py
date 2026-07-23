"""Gestión de la cuenta del usuario: eliminar cuenta (darse de baja)."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/cuenta", tags=["cuenta"])


class EliminarRequest(BaseModel):
    access_token: str


@router.post("/eliminar")
async def eliminar_cuenta(req: EliminarRequest):
    """Elimina la cuenta del usuario autenticado. Verifica el token para que
    cada quien solo pueda borrarse a sí mismo, luego borra sus datos y el usuario auth."""
    from app.services.supabase import get_supabase
    sb = get_supabase()

    # 1) Verificar el token → obtener el user_id real (no confiar en el cliente)
    try:
        res = sb.auth.get_user(req.access_token)
        user = getattr(res, "user", None) or (res.get("user") if isinstance(res, dict) else None)
        uid = user.id if hasattr(user, "id") else (user.get("id") if user else None)
    except Exception:
        uid = None
    if not uid:
        raise HTTPException(status_code=401, detail="Token inválido")

    # 2) Borrar datos propios (best-effort; RLS no aplica con service key)
    for tabla in ("resultados", "cotizaciones", "proyectos", "proveedores", "ordenes_compra"):
        try:
            sb.table(tabla).delete().eq("user_id", uid).execute()
        except Exception:
            pass  # tabla puede no tener user_id o no existir; no bloquea

    # 3) Borrar el usuario de auth (permite re-registrarse con el mismo correo)
    try:
        sb.auth.admin.delete_user(uid)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"No se pudo eliminar la cuenta: {e}")

    return {"success": True}
