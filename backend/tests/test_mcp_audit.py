from app.mcp.audit import _entity


def test_audit_extrae_solo_referencia_no_payload_sensible():
    kind, entity_id = _entity({"list_id": "l1", "pdf_base64": "SECRETO", "body": "correo"})
    assert (kind, entity_id) == ("list", "l1")


def test_audit_sin_entidad_no_serializa_argumentos():
    assert _entity({"query": "proveedor"}) == (None, None)
