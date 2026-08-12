from app.routers.proveedores_import import _mapear_fila, _tiene_columnas_reconocidas


def test_mapea_formato_catalogo_baiyer():
    fila = _mapear_fila({
        "company_name": "Dartel Electricidad",
        "primary_email": "ventas@dartel.cl",
        "website": "https://dartel.cl",
        "phone": "+56 2 2680 0000",
        "category": "electrico",
    })

    assert fila["nombre"] == "Dartel Electricidad"
    assert fila["email"] == "ventas@dartel.cl"
    assert fila["sitio_web"] == "https://dartel.cl"
    assert fila["telefono"] == "+56 2 2680 0000"
    assert fila["categoria"] == "electrico"


def test_reconoce_company_name_sin_necesitar_gemini():
    assert _tiene_columnas_reconocidas(["company_name", "primary_email", "website"])


def test_normaliza_salida_de_gemini_con_aliases():
    fila = _mapear_fila({"supplier_name": "Proveedor Uno", "correo": "uno@example.cl"})
    assert fila["nombre"] == "Proveedor Uno"
    assert fila["email"] == "uno@example.cl"
