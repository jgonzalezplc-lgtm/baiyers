"""Una moneda leída no se puede reetiquetar por el país de la búsqueda.

Caso real (2026-08-27): al cotizar un tocadiscos por MCP, los resultados venían
en USD y el sistema los mostró como CLP. `_parse_precio` devolvía "USD" tanto
para un precio marcado en dólares como para uno que no decía nada, y el llamador
lo pisaba a CLP cuando la búsqueda era chilena. Dos suposiciones apiladas.

Consecuencia: un artículo de US$199 aparecía como $199 CLP — mil veces más
barato, y primero en el comparador.
"""
import pytest

from app.routers.buscar import _detectar_moneda, _parse_precio, _parse_precio_detallado


# ─── Monedas leídas de verdad ────────────────────────────────────────────────

@pytest.mark.parametrize("texto,moneda", [
    ("US$199.99", "USD"),
    ("USD 199.99", "USD"),
    ("U$S 199", "USD"),
    ("CLP 21.190", "CLP"),
    ("€45,99", "EUR"),
    ("£120.00", "GBP"),
    ("¥1200", "CNY"),
])
def test_moneda_explicita_queda_confirmada(texto, moneda):
    _, detectada, confirmada = _parse_precio_detallado(texto)
    assert (detectada, confirmada) == (moneda, True)


@pytest.mark.parametrize("texto", ["$21.190", "$199.99", "$1.234.567", "21190"])
def test_simbolo_ambiguo_no_se_confirma(texto):
    """En Chile "$" es el peso; en EE.UU. el dólar. El símbolo solo no alcanza."""
    assert _parse_precio_detallado(texto)[2] is False


def test_precio_vacio_no_confirma_nada():
    assert _parse_precio_detallado(None) == (None, "USD", False)
    assert _parse_precio_detallado("")[2] is False


# ─── La inferencia por país sólo aplica a lo no confirmado ───────────────────

def _moneda_final(texto: str, pais: str) -> str:
    """Reproduce la decisión del llamador tras el arreglo."""
    _, moneda, confirmada = _parse_precio_detallado(texto)
    if not confirmada:
        moneda = "CLP" if pais == "CL" else "USD"
    return moneda


def test_un_precio_en_dolares_no_se_vuelve_pesos_en_una_busqueda_chilena():
    """El bug exacto del tocadiscos."""
    assert _moneda_final("US$199.99", "CL") == "USD"


def test_un_precio_ambiguo_en_chile_se_asume_pesos():
    """Sigue funcionando el caso común: una tienda chilena que escribe "$21.190"."""
    assert _moneda_final("$21.190", "CL") == "CLP"


def test_un_precio_ambiguo_fuera_de_chile_se_asume_dolares():
    assert _moneda_final("$199.99", "US") == "USD"


def test_una_moneda_confirmada_no_cambia_en_ningun_pais():
    for pais in ("CL", "US", "AR"):
        assert _moneda_final("€45,99", pais) == "EUR"
        assert _moneda_final("CLP 21.190", pais) == "CLP"


# ─── El parseo del monto no cambió ───────────────────────────────────────────

@pytest.mark.parametrize("texto,valor", [
    ("$21.190", 21190.0),        # miles chileno
    ("US$199.99", 199.99),       # decimal anglosajón
    ("€1.234,56", 1234.56),      # miles europeo con decimal
    ("$1,234.56", 1234.56),      # miles anglosajón con decimal
    ("45,99", 45.99),            # decimal con coma
    ("45,990", 45990.0),         # miles con coma
])
def test_montos_se_siguen_parseando_igual(texto, valor):
    assert _parse_precio_detallado(texto)[0] == valor


def test_la_firma_vieja_sigue_devolviendo_dos_valores():
    """`_parse_precio` lo usan otros llamadores: no puede cambiar de forma."""
    resultado = _parse_precio("$21.190")
    assert len(resultado) == 2
    assert resultado[0] == 21190.0


def test_detectar_moneda_es_insensible_a_mayusculas():
    assert _detectar_moneda("us$199")[0] == "USD"
    assert _detectar_moneda("Usd 199")[0] == "USD"
