"""
Perfil de procurement por usuario — Fase 1 de Supplier Capability Intelligence.

Se genera al completar el onboarding (prior inicial, confianza media, origen
"onboarding"/"industry_prior") y evoluciona con uso real. Nunca se sobreescribe
sin dejar rastro: cada categoría tiene su propia fila con confianza, orígenes
acumulados y si el usuario la confirmó explícitamente.

Precedencia (nunca se invierte acá — este perfil es solo un prior, no un filtro):
  intención explícita del ítem > contexto del proyecto > historial real
  > este perfil > conocimiento global (todavía no implementado).
"""
from datetime import datetime, timezone
from typing import Optional
from app.services.supabase import ejecutar_maybe_single

CONFIANZA_INICIAL_ONBOARDING = 0.6
CONFIANZA_SENAL_USO = 0.05  # cuánto sube una categoría al verla en una búsqueda real
CONFIANZA_CONFIRMACION_USUARIO = 1.0


def _sb():
    from app.services.supabase import get_supabase
    return get_supabase()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def crear_o_actualizar_perfil(
    user_id: str,
    empresa: Optional[str] = None,
    dominio: Optional[str] = None,
    industria: Optional[str] = None,
    pais: Optional[str] = None,
    categorias_probables: Optional[list[str]] = None,
    descripcion_actividad: Optional[str] = None,
    origen: str = "onboarding",
) -> dict:
    """Crea el perfil si no existe, o actualiza los datos de empresa si cambiaron
    (ej: el usuario corrigió el nombre en el onboarding). Las categorías se
    fusionan con las que ya había — nunca se pisan confianzas ya ganadas por uso."""
    sb = _sb()
    existente = ejecutar_maybe_single(sb.table("procurement_profiles").select("*").eq("user_id", user_id).maybe_single()).data

    datos = {
        "user_id": user_id,
        "empresa": empresa,
        "dominio": dominio,
        "industria": industria,
        "pais": pais,
        "descripcion_actividad": descripcion_actividad,
        "updated_at": _now(),
    }
    if existente:
        sb.table("procurement_profiles").update(datos).eq("id", existente["id"]).execute()
        profile_id = existente["id"]
    else:
        ins = sb.table("procurement_profiles").insert(datos).execute()
        profile_id = ins.data[0]["id"]

    for categoria in (categorias_probables or []):
        _upsert_categoria(sb, profile_id, categoria.lower().strip(), origen, CONFIANZA_INICIAL_ONBOARDING)

    return listar_perfil(user_id)


def _upsert_categoria(sb, profile_id: str, categoria: str, origen: str, confianza_si_nueva: float) -> None:
    if not categoria:
        return
    existente = ejecutar_maybe_single(
        sb.table("procurement_profile_categories").select("*")
        .eq("profile_id", profile_id).eq("categoria", categoria).maybe_single()
    ).data
    if existente:
        origenes = set(existente.get("origenes") or [])
        if origen in origenes:
            return  # ya registrada por esta misma fuente, no duplica evidencia
        origenes.add(origen)
        sb.table("procurement_profile_categories").update({
            "origenes": sorted(origenes),
            "updated_at": _now(),
        }).eq("id", existente["id"]).execute()
    else:
        sb.table("procurement_profile_categories").insert({
            "profile_id": profile_id,
            "categoria": categoria,
            "confianza": confianza_si_nueva,
            "origenes": [origen],
            "confirmado_por_usuario": False,
        }).execute()


def listar_perfil(user_id: str) -> Optional[dict]:
    sb = _sb()
    perfil = ejecutar_maybe_single(sb.table("procurement_profiles").select("*").eq("user_id", user_id).maybe_single()).data
    if not perfil:
        return None
    categorias = (
        sb.table("procurement_profile_categories").select("*")
        .eq("profile_id", perfil["id"]).order("confianza", desc=True).execute().data or []
    )
    return {**perfil, "categorias": categorias}


def confirmar_categoria(user_id: str, categoria_row_id: str, confirmar: bool = True) -> dict:
    """El usuario confirma (o desconfirma) una categoría sugerida. Confirmar es
    una señal fuerte y explícita — sube la confianza al máximo."""
    sb = _sb()
    fila = ejecutar_maybe_single(sb.table("procurement_profile_categories").select("*, procurement_profiles(user_id)").eq("id", categoria_row_id).maybe_single()).data
    if not fila or not fila.get("procurement_profiles") or fila["procurement_profiles"]["user_id"] != user_id:
        raise ValueError("Categoría no encontrada para este usuario")

    origenes = set(fila.get("origenes") or [])
    cambios: dict = {"confirmado_por_usuario": confirmar, "updated_at": _now()}
    if confirmar:
        origenes.add("user_confirmed")
        cambios["origenes"] = sorted(origenes)
        cambios["confianza"] = CONFIANZA_CONFIRMACION_USUARIO
    sb.table("procurement_profile_categories").update(cambios).eq("id", categoria_row_id).execute()
    return sb.table("procurement_profile_categories").select("*").eq("id", categoria_row_id).single().execute().data


def agregar_categoria_manual(user_id: str, categoria: str) -> dict:
    sb = _sb()
    perfil = ejecutar_maybe_single(sb.table("procurement_profiles").select("id").eq("user_id", user_id).maybe_single()).data
    if not perfil:
        perfil_completo = crear_o_actualizar_perfil(user_id)
        profile_id = perfil_completo["id"]
    else:
        profile_id = perfil["id"]

    categoria = categoria.lower().strip()
    existente = ejecutar_maybe_single(
        sb.table("procurement_profile_categories").select("*")
        .eq("profile_id", profile_id).eq("categoria", categoria).maybe_single()
    ).data
    if existente:
        return confirmar_categoria(user_id, existente["id"], confirmar=True)

    ins = sb.table("procurement_profile_categories").insert({
        "profile_id": profile_id,
        "categoria": categoria,
        "confianza": CONFIANZA_CONFIRMACION_USUARIO,
        "origenes": ["user_confirmed"],
        "confirmado_por_usuario": True,
    }).execute()
    return ins.data[0]


def eliminar_categoria(user_id: str, categoria_row_id: str) -> None:
    sb = _sb()
    fila = ejecutar_maybe_single(sb.table("procurement_profile_categories").select("*, procurement_profiles(user_id)").eq("id", categoria_row_id).maybe_single()).data
    if not fila or not fila.get("procurement_profiles") or fila["procurement_profiles"]["user_id"] != user_id:
        raise ValueError("Categoría no encontrada para este usuario")
    sb.table("procurement_profile_categories").delete().eq("id", categoria_row_id).execute()


def registrar_senal_uso(user_id: str, categoria: str, origen: str = "search_history") -> None:
    """Señal débil de uso real (ej: el usuario buscó en esta categoría). Sube
    la confianza un poco sin necesitar confirmación explícita — así el
    historial real va superando gradualmente el prior de onboarding, sin
    caer en el ciclo de solo reforzar lo ya inferido: si la categoría no
    existía en el perfil, esto la CREA (descubre necesidades nuevas)."""
    if not categoria:
        return
    sb = _sb()
    perfil = ejecutar_maybe_single(sb.table("procurement_profiles").select("id").eq("user_id", user_id).maybe_single()).data
    profile_id = perfil["id"] if perfil else crear_o_actualizar_perfil(user_id)["id"]

    categoria = categoria.lower().strip()
    existente = ejecutar_maybe_single(
        sb.table("procurement_profile_categories").select("*")
        .eq("profile_id", profile_id).eq("categoria", categoria).maybe_single()
    ).data
    if existente:
        if existente.get("confirmado_por_usuario"):
            return  # ya está en el techo, no hace falta reforzar
        origenes = set(existente.get("origenes") or [])
        origenes.add(origen)
        nueva_confianza = min(1.0, float(existente["confianza"]) + CONFIANZA_SENAL_USO)
        sb.table("procurement_profile_categories").update({
            "confianza": round(nueva_confianza, 4),
            "origenes": sorted(origenes),
            "evidencia_positiva": (existente.get("evidencia_positiva") or 0) + 1,
            "ultima_evidencia_at": _now(),
            "updated_at": _now(),
        }).eq("id", existente["id"]).execute()
    else:
        sb.table("procurement_profile_categories").insert({
            "profile_id": profile_id,
            "categoria": categoria,
            "confianza": CONFIANZA_SENAL_USO,
            "origenes": [origen],
            "confirmado_por_usuario": False,
            "evidencia_positiva": 1,
            "ultima_evidencia_at": _now(),
        }).execute()
