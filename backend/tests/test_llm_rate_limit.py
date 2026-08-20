import unittest
from unittest.mock import MagicMock

from fastapi import HTTPException

from app.services.llm_rate_limit import (
    es_llamada_interna,
    ip_cliente,
    limitar_por_ip,
    registrar_intento,
    reset_para_tests,
)


def _request(headers=None, host="1.2.3.4"):
    req = MagicMock()
    req.headers = headers or {}
    req.client = MagicMock(host=host) if host else None
    return req


class IpClienteTest(unittest.TestCase):
    def test_prefiere_cf_connecting_ip(self):
        """Cloudflare sobrescribe esa cabecera, así que es la confiable — si
        se usara X-Forwarded-For a ciegas, el cliente podría falsearla."""
        req = _request({"cf-connecting-ip": "9.9.9.9", "x-forwarded-for": "1.1.1.1"})
        self.assertEqual(ip_cliente(req), "9.9.9.9")

    def test_usa_el_primer_x_forwarded_for_si_no_hay_cloudflare(self):
        self.assertEqual(ip_cliente(_request({"x-forwarded-for": "1.1.1.1, 2.2.2.2"})), "1.1.1.1")

    def test_cae_al_host_directo_sin_proxy(self):
        self.assertEqual(ip_cliente(_request(host="5.5.5.5")), "5.5.5.5")

    def test_sin_cliente_no_revienta(self):
        self.assertEqual(ip_cliente(_request(host=None)), "desconocido")


class RegistrarIntentoTest(unittest.TestCase):
    def setUp(self):
        reset_para_tests()

    def test_permite_hasta_el_limite_y_luego_corta(self):
        for _ in range(3):
            registrar_intento("x", "ip1", por_minuto=3, por_hora=100)
        with self.assertRaises(HTTPException) as ctx:
            registrar_intento("x", "ip1", por_minuto=3, por_hora=100)
        self.assertEqual(ctx.exception.status_code, 429)

    def test_el_limite_por_hora_tambien_corta(self):
        for _ in range(5):
            registrar_intento("x", "ip1", por_minuto=100, por_hora=5)
        with self.assertRaises(HTTPException):
            registrar_intento("x", "ip1", por_minuto=100, por_hora=5)

    def test_una_ip_no_afecta_a_otra(self):
        for _ in range(3):
            registrar_intento("x", "ip1", por_minuto=3, por_hora=100)
        registrar_intento("x", "ip2", por_minuto=3, por_hora=100)  # no lanza

    def test_endpoints_distintos_no_comparten_contador(self):
        for _ in range(3):
            registrar_intento("a", "ip1", por_minuto=3, por_hora=100)
        registrar_intento("b", "ip1", por_minuto=3, por_hora=100)  # no lanza

    def test_el_intento_rechazado_no_se_contabiliza(self):
        """Si el rechazo sumara a la ventana, un atacante en loop dejaría a esa
        IP bloqueada para siempre en vez de que el bloqueo expire solo."""
        from app.services import llm_rate_limit as mod

        for _ in range(2):
            registrar_intento("x", "ip1", por_minuto=2, por_hora=100)
        for _ in range(5):
            with self.assertRaises(HTTPException):
                registrar_intento("x", "ip1", por_minuto=2, por_hora=100)
        self.assertEqual(len(mod._ventanas[("x", "ip1")]), 2)


class LlamadaInternaTest(unittest.TestCase):
    """`/api/buscar` lo consumen el servidor MCP y la API pública contra
    `http://localhost:8000`. Sin exención, ambos comparten la IP de loopback y
    se estrangulan entre sí."""

    def setUp(self):
        reset_para_tests()

    def test_loopback_sin_headers_de_proxy_es_interno(self):
        self.assertTrue(es_llamada_interna(_request(host="127.0.0.1")))
        self.assertTrue(es_llamada_interna(_request(host="::1")))

    def test_x_forwarded_for_falsificado_no_alcanza_para_pasar_por_interno(self):
        """El bypass obvio: declararse localhost desde internet. Un request que
        entra por Cloudflare → Railway siempre trae alguna de las dos cabeceras,
        así que su sola presencia descalifica la exención."""
        self.assertFalse(
            es_llamada_interna(_request({"x-forwarded-for": "127.0.0.1"}, host="127.0.0.1"))
        )
        self.assertFalse(
            es_llamada_interna(_request({"cf-connecting-ip": "127.0.0.1"}, host="127.0.0.1"))
        )

    def test_ip_publica_no_es_interna(self):
        self.assertFalse(es_llamada_interna(_request(host="8.8.8.8")))

    def test_host_no_parseable_no_es_interno(self):
        self.assertFalse(es_llamada_interna(_request(host="localhost")))
        self.assertFalse(es_llamada_interna(_request(host=None)))

    def test_la_dependencia_no_gasta_cupo_en_llamadas_internas(self):
        dep = limitar_por_ip("interna", por_minuto=1, por_hora=1)
        for _ in range(10):
            dep(_request(host="127.0.0.1"))  # no lanza aunque el límite sea 1

    def test_la_dependencia_si_limita_trafico_externo(self):
        dep = limitar_por_ip("externa", por_minuto=1, por_hora=10)
        dep(_request({"cf-connecting-ip": "9.9.9.9"}))
        with self.assertRaises(HTTPException):
            dep(_request({"cf-connecting-ip": "9.9.9.9"}))


if __name__ == "__main__":
    unittest.main()
