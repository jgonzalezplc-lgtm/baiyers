"""En producción no se sirve el mapa completo de la API.

`/openapi.json` exponía los ~200 endpoints, incluido todo el plano
administrativo (dump de tablas, correos de usuarios, recuperación de contraseña
de cualquier cuenta). Las rutas están cerradas por `tenant_guard`, así que esto
no es una vulnerabilidad por sí sola — pero le regala el trabajo de
descubrimiento a un atacante. Local sigue teniendo Swagger.
"""
import importlib

import app.config
import app.main


def test_docs_apagados_en_produccion(monkeypatch):
    monkeypatch.setattr(app.config.settings, "environment", "production")
    modulo = importlib.reload(app.main)
    try:
        assert modulo.app.openapi_url is None
        assert modulo.app.docs_url is None
        assert modulo.app.redoc_url is None
    finally:
        # Dejar el módulo como estaba: otros tests importan `app.main`.
        monkeypatch.setattr(app.config.settings, "environment", "development")
        importlib.reload(app.main)


def test_docs_disponibles_fuera_de_produccion():
    assert app.main.app.openapi_url == "/openapi.json"
