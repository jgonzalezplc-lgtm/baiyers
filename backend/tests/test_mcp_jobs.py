from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.services.mcp_context import ApplicationActorContext
from app.services.mcp_jobs import cancel_job, get_job, list_jobs, update_job


def actor():
    return ApplicationActorContext("u", "org-1", "Org", ("u",), client_id="codex")


def _sb_with_get(data):
    sb = MagicMock()
    query = sb.table.return_value.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value
    query.execute.return_value = MagicMock(data=data)
    return sb


def test_get_job_siempre_filtra_organizacion():
    sb = _sb_with_get({"id": "job-1", "organization_id": "org-1"})
    assert get_job(sb, actor(), "job-1")["id"] == "job-1"


def test_get_job_ajeno_se_presenta_como_no_encontrado():
    with pytest.raises(HTTPException) as error:
        get_job(_sb_with_get(None), actor(), "job-ajeno")
    assert error.value.status_code == 404


def test_update_job_valida_estado_y_progreso_antes_de_escribir():
    with pytest.raises(HTTPException):
        update_job(MagicMock(), actor(), "job", status="inventado", progress=0)
    with pytest.raises(HTTPException):
        update_job(MagicMock(), actor(), "job", status="running", progress=101)


def test_list_jobs_valida_filtros():
    with pytest.raises(HTTPException):
        list_jobs(MagicMock(), actor(), status="inventado")
    with pytest.raises(HTTPException):
        list_jobs(MagicMock(), actor(), limit=101)


def test_cancel_job_no_reabre_un_job_terminado(monkeypatch):
    monkeypatch.setattr("app.services.mcp_jobs.get_job", lambda *_: {"id": "j1", "status": "completed"})
    with pytest.raises(HTTPException) as error:
        cancel_job(MagicMock(), actor(), "j1")
    assert error.value.status_code == 409
