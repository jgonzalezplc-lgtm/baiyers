"""
Supplier Intelligence — actualiza scores y programa emails de rating.
Todas las funciones son síncronas para compatibilidad con el cron job.
"""
from datetime import datetime, timezone, timedelta
from typing import Optional


def _sb():
    from app.services.supabase import get_supabase
    return get_supabase()


def _get_or_create_proveedor(user_id: str, nombre: str, email: Optional[str] = None) -> Optional[str]:
    """Retorna el id del proveedor, creándolo si no existe."""
    sb = _sb()
    # Buscar por email si existe
    if email:
        res = sb.table("proveedores").select("id").eq("user_id", user_id).eq("email", email).execute()
        if res.data:
            return res.data[0]["id"]
    # Buscar por nombre
    res = sb.table("proveedores").select("id").eq("user_id", user_id).eq("nombre", nombre[:200]).execute()
    if res.data:
        return res.data[0]["id"]
    # Crear
    try:
        ins = sb.table("proveedores").insert({
            "user_id": user_id,
            "nombre": nombre[:200],
            "email": email,
            "score": 50,
            "categoria_score": "confiable",
        }).execute()
        return ins.data[0]["id"]
    except Exception as e:
        print(f"[SI] Error creando proveedor: {e}")
        return None


def _obtener_rating_promedio(proveedor_id: str) -> float:
    sb = _sb()
    try:
        res = sb.table("supplier_ratings").select("estrellas").eq("proveedor_id", proveedor_id).execute()
        if res.data:
            return sum(r["estrellas"] for r in res.data) / len(res.data)
    except Exception:
        pass
    return 3.0


def calcular_score(proveedor_id: str) -> int:
    sb = _sb()
    try:
        res = sb.table("proveedores").select("*").eq("id", proveedor_id).single().execute()
        if not res.data:
            return 50
        p = res.data

        total_sol = p.get("total_solicitudes") or 0
        total_res = p.get("total_respuestas") or 0
        tiempo_avg = p.get("tiempo_respuesta_horas_avg") or 0
        total_oc_env = p.get("total_oc_enviadas") or 0
        total_oc_con = p.get("total_oc_confirmadas") or 0

        # Tasa de respuesta (0-25 pts)
        tasa_respuesta = total_res / max(total_sol, 1)
        pts_respuesta = tasa_respuesta * 25

        # Velocidad de respuesta (0-25 pts)
        if total_avg := tiempo_avg:
            if total_avg <= 24:
                pts_velocidad = 25
            elif total_avg <= 48:
                pts_velocidad = 20
            elif total_avg <= 72:
                pts_velocidad = 15
            elif total_avg <= 168:
                pts_velocidad = 5
            else:
                pts_velocidad = 0
        else:
            pts_velocidad = 12  # neutral si no hay datos

        # Tasa de cumplimiento OC (0-25 pts)
        tasa_oc = total_oc_con / max(total_oc_env, 1)
        pts_cumplimiento = tasa_oc * 25

        # Rating promedio (0-25 pts)
        rating_avg = _obtener_rating_promedio(proveedor_id)
        pts_rating = (rating_avg / 5) * 25

        score = pts_respuesta + pts_velocidad + pts_cumplimiento + pts_rating
        score = max(0, min(100, int(score)))

        if score >= 80:
            categoria = "preferido"
        elif score >= 60:
            categoria = "confiable"
        elif score >= 40:
            categoria = "con_reparos"
        elif score >= 20:
            categoria = "problematico"
        else:
            categoria = "bloqueado_auto"

        sb.table("proveedores").update({"score": score, "categoria_score": categoria}).eq("id", proveedor_id).execute()
        return score
    except Exception as e:
        print(f"[SI] Error calculando score: {e}")
        return 50


def registrar_solicitud(user_id: str, proveedor_nombre: str, proveedor_email: Optional[str] = None) -> Optional[str]:
    """Incrementa solicitudes y retorna proveedor_id."""
    proveedor_id = _get_or_create_proveedor(user_id, proveedor_nombre, proveedor_email)
    if not proveedor_id:
        return None
    sb = _sb()
    try:
        res = sb.table("proveedores").select("total_solicitudes").eq("id", proveedor_id).single().execute()
        current = res.data.get("total_solicitudes") or 0
        sb.table("proveedores").update({"total_solicitudes": current + 1}).eq("id", proveedor_id).execute()
        calcular_score(proveedor_id)
    except Exception as e:
        print(f"[SI] Error registrar_solicitud: {e}")
    return proveedor_id


def registrar_oc_enviada(user_id: str, proveedor_nombre: str, proveedor_email: Optional[str] = None) -> Optional[str]:
    proveedor_id = _get_or_create_proveedor(user_id, proveedor_nombre, proveedor_email)
    if not proveedor_id:
        return None
    sb = _sb()
    try:
        res = sb.table("proveedores").select("total_oc_enviadas").eq("id", proveedor_id).single().execute()
        current = res.data.get("total_oc_enviadas") or 0
        sb.table("proveedores").update({"total_oc_enviadas": current + 1}).eq("id", proveedor_id).execute()
        calcular_score(proveedor_id)
    except Exception as e:
        print(f"[SI] Error registrar_oc_enviada: {e}")
    return proveedor_id


def registrar_oc_confirmada(oc_id: str):
    sb = _sb()
    try:
        oc_res = sb.table("ordenes_compra").select("user_id, proveedor_nombre, proveedor_email").eq("id", oc_id).single().execute()
        if not oc_res.data:
            return
        oc = oc_res.data
        proveedor_id = _get_or_create_proveedor(oc["user_id"], oc.get("proveedor_nombre", ""), oc.get("proveedor_email"))
        if not proveedor_id:
            return
        res = sb.table("proveedores").select("total_oc_confirmadas").eq("id", proveedor_id).single().execute()
        current = res.data.get("total_oc_confirmadas") or 0
        sb.table("proveedores").update({"total_oc_confirmadas": current + 1}).eq("id", proveedor_id).execute()
        calcular_score(proveedor_id)
    except Exception as e:
        print(f"[SI] Error registrar_oc_confirmada: {e}")


def programar_rating(oc_id: str):
    """Programa el envío del email de rating 7 días después."""
    sb = _sb()
    try:
        oc_res = sb.table("ordenes_compra").select("user_id, proveedor_nombre, proveedor_email").eq("id", oc_id).single().execute()
        if not oc_res.data:
            return
        oc = oc_res.data
        proveedor_id = _get_or_create_proveedor(oc["user_id"], oc.get("proveedor_nombre", ""), oc.get("proveedor_email"))
        enviar_en = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
        sb.table("rating_pendiente").insert({
            "oc_id": oc_id,
            "user_id": oc["user_id"],
            "proveedor_id": proveedor_id,
            "enviar_en": enviar_en,
            "enviado": False,
        }).execute()
    except Exception as e:
        print(f"[SI] Error programar_rating: {e}")
