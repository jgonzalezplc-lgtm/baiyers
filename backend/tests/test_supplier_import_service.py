import base64
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.services.mcp_context import ApplicationActorContext
from app.services.supplier_import_service import commit_supplier_import


def actor():
    return ApplicationActorContext("u1", "o1", "Org", ("u1",), client_id="codex")


def test_commit_import_requiere_confirmacion():
    with pytest.raises(HTTPException) as error:
        __import__("asyncio").run(commit_supplier_import(MagicMock(), actor(), "d1", confirmed=False))
    assert error.value.status_code == 409
