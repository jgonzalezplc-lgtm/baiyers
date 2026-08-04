from app.services.proveedores_sugeridos import categorias_banco, sugeridos_para_categoria


def test_mapea_categorias_del_identificador_al_banco():
    assert categorias_banco("electronica") == {"electronico"}
    assert categorias_banco("carpinteria") == {"madera"}
    assert "mecanico" in categorias_banco("hidraulico")


def test_sugerencias_incluyen_contacto_y_leyenda():
    sugeridos = sugeridos_para_categoria("electronica")
    assert any(p["nombre"] == "MCI Electronics" for p in sugeridos)
    assert all(p["email"] and p["match_label"] == "Posible match" for p in sugeridos)
    assert all(p["origen"] == "sugerido" for p in sugeridos)
