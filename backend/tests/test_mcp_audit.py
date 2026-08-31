from app.mcp.audit import _entity, _nivel_de_confirmacion


def test_confirmed_del_modelo_no_se_audita_como_confirmacion_humana():
    """`confirmed` lo elige el propio modelo. Registrarlo como "explicit" hacía
    que la auditoría certificara una confirmación humana que nadie verificó."""
    assert _nivel_de_confirmacion({"confirmed": True}) == "asserted_by_model"
    assert _nivel_de_confirmacion({"confirmed": True}) != "explicit"


def test_sin_confirmed_no_hay_ningun_respaldo():
    for argumentos in ({}, {"confirmed": False}, {"confirmed": "true"}, {"confirmed": None}):
        assert _nivel_de_confirmacion(argumentos) == "none", argumentos


def test_audit_extrae_solo_referencia_no_payload_sensible():
    kind, entity_id = _entity({"list_id": "l1", "pdf_base64": "SECRETO", "body": "correo"})
    assert (kind, entity_id) == ("list", "l1")


def test_audit_sin_entidad_no_serializa_argumentos():
    assert _entity({"query": "proveedor"}) == (None, None)
