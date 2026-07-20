"""
Mapeo categoría → fuentes de búsqueda (Fase 2, Smart Procurement).

Cada categoría define qué fuentes son PRIMARIAS (siempre se consultan) y cuáles
se omiten para reducir latencia y ruido. Las fuentes genéricas (MercadoLibre,
Google/SerpAPI) se consultan siempre porque cubren todas las categorías.

Fuentes disponibles hoy:
  Electrónica:   mouser, digikey, tme
  Retail CL:     sodimac, easy, lasierra, construmart  (construcción/ferretería)
  Eléctrico CL:  vitel, dartel, ferrelectrica, gobantes, rhona
  Genéricas:     mercadolibre, google (SerpAPI)
"""

# Fuentes genéricas: aplican a toda categoría
FUENTES_GENERICAS = {"mercadolibre", "google"}

# Fuentes específicas por grupo
ELECTRONICA = {"mouser", "digikey", "tme"}
CONSTRUCCION = {"sodimac", "easy", "lasierra", "construmart"}
ELECTRICO_CL = {"vitel", "dartel", "ferrelectrica", "gobantes", "rhona"}
# Maderas CL: tienen gate interno de keywords (si la consulta no es de madera
# devuelven [] sin salir a la red), por eso es barato incluirlas en categorías amplias.
MADERAS_CL = {"clcsa", "wmaderas", "ferramenta", "maderas_dir"}
# Carpintería/madera: barracas + retail de construcción que vende madera.
# NO incluye eléctrico (una tabla de pino no se cotiza en Vitel).
CARPINTERIA = MADERAS_CL | {"sodimac", "easy", "construmart", "lasierra"}

TODAS_ESPECIFICAS = ELECTRONICA | CONSTRUCCION | ELECTRICO_CL | MADERAS_CL

CATEGORIA_FUENTES: dict[str, set[str]] = {
    # Categorías nuevas (v2)
    "carpinteria":       CARPINTERIA,                 # madera/maderas → sin eléctrico
    "electronica":       ELECTRONICA | ELECTRICO_CL,
    "construccion":      CONSTRUCCION | MADERAS_CL,   # construcción general (sin eléctrico)
    "insumos_medicos":   set(),                       # solo genéricas + proveedores custom
    "industrial":        TODAS_ESPECIFICAS,
    "tuberias_valvulas": CONSTRUCCION,
    # Categorías legacy (v1) — mapeo conservador
    "mecanico":          CONSTRUCCION,
    "electrico":         ELECTRONICA | ELECTRICO_CL,  # eléctrico → sin retail construcción
    "hidraulico":        CONSTRUCCION | ELECTRICO_CL,
    "neumatico":         CONSTRUCCION,
    "consumible":        CONSTRUCCION | MADERAS_CL,
    "servicio":          set(),
    "otro":              TODAS_ESPECIFICAS,
}


def fuentes_para_categoria(categoria: str | None) -> set[str]:
    """Devuelve el set de fuentes específicas a consultar para una categoría.
    Si la categoría es desconocida o None, consulta todas (comportamiento v1)."""
    if not categoria:
        return TODAS_ESPECIFICAS
    return CATEGORIA_FUENTES.get(categoria.lower().strip(), TODAS_ESPECIFICAS)


async def proveedores_custom_para(user_id: str, categoria: str | None, nombre_item: str) -> list[dict]:
    """Busca proveedores custom del usuario relevantes para la categoría/ítem.

    Consulta supplier_categories (keywords + categoría) y devuelve pseudo-resultados
    con fuente='manual' para incluir en la búsqueda. Nunca lanza: devuelve [] ante error.
    """
    try:
        from app.services.supabase import get_supabase
        sb = get_supabase()

        q = sb.table("supplier_categories").select("*").eq("user_id", user_id)
        if categoria:
            q = q.eq("categoria_principal", categoria.lower().strip())
        rows = (q.execute().data) or []

        # Si no hubo match por categoría, intentar por keywords contra el nombre del ítem
        if not rows and nombre_item:
            todos = sb.table("supplier_categories").select("*").eq("user_id", user_id).execute().data or []
            palabras = {w for w in nombre_item.lower().split() if len(w) > 2}
            rows = [
                r for r in todos
                if palabras & {k.lower() for k in (r.get("keywords_asociadas") or [])}
            ]

        resultados = []
        for r in rows:
            resultados.append({
                "titulo": f"{nombre_item} — consultar a {r.get('supplier_nombre') or 'proveedor'}",
                "proveedor": r.get("supplier_nombre"),
                "precio": None,
                "moneda": "CLP",
                "url": "",
                "pais": "CL",
                "fuente": "manual",
                "tipo_proveedor": "distribuidor",
                "relevante": True,
                "es_proveedor_custom": True,
                "supplier_id": r.get("supplier_id"),
                "categoria": r.get("categoria_principal"),
            })
        return resultados
    except Exception as e:
        print(f"[categoria_mapper] Error consultando proveedores custom: {e}")
        return []
