"""Banco global de proveedores sugeridos por Baiyer y matching por categoría."""
import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path


ALIAS_CATEGORIAS: dict[str, set[str]] = {
    "electronica": {"electronico"},
    "electrico": {"electrico"},
    "construccion": {"construccion"},
    "carpinteria": {"madera"},
    "mecanico": {"mecanico", "ferreteria"},
    "industrial": {"mecanico", "ferreteria"},
    "hidraulico": {"mecanico"},
    "neumatico": {"mecanico", "electronico"},
    "tuberias_valvulas": {"mecanico", "construccion"},
    "consumible": {"retail", "ferreteria"},
}


@lru_cache(maxsize=1)
def cargar_banco_sugerido() -> list[dict]:
    ruta = Path(__file__).resolve().parent.parent / "data" / "proveedores_sugeridos.json"
    with ruta.open(encoding="utf-8") as archivo:
        return json.load(archivo)


def categorias_banco(categoria_item: str | None) -> set[str]:
    categoria = (categoria_item or "otro").lower().strip()
    return ALIAS_CATEGORIAS.get(categoria, {categoria})


PALABRAS_VACIAS = {
    "a", "al", "con", "de", "del", "e", "el", "en", "la", "las", "los",
    "o", "para", "por", "sin", "tipo", "un", "una", "y",
    # Describen el rubro pero no distinguen la capacidad concreta del proveedor.
    "accesorio", "accesorios", "construccion", "electrico", "electricos",
    "electronico", "electronicos", "equipo", "equipos", "ferreteria",
    "industrial", "industriales", "material", "materiales", "mecanico",
    "mecanicos", "producto", "productos", "retail", "sistema", "sistemas",
}


def _tokens(texto: str | None) -> set[str]:
    """Normaliza acentos y ruido para comparar el ítem con el catálogo."""
    normalizado = unicodedata.normalize("NFKD", texto or "")
    normalizado = "".join(c for c in normalizado if not unicodedata.combining(c)).lower()
    tokens = {
        token for token in re.findall(r"[a-z0-9]+", normalizado)
        if len(token) >= 3 and token not in PALABRAS_VACIAS
    }
    # Singularización conservadora suficiente para el vocabulario del catálogo
    # (rodamiento/rodamientos, cable/cables, batería/baterías).
    return {
        token[:-2] if len(token) > 5 and token.endswith("es")
        else token[:-1] if len(token) > 4 and token.endswith("s")
        else token
        for token in tokens
    }


def _puntuar_contexto(proveedor: dict, consulta: str | None) -> tuple[int, str | None]:
    consulta_tokens = _tokens(consulta)
    if not consulta_tokens:
        return 0, None

    mejores_productos = []
    mejor_producto_score = 0
    mejores_producto_tokens: set[str] = set()
    for producto in proveedor.get("products", []):
        coincidencias = consulta_tokens.intersection(_tokens(producto))
        if len(coincidencias) > mejor_producto_score:
            mejor_producto_score = len(coincidencias)
            mejores_producto_tokens = coincidencias
            mejores_productos = [producto]
        elif coincidencias and len(coincidencias) == mejor_producto_score:
            mejores_productos.append(producto)

    mejores_familias = []
    mejor_familia_score = 0
    mejores_familia_tokens: set[str] = set()
    for familia in proveedor.get("product_categories", []):
        coincidencias = consulta_tokens.intersection(_tokens(familia))
        if len(coincidencias) > mejor_familia_score:
            mejor_familia_score = len(coincidencias)
            mejores_familia_tokens = coincidencias
            mejores_familias = [familia]
        elif coincidencias and len(coincidencias) == mejor_familia_score:
            mejores_familias.append(familia)

    # Un producto concreto pesa más que una familia comercial amplia.
    # No premia dos veces la misma palabra si aparece tanto en la familia como
    # en el producto (por ejemplo, "tablero" en ambas descripciones).
    score = mejor_producto_score * 5 + len(mejores_familia_tokens - mejores_producto_tokens) * 3
    if mejor_producto_score:
        return score, f"Match por producto: {mejores_productos[0]}"
    if mejor_familia_score:
        return score, f"Match por especialidad: {mejores_familias[0]}"
    return 0, None


def sugeridos_para_categoria(categoria_item: str | None, consulta: str | None = None) -> list[dict]:
    buscadas = categorias_banco(categoria_item)
    candidatos = []
    for posicion, p in enumerate(cargar_banco_sugerido()):
        if not p.get("is_suggested", True) or not buscadas.intersection(p.get("categories", [])):
            continue
        score, motivo = _puntuar_contexto(p, consulta)
        candidatos.append((score, posicion, {
            "id": f"sugerido:{p['primary_email'].lower()}",
            "nombre": p["company_name"],
            "email": p["primary_email"],
            "sitio_web": p.get("website"),
            "telefono": p.get("phone"),
            "categorias": p.get("categories", []),
            "categorias_producto": p.get("product_categories", []),
            "productos": p.get("products", []),
            "origen": "sugerido",
            "origen_label": "Sugerido por Baiyer",
            "match_label": motivo or "Match por categoría",
            "match_score": score,
        }))

    # Conserva el orden histórico cuando no hay contexto; con contexto pone
    # primero a los especialistas y usa el orden del banco como desempate.
    candidatos.sort(key=lambda candidato: (-candidato[0], candidato[1]))
    return [proveedor for _, _, proveedor in candidatos]


def buscar_sugerido(email: str) -> dict | None:
    normalizado = email.lower().strip()
    return next((p for p in cargar_banco_sugerido() if p["primary_email"].lower() == normalizado), None)
