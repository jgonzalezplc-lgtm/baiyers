"""Tests del helper compartido `ejecutar_maybe_single` — protege contra el
bug real de postgrest-py 2.x donde `.maybe_single().execute()` devuelve
`None` en vez de un objeto con `.data = None`."""
import unittest
from unittest.mock import MagicMock

from app.services.supabase import ejecutar_maybe_single


class EjecutarMaybeSingleTest(unittest.TestCase):
    def test_execute_devuelve_none_no_crashea(self):
        query = MagicMock()
        query.execute.return_value = None
        resp = ejecutar_maybe_single(query)
        self.assertIsNone(resp.data)

    def test_respuesta_real_se_devuelve_tal_cual(self):
        fake_resp = MagicMock(data={"id": "x"})
        query = MagicMock()
        query.execute.return_value = fake_resp
        resp = ejecutar_maybe_single(query)
        self.assertIs(resp, fake_resp)
        self.assertEqual(resp.data, {"id": "x"})

    def test_sin_filas_con_data_none_se_devuelve_tal_cual(self):
        fake_resp = MagicMock(data=None)
        query = MagicMock()
        query.execute.return_value = fake_resp
        resp = ejecutar_maybe_single(query)
        self.assertIsNone(resp.data)

    def test_excepcion_real_se_propaga_no_se_esconde(self):
        query = MagicMock()
        query.execute.side_effect = RuntimeError("error de red real")
        with self.assertRaises(RuntimeError):
            ejecutar_maybe_single(query)


if __name__ == "__main__":
    unittest.main()
