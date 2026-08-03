import unittest
from decimal import Decimal
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers.admin_control_plane import router as admin_router
from app.services.control_plane_telemetry import (
    estimar_costo_usd,
    registrar_uso_ia,
    sanitizar_metadata,
)


class _Result:
    def __init__(self, data): self.data = data


class _Query:
    def __init__(self, sb, table, payload): self.sb, self.table, self.payload = sb, table, payload
    def execute(self):
        self.sb.inserted.append((self.table, self.payload))
        return _Result([{"id": "evt-1"}])


class _Table:
    def __init__(self, sb, name): self.sb, self.name = sb, name
    def insert(self, payload): return _Query(self.sb, self.name, payload)


class _Rpc:
    def execute(self): return _Result("org-1")


class _FakeSupabase:
    def __init__(self): self.inserted = []
    def table(self, name): return _Table(self, name)
    def rpc(self, name, params): return _Rpc()


class ControlPlaneTelemetryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app = FastAPI()
        app.include_router(admin_router)
        cls.client = TestClient(app)

    def test_api_admin_rechaza_request_sin_bearer(self):
        response = self.client.get("/api/admin-control-plane/dashboard")
        self.assertEqual(response.status_code, 401)

    def test_calcula_costo_con_snapshot(self):
        costo, snapshot = estimar_costo_usd("google", "gemini-3.5-flash-lite", 1_000_000, 1_000_000)
        self.assertEqual(costo, Decimal("2.80000000"))
        self.assertEqual(snapshot["catalog_version"], "2026-08-03")

    def test_metadata_elimina_pii_y_limita_texto(self):
        limpia = sanitizar_metadata({"prompt": "secreto", "email": "x@y.cl", "ronda": 2, "tipo": "x" * 500})
        self.assertNotIn("prompt", limpia)
        self.assertNotIn("email", limpia)
        self.assertEqual(limpia["ronda"], 2)
        self.assertEqual(len(limpia["tipo"]), 300)

    def test_registro_atribuye_organizacion_y_fallback(self):
        sb = _FakeSupabase()
        with patch("app.services.control_plane_telemetry._sb", return_value=sb):
            event_id = registrar_uso_ia(
                feature="identificacion", provider="google",
                requested_model="gemini-3.5-flash-lite", effective_model="gemini-2.5-flash",
                input_tokens=100, output_tokens=20, latency_ms=1500,
                status="fallback", user_id="user-1", metadata={"prompt": "no guardar", "modo": "cubicacion"},
            )
        self.assertEqual(event_id, "evt-1")
        table, payload = sb.inserted[0]
        self.assertEqual(table, "ai_usage_events")
        self.assertEqual(payload["organization_id"], "org-1")
        self.assertTrue(payload["fallback_used"])
        self.assertNotIn("prompt", payload["metadata"])

    def test_falla_sin_interrumpir_negocio(self):
        with patch("app.services.control_plane_telemetry._sb", side_effect=RuntimeError("tabla ausente")):
            self.assertIsNone(registrar_uso_ia(
                feature="test", provider="google", requested_model="x", effective_model="x",
            ))


if __name__ == "__main__":
    unittest.main()
