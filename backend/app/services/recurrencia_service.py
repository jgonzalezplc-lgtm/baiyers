"""Servicio de compras recurrentes."""
import calendar as cal_module
from datetime import datetime, timezone, timedelta
from typing import Optional


def calcular_proxima_ejecucion(frecuencia: str, dia_ejecucion: Optional[int], desde: datetime) -> datetime:
    """Calcula la próxima fecha de ejecución según la frecuencia."""
    meses_map = {"mensual": 1, "bimestral": 2, "trimestral": 3, "anual": 12}

    if frecuencia == "diaria":
        return desde + timedelta(days=1)
    elif frecuencia == "semanal":
        return desde + timedelta(weeks=1)
    elif frecuencia in meses_map:
        meses = meses_map[frecuencia]
        mes_total = desde.month + meses
        año = desde.year + (mes_total - 1) // 12
        mes = ((mes_total - 1) % 12) + 1
        dia = dia_ejecucion or desde.day
        max_dia = cal_module.monthrange(año, mes)[1]
        return desde.replace(year=año, month=mes, day=min(dia, max_dia),
                             hour=9, minute=0, second=0, microsecond=0)
    return desde + timedelta(days=30)


def ejecutar_recurrencia(recurrencia_id: str) -> dict:
    from app.services.supabase import get_supabase
    sb = get_supabase()

    try:
        res = sb.table("recurrencias").select("*").eq("id", recurrencia_id).single().execute()
        if not res.data:
            return {"success": False, "error": "Recurrencia no encontrada"}

        rec = res.data
        if not rec.get("activa"):
            return {"success": False, "error": "Recurrencia inactiva"}

        # Obtener proveedor preferido
        proveedor_nombre = ""
        proveedor_email = None
        if rec.get("proveedor_id"):
            prov_res = sb.table("proveedores").select("nombre, email").eq("id", rec["proveedor_id"]).single().execute()
            if prov_res.data:
                proveedor_nombre = prov_res.data.get("nombre", "")
                proveedor_email = prov_res.data.get("email")

        resultado_texto = ""

        if rec.get("cotizar_antes"):
            # Enviar email de cotización al proveedor preferido
            resultado_texto = f"Solicitud enviada a {proveedor_nombre or 'proveedor'}"
            if proveedor_email:
                try:
                    gmail_res = sb.table("user_integrations").select("*").eq("user_id", rec["user_id"]).eq("provider", "gmail").single().execute()
                    if gmail_res.data:
                        from app.services.gmail_service import get_gmail_service, send_email
                        integration = gmail_res.data
                        service, _ = get_gmail_service(integration["access_token"], integration["refresh_token"])
                        send_email(
                            service=service,
                            to=proveedor_email,
                            subject=f"Solicitud de cotización — {rec['nombre']}",
                            body=(
                                f"Estimado/a {proveedor_nombre},\n\n"
                                f"Necesitamos cotización para los siguientes ítems:\n\n{rec['items']}\n\n"
                                f"Por favor envíenos precios, disponibilidad y plazo de entrega.\n\n"
                                f"Saludos,\nEquipo Claria\nhola@claria.cc"
                            ),
                            from_email=integration["email"],
                        )
                except Exception as e:
                    resultado_texto = f"Error enviando email: {e}"
        else:
            # Emitir OC con último precio conocido
            resultado_texto = "Sin precio disponible para OC directa"
            if proveedor_nombre:
                ocs_prev = sb.table("ordenes_compra").select("precio_unitario, moneda").eq("user_id", rec["user_id"]).eq("proveedor_nombre", proveedor_nombre).order("created_at", desc=True).limit(1).execute()
                if ocs_prev.data and ocs_prev.data[0].get("precio_unitario"):
                    precio = ocs_prev.data[0]["precio_unitario"]
                    moneda = ocs_prev.data[0].get("moneda", "CLP")
                    if rec.get("monto_maximo") and precio > rec["monto_maximo"]:
                        resultado_texto = f"Monto ${precio:,.0f} supera máximo ${rec['monto_maximo']:,.0f}. Requiere aprobación."
                        _notificar_aprobacion(rec, precio, proveedor_nombre)
                    else:
                        resultado_texto = f"OC directa registrada — ${precio:,.0f} {moneda}"

        # Actualizar próxima ejecución
        proxima = calcular_proxima_ejecucion(
            rec["frecuencia"], rec.get("dia_ejecucion"), datetime.now(timezone.utc)
        )
        sb.table("recurrencias").update({"proxima_ejecucion": proxima.isoformat()}).eq("id", recurrencia_id).execute()

        # Log de auditoría — cada trigger queda registrado
        modo = rec.get("modo") or ("re_cotizar" if rec.get("cotizar_antes") else "oc_directa")
        try:
            sb.table("recurrencias_log").insert({
                "recurrencia_id": recurrencia_id,
                "resultado": resultado_texto,
            }).execute()
        except Exception:
            pass
        try:
            sb.table("recurrencia_logs").insert({
                "recurrencia_id": recurrencia_id,
                "user_id": rec["user_id"],
                "modo": modo,
                "resultado": resultado_texto,
                "exitoso": True,
            }).execute()
        except Exception:
            pass  # tabla aún no migrada

        print(f"[Recurrencia] '{rec['nombre']}': {resultado_texto}")
        return {"success": True, "resultado": resultado_texto}

    except Exception as e:
        print(f"[Recurrencia] Error en {recurrencia_id}: {e}")
        return {"success": False, "error": str(e)}


def _notificar_aprobacion(rec: dict, monto: float, proveedor_nombre: str):
    from app.services.supabase import get_supabase
    sb = get_supabase()
    try:
        gmail_res = sb.table("user_integrations").select("*").eq("user_id", rec["user_id"]).eq("provider", "gmail").single().execute()
        if gmail_res.data:
            from app.services.gmail_service import get_gmail_service, send_email
            from app.config import settings
            integration = gmail_res.data
            service, _ = get_gmail_service(integration["access_token"], integration["refresh_token"])
            send_email(
                service=service,
                to=integration["email"],
                subject=f"Aprobacion requerida — {rec['nombre']}",
                body=(
                    f"La recurrencia '{rec['nombre']}' no se ejecutó automáticamente.\n\n"
                    f"Motivo: el monto ${monto:,.0f} supera el máximo autorizado de ${rec['monto_maximo']:,.0f}.\n\n"
                    f"Proveedor: {proveedor_nombre}\n\n"
                    f"Ingresa al sistema para aprobar manualmente:\n{settings.frontend_url}/recurrencias"
                ),
                from_email=integration["email"],
            )
    except Exception as e:
        print(f"[Recurrencia] Error notificando aprobación: {e}")


def check_recurrencias():
    """Cron: ejecuta recurrencias vencidas."""
    from app.services.supabase import get_supabase
    sb = get_supabase()
    now = datetime.now(timezone.utc).isoformat()
    try:
        pendientes = sb.table("recurrencias").select("id, nombre").lte("proxima_ejecucion", now).eq("activa", True).execute()
        for rec in pendientes.data:
            try:
                ejecutar_recurrencia(rec["id"])
            except Exception as e:
                print(f"[Recurrencia Cron] Error en '{rec['nombre']}': {e}")
    except Exception as e:
        print(f"[Recurrencia Cron] Error general: {e}")
