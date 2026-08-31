"""Chat con tus datos — Claria como asistente de compras."""
import asyncio
import json
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.services.auth_context import AuthContext, get_auth_context

router = APIRouter(prefix="/api/chat", tags=["chat"])


class MensajeRequest(BaseModel):
    mensaje: str
    conversacion_id: Optional[str] = None


def _cargar_contexto_usuario(user_id: str) -> dict:
    """Carga stats agregadas del usuario desde Supabase."""
    from app.services.supabase import get_supabase
    from app.services.organizacion import ids_organizacion
    sb = get_supabase()
    ids = ids_organizacion(user_id)

    ctx: dict = {}
    try:
        # Gasto total en OCs
        ocs = sb.table("ordenes_compra").select("monto_total, estado, proveedor_nombre, created_at").in_("user_id", ids).order("created_at", desc=True).limit(50).execute()
        monto_total = sum(float(o.get("monto_total") or 0) for o in (ocs.data or []))
        ctx["total_ocs"] = len(ocs.data or [])
        ctx["gasto_total_clp"] = round(monto_total)

        # Top proveedores
        prov_count: dict[str, float] = {}
        for oc in (ocs.data or []):
            prov = oc.get("proveedor_nombre") or "Sin nombre"
            prov_count[prov] = prov_count.get(prov, 0) + float(oc.get("monto_total") or 0)
        ctx["top_proveedores"] = sorted(
            [{"nombre": k, "gasto": round(v)} for k, v in prov_count.items()],
            key=lambda x: x["gasto"], reverse=True
        )[:5]

        # Cotizaciones recientes
        cots = sb.table("cotizaciones").select("nombre_identificado, descripcion, created_at").in_("user_id", ids).order("created_at", desc=True).limit(50).execute()
        ctx["total_cotizaciones"] = len(cots.data or [])
        ctx["items_recientes"] = [c.get("nombre_identificado") or c.get("descripcion") for c in (cots.data or [])[:10]]

        # Proveedores con score
        suppliers = sb.table("proveedores").select("nombre, score, categoria_score").in_("user_id", ids).order("score", desc=True).limit(10).execute()
        ctx["proveedores_red"] = [{"nombre": p["nombre"], "score": p.get("score"), "categoria": p.get("categoria_score")} for p in (suppliers.data or [])]

        # Facturas pendientes
        facturas = sb.table("facturas").select("monto, estado, proveedor_nombre").in_("user_id", ids).eq("estado", "pendiente").execute()
        ctx["facturas_pendientes"] = len(facturas.data or [])
        ctx["monto_facturas_pendientes"] = round(sum(float(f.get("monto") or 0) for f in (facturas.data or [])))

    except Exception as e:
        print(f"[Chat] Error cargando contexto: {e}")

    return ctx


# Acá vivía `_ejecutar_sql_seguro()`, que sanitizaba con `services/sql_safety.py`
# el SQL que escribía Gemini y lo ejecutaba vía la RPC `ejecutar_query_usuario`.
# Se borró junto con el sanitizador el 2026-08-31. Tres motivos:
#
# 1. Estaba muerta desde el commit inicial: nadie la llamó nunca (`git log -S`),
#    y la RPC que invocaba no existe en ninguna migración.
# 2. El sanitizador no aislaba organizaciones. Inyectaba el filtro de tenant sólo
#    si la cadena "user_id" NO aparecía en el SQL, así que `SELECT user_id, ...`
#    o `WHERE user_id IS NOT NULL` salían sin filtro y devolvían datos de todas
#    las empresas. Un subquery (`FROM (SELECT ...)`) además esquivaba la
#    allowlist de tablas, porque el regex `FROM\s+(\w+)` no matchea `FROM (`.
# 3. Conectarla era un renglón. Con el empleado digital encima —que encadena
#    llamadas sin supervisión y come correo de proveedores como input— dejar eso
#    a mano era una trampa, no una feature pendiente.
#
# Si alguna vez se quiere "chat con tus datos" de verdad, la respuesta NO es
# arreglar el regex: es `services/semantic_query.py`, que ya usa el MCP
# (`query_baiyer_data`). Es allowlist de entidades/campos/operadores y filtra por
# `in_(ownership, actor.organization_user_ids)` en el query builder, sin construir
# SQL como texto. Un solo límite de tenant para web, MCP y agente.


@router.post("/mensaje")
async def enviar_mensaje(req: MensajeRequest, auth_ctx: AuthContext = Depends(get_auth_context)):
    from app.config import settings
    from app.services.supabase import get_supabase
    import google.generativeai as genai

    if not settings.gemini_api_key:
        raise HTTPException(status_code=503, detail="GEMINI_API_KEY no configurada")

    sb = get_supabase()

    # ── Conversación ──────────────────────────────────────────────────────────
    conv_id = req.conversacion_id
    if not conv_id:
        # Crear nueva conversación
        conv = sb.table("chat_conversaciones").insert({
            "user_id": auth_ctx.actor_user_id,
            "titulo": req.mensaje[:60],
        }).execute()
        conv_id = conv.data[0]["id"] if conv.data else None

    # ── Historial de mensajes ─────────────────────────────────────────────────
    historial = []
    if conv_id:
        msgs = sb.table("chat_mensajes").select("rol, contenido").eq(
            "conversacion_id", conv_id
        ).order("created_at").limit(10).execute()
        historial = msgs.data or []

    # ── Contexto del usuario ──────────────────────────────────────────────────
    ctx = _cargar_contexto_usuario(auth_ctx.actor_user_id)

    # ── Prompt ────────────────────────────────────────────────────────────────
    system_prompt = f"""Eres Claria, asistente de compras e inteligencia de proveedores.
Ayudas al usuario a analizar sus compras, proveedores y cotizaciones en lenguaje natural.

DATOS ACTUALES DEL USUARIO:
- Total OCs emitidas: {ctx.get('total_ocs', 0)}
- Gasto total histórico: ${ctx.get('gasto_total_clp', 0):,} CLP
- Total cotizaciones: {ctx.get('total_cotizaciones', 0)}
- Facturas pendientes: {ctx.get('facturas_pendientes', 0)} (${ctx.get('monto_facturas_pendientes', 0):,} CLP)
- Top proveedores por gasto: {json.dumps(ctx.get('top_proveedores', []), ensure_ascii=False)}
- Red de proveedores: {json.dumps(ctx.get('proveedores_red', []), ensure_ascii=False)}
- Ítems cotizados recientemente: {', '.join(str(x) for x in ctx.get('items_recientes', []) if x)}

Responde SIEMPRE en JSON válido sin markdown:
{{
  "respuesta": "texto en español amigable y directo",
  "formato_visual": "texto" | "tabla" | "grafico_barras" | "cards",
  "datos_tabla": [{{"columna": "valor"}}] (solo si formato_visual es tabla),
  "datos_grafico": [{{"label": "...", "valor": 0}}] (solo si es grafico_barras),
  "datos_cards": [{{"titulo": "...", "valor": "...", "color": "#hex"}}] (solo si es cards),
  "links": [{{"texto": "...", "href": "/ruta"}}]
}}

Si no tienes suficientes datos para responder precisamente, dilo honestamente."""

    # Construir historial para Gemini
    gemini_history = []
    for msg in historial:
        role = "user" if msg["rol"] == "user" else "model"
        gemini_history.append({"role": role, "parts": [msg["contenido"]]})

    # ── Llamar a Gemini ───────────────────────────────────────────────────────
    genai.configure(api_key=settings.gemini_api_key)
    model = genai.GenerativeModel("gemini-2.5-flash", system_instruction=system_prompt)

    chat_session = model.start_chat(history=gemini_history)

    try:
        response = await asyncio.wait_for(
            chat_session.send_message_async(req.mensaje),
            timeout=30.0,
        )
        text = response.text.strip()
        if "```" in text:
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:].strip()
        resultado = json.loads(text)
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="Gemini tardó demasiado")
    except json.JSONDecodeError:
        # Respuesta de texto simple
        resultado = {"respuesta": response.text.strip(), "formato_visual": "texto"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    # ── Guardar mensajes ──────────────────────────────────────────────────────
    if conv_id:
        sb.table("chat_mensajes").insert([
            {"conversacion_id": conv_id, "rol": "user", "contenido": req.mensaje},
            {
                "conversacion_id": conv_id,
                "rol": "assistant",
                "contenido": resultado.get("respuesta", ""),
                "datos_visuales": {k: v for k, v in resultado.items() if k != "respuesta"},
            },
        ]).execute()

        # Actualizar updated_at conversación
        sb.table("chat_conversaciones").update({"updated_at": "now()", "titulo": req.mensaje[:60] if not req.conversacion_id else None}).eq("id", conv_id).execute()

    return {**resultado, "conversacion_id": conv_id}


@router.get("/conversaciones")
async def listar_conversaciones(ctx: AuthContext = Depends(get_auth_context)):
    from app.services.supabase import get_supabase
    sb = get_supabase()
    res = sb.table("chat_conversaciones").select("*").eq("user_id", ctx.actor_user_id).order("updated_at", desc=True).limit(30).execute()
    return res.data or []


@router.delete("/conversaciones/{conv_id}")
async def eliminar_conversacion(conv_id: str, ctx: AuthContext = Depends(get_auth_context)):
    from app.services.supabase import get_supabase
    sb = get_supabase()
    sb.table("chat_conversaciones").delete().eq("id", conv_id).eq("user_id", ctx.actor_user_id).execute()
    return {"ok": True}


@router.get("/conversaciones/{conv_id}/mensajes")
async def mensajes_conversacion(conv_id: str, ctx: AuthContext = Depends(get_auth_context)):
    from app.services.supabase import ejecutar_maybe_single, get_supabase
    sb = get_supabase()
    # La conversación tiene que ser del actor. Antes esto devolvía los mensajes
    # de cualquier `conv_id` sin ningún filtro de propietario: con un id ajeno
    # se leía el chat de otra organización.
    duena = ejecutar_maybe_single(
        sb.table("chat_conversaciones").select("id").eq("id", conv_id)
        .eq("user_id", ctx.actor_user_id).maybe_single()
    )
    if not duena.data:
        raise HTTPException(status_code=404, detail="Conversación no encontrada")
    res = sb.table("chat_mensajes").select("*").eq("conversacion_id", conv_id).order("created_at").execute()
    return res.data or []
