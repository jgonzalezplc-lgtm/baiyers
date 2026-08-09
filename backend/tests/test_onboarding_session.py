"""Tests de onboarding_session.py — incluye regresión del bug real de
postgrest-py donde `.maybe_single().execute()` devuelve `None` en vez de un
objeto con `.data = None` cuando no hay filas."""
import unittest
from unittest.mock import MagicMock, patch


class FakeQueryExecuteNone:
    def select(self, *_): return self
    def eq(self, *_): return self
    def maybe_single(self): return self
    def execute(self): return None


class ObtenerSesionTest(unittest.TestCase):
    def test_sesion_inexistente_devuelve_none_sin_crashear(self):
        fake = MagicMock()
        fake.table.return_value = FakeQueryExecuteNone()
        with patch("app.services.onboarding_session._sb", return_value=fake):
            from app.services.onboarding_session import obtener_sesion
            resultado = obtener_sesion("sesion-inexistente", "u-cualquiera")
        self.assertIsNone(resultado)

    def test_sesion_propia_devuelve_la_fila(self):
        fila = {"id": "s1", "user_id": "u-1", "draft": {}}
        fake_exec = MagicMock(data=fila)
        fake = MagicMock()
        fake.table.return_value.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value = fake_exec
        with patch("app.services.onboarding_session._sb", return_value=fake):
            from app.services.onboarding_session import obtener_sesion
            resultado = obtener_sesion("s1", "u-1")
        self.assertEqual(resultado, fila)


if __name__ == "__main__":
    unittest.main()
