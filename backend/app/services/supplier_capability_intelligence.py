"""
Supplier Capability Intelligence — Fase 1 (fundaciones).

Aprende, por usuario y de forma auditable, qué proveedor abastece qué
categoría. Cada aprendizaje viene de un evento inmutable en
`supplier_capability_events`; la capacidad en `supplier_capabilities` se
RECALCULA SIEMPRE desde el historial completo de eventos — nunca se
incrementa in-place — para evitar condiciones de carrera de "leer contador y
luego escribir" bajo escrituras concurrentes (ej: dos respuestas de Gmail
llegando casi al mismo tiempo).

No implementa aprendizaje compartido entre clientes: todo está filtrado por
`user_id`. Los pesos son iniciales y ajustables — no hay ML opaco, todo es
una suma determinística y explicable.
"""
from datetime import datetime, timezone
from typing import Optional
from app.services.supabase import ejecutar_maybe_single

# Pesos iniciales por tipo de evento (ver PROMPT_CLAUDE_CODE_SUPPLIER_INTELLIGENCE.md).
# Ajustables sin tocar la lógica de cálculo.
PESOS: dict[str, float] = {
    "appeared_in_search": 0.05,
    "search_result_relevant": 0.15,
    "supplier_selected_for_rfq": 0.30,
    "supplier_replied_can_supply": 0.60,
    "valid_quote_received": 0.75,
    "supplier_selected": 0.85,
    "purchase_approved": 0.90,
    "purchase_completed": 1.00,
    "search_result_rejected": -0.60,
    "supplier_replied_cannot_supply": -0.80,
    "user_corrected_category": -0.80,
    "no_satisfactory_results": 0.0,  # no afecta una capacidad puntual; es señal de la sesión de búsqueda
    # Alta manual (Fase 3) o confirmación explícita de una categoría sugerida
    # por la investigación automática — declaración directa del usuario,
    # máxima confianza posible, igual que una compra completada.
    "manual_category_assigned": 1.00,
}

UMBRAL_CONFIRMADO = 0.80
UMBRAL_RECHAZADO = 0.20


def _sb():
    from app.services.supabase import get_supabase
    return get_supabase()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clave_idempotencia(
    user_id: str, proveedor_id: str, tipo_evento: str,
    resultado_id: Optional[str], cotizacion_id: Optional[str], session_id: Optional[str],
    categoria: Optional[str],
) -> str:
    """Determina de forma estable si "el mismo evento" ya se registró. Usa el
    ancla más específica disponible (resultado > cotización > sesión) para que
    reintentos (ej: cron reprocesando un mensaje) no dupliquen evidencia."""
    ancla = resultado_id or cotizacion_id or session_id or "sin-ancla"
    return f"{tipo_evento}:{user_id}:{proveedor_id}:{ancla}:{categoria or ''}"


def registrar_evento(
    user_id: str,
    proveedor_id: str,
    tipo_evento: str,
    *,
    resultado_id: Optional[str] = None,
    cotizacion_id: Optional[str] = None,
    session_id: Optional[str] = None,
    categoria_predicha: Optional[str] = None,
    categoria_confirmada: Optional[str] = None,
    concepto_normalizado: str = "",
    metadata: Optional[dict] = None,
    estricto: bool = False,
) -> Optional[dict]:
    """Registra un evento de evidencia y recalcula la capacidad afectada.
    Idempotente: si el mismo evento (misma ancla + tipo + categoría) ya se
    registró, no duplica ni vuelve a sumar su peso — devuelve la capacidad
    actual sin cambios."""
    if tipo_evento not in PESOS:
        raise ValueError(f"tipo_evento inválido: {tipo_evento}")

    categoria = categoria_confirmada or categoria_predicha
    sb = _sb()
    clave = _clave_idempotencia(
        user_id, proveedor_id, tipo_evento, resultado_id, cotizacion_id, session_id, categoria,
    )

    ya_existe = sb.table("supplier_capability_events").select("id").eq("clave_idempotencia", clave).execute().data
    if ya_existe:
        if categoria:
            return recalcular_capacidad(user_id, proveedor_id, categoria, concepto_normalizado)
        return None

    try:
        sb.table("supplier_capability_events").insert({
            "user_id": user_id,
            "proveedor_id": proveedor_id,
            "resultado_id": resultado_id,
            "cotizacion_id": cotizacion_id,
            "session_id": session_id,
            "categoria_predicha": categoria_predicha,
            "categoria_confirmada": categoria_confirmada,
            "concepto_normalizado": concepto_normalizado or "",
            "tipo_evento": tipo_evento,
            "peso": PESOS[tipo_evento],
            "clave_idempotencia": clave,
            "metadata": metadata or {},
        }).execute()
    except Exception as e:
        # Violación de unicidad por una carrera entre dos requests simultáneos:
        # alguien más ya insertó el mismo evento justo antes — no es un error real.
        if "duplicate key" in str(e).lower() or "23505" in str(e):
            pass
        else:
            print(f"[SupplierCapability] Error registrando evento: {e}")
            if estricto:
                raise
            return None

    if not categoria:
        return None
    return recalcular_capacidad(user_id, proveedor_id, categoria, concepto_normalizado)


def registrar_categorias_importadas(
    user_id: str, asignaciones: set[tuple[str, str]], *, tamano_lote: int = 200,
) -> int:
    """Registra categorías explícitas de una importación en lotes.

    Evita ejecutar 4-5 requests a PostgREST por cada proveedor/categoría. Los
    eventos siguen siendo auditables e idempotentes y la capacidad derivada
    queda con la misma confianza máxima de ``manual_category_assigned``.
    """
    if not asignaciones:
        return 0
    sb = _sb()
    ahora = _now()
    eventos = []
    capacidades = []
    for proveedor_id, categoria in sorted(asignaciones):
        clave = _clave_idempotencia(
            user_id, proveedor_id, "manual_category_assigned",
            None, None, None, categoria,
        )
        eventos.append({
            "user_id": user_id,
            "proveedor_id": proveedor_id,
            "categoria_confirmada": categoria,
            "concepto_normalizado": "",
            "tipo_evento": "manual_category_assigned",
            "peso": PESOS["manual_category_assigned"],
            "clave_idempotencia": clave,
            "metadata": {"origen": "excel"},
        })
        capacidades.append({
            "user_id": user_id,
            "proveedor_id": proveedor_id,
            "categoria": categoria,
            "concepto": "",
            "confianza": 1.0,
            "evidencia_positiva": 1,
            "evidencia_negativa": 0,
            "cotizaciones_validas": 0,
            "compras": 0,
            "estado": "confirmed",
            "ultima_evidencia_at": ahora,
            "updated_at": ahora,
        })

    for inicio in range(0, len(eventos), tamano_lote):
        sb.table("supplier_capability_events").upsert(
            eventos[inicio:inicio + tamano_lote], on_conflict="clave_idempotencia",
        ).execute()
    for inicio in range(0, len(capacidades), tamano_lote):
        sb.table("supplier_capabilities").upsert(
            capacidades[inicio:inicio + tamano_lote],
            on_conflict="user_id,proveedor_id,categoria,concepto",
        ).execute()
    return len(asignaciones)


def recalcular_capacidad(
    user_id: str, proveedor_id: str, categoria: str, concepto: str = "",
) -> dict:
    """Recalcula supplier_capabilities desde CERO a partir de todos los eventos
    (nunca incrementa un contador existente). Determinístico y auditable."""
    sb = _sb()
    concepto = concepto or ""

    eventos = (
        sb.table("supplier_capability_events")
        .select("tipo_evento, peso, categoria_confirmada, categoria_predicha, created_at")
        .eq("user_id", user_id).eq("proveedor_id", proveedor_id)
        .eq("concepto_normalizado", concepto)
        .execute().data or []
    )
    # Un evento cuenta para esta categoría si la confirma explícitamente, o si
    # no hay confirmación y la predicha coincide.
    relevantes = [
        e for e in eventos
        if (e.get("categoria_confirmada") or e.get("categoria_predicha")) == categoria
    ]

    suma = sum(e["peso"] for e in relevantes)
    confianza = max(0.0, min(1.0, suma))
    evidencia_positiva = sum(1 for e in relevantes if e["peso"] > 0)
    evidencia_negativa = sum(1 for e in relevantes if e["peso"] < 0)
    cotizaciones_validas = sum(1 for e in relevantes if e["tipo_evento"] == "valid_quote_received")
    compras = sum(1 for e in relevantes if e["tipo_evento"] == "purchase_completed")
    ultima_evidencia_at = max((e["created_at"] for e in relevantes), default=None)

    if confianza >= UMBRAL_CONFIRMADO:
        estado = "confirmed"
    elif confianza <= UMBRAL_RECHAZADO and evidencia_negativa > 0:
        estado = "rejected"
    else:
        estado = "probable"

    row = {
        "user_id": user_id,
        "proveedor_id": proveedor_id,
        "categoria": categoria,
        "concepto": concepto,
        "confianza": round(confianza, 4),
        "evidencia_positiva": evidencia_positiva,
        "evidencia_negativa": evidencia_negativa,
        "cotizaciones_validas": cotizaciones_validas,
        "compras": compras,
        "estado": estado,
        "ultima_evidencia_at": ultima_evidencia_at,
        "updated_at": _now(),
    }
    sb.table("supplier_capabilities").upsert(
        row, on_conflict="user_id,proveedor_id,categoria,concepto",
    ).execute()
    return row


def _explicar(cap: dict) -> str:
    partes = []
    if cap.get("compras"):
        partes.append(f"{cap['compras']} compra(s) completada(s)")
    if cap.get("cotizaciones_validas"):
        partes.append(f"{cap['cotizaciones_validas']} cotización(es) válida(s)")
    if not partes and cap.get("evidencia_positiva"):
        partes.append(f"{cap['evidencia_positiva']} señal(es) positiva(s) de búsqueda/selección")
    if not partes:
        return "Sin evidencia suficiente todavía."
    return "Basado en " + ", ".join(partes) + "."


def rankear_proveedores(user_id: str, categoria: str, limit: int = 10) -> list[dict]:
    """Proveedores conocidos del usuario para una categoría, ordenados por
    confianza de capacidad. No incluye proveedores bloqueados. Explicable:
    cada resultado trae por qué se considera capaz."""
    sb = _sb()
    caps = (
        sb.table("supplier_capabilities").select("*")
        .eq("user_id", user_id).eq("categoria", categoria)
        .neq("estado", "rejected")
        .order("confianza", desc=True).limit(limit)
        .execute().data or []
    )
    if not caps:
        return []

    proveedor_ids = [c["proveedor_id"] for c in caps]
    proveedores = {
        p["id"]: p for p in (
            sb.table("proveedores").select("id, nombre, email, score, bloqueado")
            .in_("id", proveedor_ids).execute().data or []
        )
    }

    resultado = []
    for c in caps:
        p = proveedores.get(c["proveedor_id"])
        if not p or p.get("bloqueado"):
            continue
        resultado.append({
            "proveedor_id": c["proveedor_id"],
            "proveedor_nombre": p.get("nombre"),
            "proveedor_email": p.get("email"),
            "score_general": p.get("score"),
            "categoria": categoria,
            "confianza": c["confianza"],
            "estado": c["estado"],
            "explicacion": _explicar(c),
        })
    return resultado


def listar_capacidades(user_id: str, proveedor_id: str) -> list[dict]:
    """Categorías/capacidades conocidas de un proveedor puntual, para su ficha."""
    sb = _sb()
    return (
        sb.table("supplier_capabilities").select("*")
        .eq("user_id", user_id).eq("proveedor_id", proveedor_id)
        .order("confianza", desc=True).execute().data or []
    )


def rechazar_capacidad(user_id: str, proveedor_id: str, categoria: str, concepto: str = "") -> None:
    """El usuario quita explícitamente una categoría de un proveedor — anula
    la capacidad directamente (no espera a que se acumulen eventos negativos:
    es una corrección manual, señal fuerte por definición)."""
    sb = _sb()
    sb.table("supplier_capabilities").update({
        "estado": "rejected", "confianza": 0.0, "updated_at": _now(),
    }).eq("user_id", user_id).eq("proveedor_id", proveedor_id).eq("categoria", categoria).eq("concepto", concepto or "").execute()


def registrar_evento_para_resultado(
    user_id: str, resultado_id: str, tipo_evento: str, metadata: Optional[dict] = None,
) -> Optional[dict]:
    """Resuelve un resultado hacia el proveedor privado que lo originó y
    registra evidencia. Soporta tanto conversación legacy 1:1 como RFQ batch
    multiítem. Si el resultado externo aún no está asociado al directorio, no
    inventa identidad y retorna None."""
    sb = _sb()
    resultado = ejecutar_maybe_single(sb.table("resultados").select("id,cotizacion_id").eq("id", resultado_id).maybe_single()).data
    if not resultado:
        return None
    cot = ejecutar_maybe_single(sb.table("cotizaciones").select("categoria").eq("id", resultado["cotizacion_id"]).maybe_single()).data or {}
    proveedor_id = None
    try:
        item = ejecutar_maybe_single(sb.table("rfq_batch_items").select("rfq_batch_id").eq("resultado_id", resultado_id).maybe_single()).data
        if item:
            batch = ejecutar_maybe_single(sb.table("rfq_batches").select("proveedor_id,user_id").eq("id", item["rfq_batch_id"]).eq("user_id", user_id).maybe_single()).data
            proveedor_id = (batch or {}).get("proveedor_id")
    except Exception:
        pass
    if not proveedor_id:
        try:
            conv = sb.table("gmail_conversations").select("proveedor_id").eq("resultado_id", resultado_id).eq("user_id", user_id).order("last_message_at", desc=True).limit(1).execute().data or []
            proveedor_id = (conv[0] if conv else {}).get("proveedor_id")
        except Exception:
            pass
    if not proveedor_id or not cot.get("categoria"):
        return None
    return registrar_evento(
        user_id, proveedor_id, tipo_evento,
        resultado_id=resultado_id, cotizacion_id=resultado["cotizacion_id"],
        categoria_confirmada=cot["categoria"], metadata=metadata,
    )
