"""El logo vive en un bucket privado: la URL se firma al leer, no se guarda.

Contexto del bug que esto arregla: `subir_logo()` devolvía
`get_public_url(...)` y esa URL se persistía en `organizaciones.logo_url`. Pero
`company-logos` tiene `public=false`, así que la ruta `/object/public/...`
responde `400 Bucket not found` y el logo NUNCA cargaba. Los PDFs de OC y los
informes caían siempre al fallback de texto, en silencio.
"""
from unittest.mock import MagicMock, patch

from app.services.logo_upload import BUCKET_LOGOS, path_de_logo_legado


# ── Recuperación de las organizaciones que ya tienen la URL rota guardada ─────

def test_extrae_el_path_de_una_url_publica_vieja():
    """La `logo_url` rota contiene el path real, así que las organizaciones
    existentes se recuperan solas sin backfill."""
    url = f"https://proj.supabase.co/storage/v1/object/public/{BUCKET_LOGOS}/org-123/abc.png"
    assert path_de_logo_legado(url) == "org-123/abc.png"


def test_ignora_el_query_string_al_extraer_el_path():
    url = f"https://proj.supabase.co/storage/v1/object/public/{BUCKET_LOGOS}/org-1/a.png?t=123"
    assert path_de_logo_legado(url) == "org-1/a.png"


def test_una_url_de_otro_bucket_no_se_confunde_con_un_logo():
    """No debe rescatar paths de `ordenes-compra` ni de `boletas`: firmar contra
    el bucket equivocado devolvería basura o filtraría otra cosa."""
    assert path_de_logo_legado("https://proj.supabase.co/.../ordenes-compra/x.pdf") is None
    assert path_de_logo_legado("https://cdn.otrositio.com/logo.png") is None


def test_sin_url_no_hay_path():
    assert path_de_logo_legado(None) is None
    assert path_de_logo_legado("") is None


# ── subir_logo devuelve el path durable, no una URL ───────────────────────────

def test_subir_logo_devuelve_el_path_y_no_una_url():
    sb = MagicMock()
    with patch("app.services.logo_upload._sb", return_value=sb):
        from app.services.logo_upload import subir_logo
        path = subir_logo("org-42", "image/png", b"\x89PNG...")

    assert path.startswith("org-42/"), path
    assert path.endswith(".png")
    assert "http" not in path, "debe devolver el path, no una URL"
    # Y nunca vuelve a construir una URL pública sobre un bucket privado.
    sb.storage.from_.return_value.get_public_url.assert_not_called()


# ── Fallar al firmar no puede tumbar un documento ────────────────────────────

def test_si_no_se_puede_firmar_devuelve_none_en_vez_de_lanzar():
    """El logo es decorativo: su ausencia cae al fallback de texto, pero una
    excepción acá abortaría la generación de la OC entera."""
    sb = MagicMock()
    sb.storage.from_.return_value.create_signed_url.side_effect = RuntimeError("storage caído")
    with patch("app.services.logo_upload._sb", return_value=sb):
        from app.services.logo_upload import url_firmada_de_logo
        assert url_firmada_de_logo("org/a.png") is None


def test_acepta_las_dos_claves_que_usa_el_sdk():
    """El SDK renombró la clave entre versiones; soportar una sola haría que el
    logo desapareciera al actualizar la dependencia."""
    from app.services.logo_upload import url_firmada_de_logo
    for clave in ("signedURL", "signedUrl", "signed_url"):
        sb = MagicMock()
        sb.storage.from_.return_value.create_signed_url.return_value = {clave: "https://firmada"}
        with patch("app.services.logo_upload._sb", return_value=sb):
            assert url_firmada_de_logo("org/a.png") == "https://firmada", clave


def test_path_vacio_no_llama_a_storage():
    sb = MagicMock()
    with patch("app.services.logo_upload._sb", return_value=sb):
        from app.services.logo_upload import url_firmada_de_logo
        assert url_firmada_de_logo("") is None
    sb.storage.from_.assert_not_called()


# ── El perfil resuelve la URL en cada lectura ────────────────────────────────

def _perfil_con(fila: dict) -> dict:
    sb = MagicMock()
    sb.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = (
        MagicMock(data=fila)
    )
    with patch("app.services.organizacion._sb", return_value=sb), \
         patch("app.services.logo_upload._sb", return_value=_storage_que_firma()):
        from app.services.organizacion import obtener_perfil_organizacion
        return obtener_perfil_organizacion("org-1")


def _storage_que_firma():
    sb = MagicMock()
    sb.storage.from_.return_value.create_signed_url.return_value = {"signedURL": "https://firmada"}
    return sb


def test_el_perfil_firma_desde_el_storage_path():
    perfil = _perfil_con({"nombre": "ACME", "logo_url": None, "logo_storage_path": "org-1/a.png"})
    assert perfil["logo_url"] == "https://firmada"


def test_el_perfil_recupera_organizaciones_viejas_desde_la_url_rota():
    url_rota = f"https://p.supabase.co/storage/v1/object/public/{BUCKET_LOGOS}/org-1/viejo.png"
    perfil = _perfil_con({"nombre": "ACME", "logo_url": url_rota, "logo_storage_path": None})
    assert perfil["logo_url"] == "https://firmada"


def test_sin_logo_el_perfil_devuelve_none_y_conserva_el_resto():
    perfil = _perfil_con({"nombre": "ACME", "rut": "1-9", "logo_url": None, "logo_storage_path": None})
    assert perfil["logo_url"] is None
    assert perfil["nombre"] == "ACME" and perfil["rut"] == "1-9"


def test_el_perfil_no_expone_el_storage_path():
    """`logo_storage_path` es detalle interno: sale por `/api/organizacion/mia`
    y no aporta nada a un cliente que sólo puede usar la URL firmada."""
    perfil = _perfil_con({"nombre": "ACME", "logo_url": None, "logo_storage_path": "org-1/a.png"})
    assert "logo_storage_path" not in perfil
