from app.services.proveedores_sugeridos import categorias_banco, sugeridos_para_categoria


def test_mapea_categorias_del_identificador_al_banco():
    assert categorias_banco("electronica") == {"electronico"}
    assert categorias_banco("carpinteria") == {"madera"}
    assert "mecanico" in categorias_banco("hidraulico")


def test_sugerencias_incluyen_contacto_y_leyenda():
    sugeridos = sugeridos_para_categoria("electronica")
    assert any(p["nombre"] == "MCI Electronics" for p in sugeridos)
    assert all(p["email"] and p["match_label"] == "Match por categoría" for p in sugeridos)
    assert all(p["origen"] == "sugerido" for p in sugeridos)


def test_prioriza_producto_concreto_sobre_match_general():
    sugeridos = sugeridos_para_categoria("electrico", "variador de frecuencia industrial")
    rhona = next(i for i, p in enumerate(sugeridos) if p["nombre"] == "Rhona S.A.")
    dartel = next(i for i, p in enumerate(sugeridos) if p["nombre"] == "Dartel Electricidad")
    assert rhona < dartel
    assert sugeridos[rhona]["match_label"].startswith("Match por producto:")
    assert sugeridos[rhona]["match_score"] > sugeridos[dartel]["match_score"]


def test_ignora_proveedor_sugerido_desactivado(monkeypatch):
    monkeypatch.setattr(
        "app.services.proveedores_sugeridos.cargar_banco_sugerido",
        lambda: [{
            "company_name": "Inactivo", "primary_email": "x@example.com",
            "categories": ["electrico"], "is_suggested": False,
        }],
    )
    assert sugeridos_para_categoria("electrico", "cable") == []


def test_no_puntua_palabras_genericas_del_rubro():
    sugeridos = sugeridos_para_categoria("mecanico", "rodamiento industrial SKF")
    assert sugeridos[0]["nombre"] == "SKF Chile"
    empack = next(p for p in sugeridos if p["nombre"] == "Empack")
    assert empack["match_score"] == 0
