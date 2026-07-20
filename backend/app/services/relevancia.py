"""
Matching de relevancia: descartar resultados "basura" que no son el producto
buscado, sino un derivado o accesorio.

Ej: buscando "madera cepillada" NO queremos "barniz de madera", "cepillo de
dientes de bambú" ni "portarretrato de madera". Buscando "taladro" no queremos
"broca para taladro" ni "maletín para taladro".

Estrategia (rápida, sin llamadas a LLM en el hot-path del stream):
  1. Negativas por categoría: palabras que delatan un producto derivado
     (barniz/esmalte para carpintería, etc.). Si el título las contiene y el
     ítem NO, se descarta.
  2. Negativas genéricas: souvenirs/juguetes/accesorios irrelevantes en B2B.
  3. Patrón de accesorio: "<algo> para <ítem>" (broca para taladro).

Devuelve True si el resultado es relevante (se muestra), False si es basura.
"""
import re
import unicodedata

_STOPWORDS = {
    "de", "para", "con", "del", "los", "las", "por", "una", "uno", "the",
    "and", "for", "kit", "set", "el", "la", "en", "y", "a", "su", "al",
}

# Palabras que casi siempre indican un producto DERIVADO, no el material/pieza.
_NEGATIVAS_POR_CATEGORIA: dict[str, set[str]] = {
    # Carpintería / madera: excluir terminaciones y objetos "de madera"
    "carpinteria": {
        "barniz", "esmalte", "pintura", "tinte", "laca", "sellador", "cera",
        "pegamento", "cola", "adhesivo", "removedor", "diluyente", "aguarras",
        "cepillo de dientes", "portarretrato", "portaretrato", "marco", "cuadro",
        "juguete", "miniatura", "adorno", "decorativo", "souvenir", "llavero",
        "bandeja", "posavaso", "individual", "tabla de picar", "cuchara",
    },
    "construccion": {
        "juguete", "miniatura", "maqueta", "decorativo", "souvenir", "llavero",
        "disfraz", "sticker", "adhesivo decorativo",
    },
    "electrico": {
        "juguete", "miniatura", "disfraz", "decorativo", "souvenir",
    },
    "electronica": {
        "juguete", "disfraz", "funda", "carcasa decorativa", "sticker",
    },
}

# Basura transversal a cualquier categoría (souvenirs / retail no-B2B).
_NEGATIVAS_GENERICAS = {
    "cepillo de dientes", "llavero", "disfraz", "sticker", "calcomania",
    "peluche", "figura coleccionable", "funda para celular", "case celular",
    "para muñeca", "para muñeco", "para gato", "para perro", "mascota",
}


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFD", (s or "").lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _stem(w: str) -> str:
    if len(w) > 4 and w.endswith("es"):
        return w[:-2]
    if len(w) > 3 and w.endswith("s"):
        return w[:-1]
    return w


def es_relevante(titulo: str, nombre_item: str, categoria: str | None = None) -> bool:
    """True si `titulo` corresponde razonablemente al `nombre_item` buscado."""
    if not titulo or not nombre_item:
        return True

    t = _norm(titulo)
    item = _norm(nombre_item)
    if not t:
        return True

    # 1) Negativas de la categoría + genéricas (frases primero, por si multi-palabra)
    negativas = set(_NEGATIVAS_GENERICAS)
    if categoria:
        negativas |= _NEGATIVAS_POR_CATEGORIA.get(categoria.lower().strip(), set())

    for neg in negativas:
        neg_n = _norm(neg)
        if neg_n and neg_n in t and neg_n not in item:
            return False

    # 2) Patrón de accesorio: "<algo> para <ítem>" → es accesorio, no el ítem.
    #    Tomamos el sustantivo principal del ítem (primer token no-stopword).
    item_tokens = [w for w in item.split() if len(w) > 2 and w not in _STOPWORDS]
    if item_tokens:
        head = _stem(item_tokens[0])
        palabras = t.split()
        idx = next(
            (i for i, p in enumerate(palabras)
             if _stem(p) == head or (len(head) > 3 and p.startswith(head))),
            -1,
        )
        if idx > 0 and "para" in palabras[max(0, idx - 2):idx]:
            return False  # "broca para taladro"

    return True
