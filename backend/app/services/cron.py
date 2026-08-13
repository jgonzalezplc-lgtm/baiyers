"""Cron job para enviar emails de rating post-compra."""
from apscheduler.schedulers.background import BackgroundScheduler


def _enviar_ratings_pendientes():
    from datetime import datetime, timezone
    from app.services.supabase import get_supabase
    from app.services.gmail_service import get_gmail_service, send_email
    from app.config import settings

    sb = get_supabase()
    now = datetime.now(timezone.utc).isoformat()

    try:
        pendientes = sb.table("rating_pendiente").select("*").lte("enviar_en", now).eq("enviado", False).execute()
    except Exception as e:
        print(f"[Cron] Error obteniendo pendientes: {e}")
        return

    for item in pendientes.data:
        try:
            gmail_res = sb.table("user_integrations").select("*").eq("user_id", item["user_id"]).eq("provider", "gmail").single().execute()
            if not gmail_res.data:
                continue

            integration = gmail_res.data
            service, _ = get_gmail_service(integration["access_token"], integration["refresh_token"])

            proveedor_res = sb.table("proveedores").select("nombre").eq("id", item["proveedor_id"]).single().execute()
            proveedor_nombre = proveedor_res.data["nombre"] if proveedor_res.data else "el proveedor"

            oc_id = item["oc_id"]
            rating_url = f"{settings.frontend_url}/rating/{oc_id}"

            send_email(
                service=service,
                to=integration["email"],
                subject=f"¿Cómo fue tu experiencia con {proveedor_nombre}?",
                body=(
                    f"Hace 7 días recibiste la OC de {proveedor_nombre}.\n\n"
                    f"Califica tu experiencia aquí:\n{rating_url}\n\n"
                    f"Tu feedback nos ayuda a mejorar la inteligencia del sistema.\n\n"
                    f"Equipo Claria\nhola@claria.cc"
                ),
                from_email=integration["email"],
            )

            sb.table("rating_pendiente").update({"enviado": True}).eq("id", item["id"]).execute()
            print(f"[Cron] Rating enviado para OC {oc_id}")

        except Exception as e:
            print(f"[Cron] Error enviando rating {item['id']}: {e}")


def _check_recurrencias():
    from app.services.recurrencia_service import check_recurrencias
    check_recurrencias()


def _sincronizar_gmail():
    """El usuario no debería tener que acordarse de apretar 'Sincronizar
    respuestas' — el agente revisa Gmail solo cada pocos minutos."""
    import asyncio
    from app.routers.gmail import sincronizar_todos_los_usuarios

    try:
        resultado = asyncio.run(sincronizar_todos_los_usuarios())
        if resultado.get("usuarios_revisados"):
            print(f"[Cron] Gmail sync: {resultado}")
    except Exception as e:
        print(f"[Cron] Error en sync de Gmail: {e}")


def _sincronizar_outlook():
    """Equivalente a `_sincronizar_gmail` pero para el agente de Outlook —
    mismo cron de 1 minuto, job aparte para que un error en un proveedor no
    afecte al otro."""
    import asyncio
    from app.routers.outlook import sincronizar_todos_los_usuarios_outlook

    try:
        resultado = asyncio.run(sincronizar_todos_los_usuarios_outlook())
        if resultado.get("usuarios_revisados"):
            print(f"[Cron] Outlook sync: {resultado}")
    except Exception as e:
        print(f"[Cron] Error en sync de Outlook: {e}")


def start_cron():
    scheduler = BackgroundScheduler()
    scheduler.add_job(_enviar_ratings_pendientes, "interval", hours=1, id="ratings_cron")
    scheduler.add_job(_check_recurrencias, "interval", hours=1, id="recurrencias_cron")
    scheduler.add_job(_sincronizar_gmail, "interval", minutes=1, id="gmail_sync_cron")
    scheduler.add_job(_sincronizar_outlook, "interval", minutes=1, id="outlook_sync_cron")
    scheduler.start()
    print("[Cron] Scheduler iniciado — ratings/recurrencias cada 1h, Gmail y Outlook cada 1min")
    return scheduler
