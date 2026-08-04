"""Banco global de proveedores sugeridos por Baiyer y matching por categoría."""
import json
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


def sugeridos_para_categoria(categoria_item: str | None) -> list[dict]:
    buscadas = categorias_banco(categoria_item)
    return [
        {
            "id": f"sugerido:{p['primary_email'].lower()}",
            "nombre": p["company_name"],
            "email": p["primary_email"],
            "sitio_web": p.get("website"),
            "telefono": p.get("phone"),
            "categorias": p.get("categories", []),
            "origen": "sugerido",
            "origen_label": "Sugerido por Baiyer",
            "match_label": "Posible match",
        }
        for p in cargar_banco_sugerido()
        if buscadas.intersection(p.get("categories", []))
    ]


def buscar_sugerido(email: str) -> dict | None:
    normalizado = email.lower().strip()
    return next((p for p in cargar_banco_sugerido() if p["primary_email"].lower() == normalizado), None)
