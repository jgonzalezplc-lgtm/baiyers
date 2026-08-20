"""Topes de tamaño y protección SSRF de los endpoints que gastan LLM.

`identificar`, `buscar` y `analisis` llaman a Gemini/Anthropic sin
autenticación. El rate limit por IP es un freno evadible por un atacante
distribuido; lo que acota de verdad el costo *por request* son estos topes, así
que conviene que estén cubiertos por pruebas.

Todas las validaciones de acá ocurren en Pydantic, antes de tocar ninguna API
paga: los casos rechazados nunca llegan al cuerpo del endpoint.
"""
import unittest

from pydantic import ValidationError

from app.routers.analisis import MAX_OPCIONES, AnalizarRequest
from app.routers.buscar import (
    MAX_LARGO_TERMINO,
    MAX_PREFETCH_IDS,
    MAX_TERMINOS,
    BuscarRequest,
    PrefetchRequest,
)
from app.routers.identificar import MAX_ADJUNTO_B64, MAX_DESCRIPCION, IdentificarRequest


class TopesBuscarTest(unittest.TestCase):
    def test_acepta_un_request_normal(self):
        req = BuscarRequest(
            cotizacion_id="abc", terminos_es=["tablón de pino"], terminos_en=["pine board"],
            nombre_item="tablón", categoria="carpinteria",
        )
        self.assertEqual(req.nombre_item, "tablón")

    def test_rechaza_demasiados_terminos(self):
        with self.assertRaises(ValidationError):
            BuscarRequest(
                cotizacion_id="abc", terminos_es=["x"] * (MAX_TERMINOS + 1),
                terminos_en=[], nombre_item="x",
            )

    def test_rechaza_un_termino_gigante(self):
        """El `max_length` de la lista sólo topa la cantidad: sin un tope por
        elemento, 10 términos de 1 MB pasaban la validación."""
        with self.assertRaises(ValidationError):
            BuscarRequest(
                cotizacion_id="abc", terminos_es=["x" * (MAX_LARGO_TERMINO + 1)],
                terminos_en=[], nombre_item="x",
            )

    def test_prefetch_rechaza_amplificacion(self):
        """Cada id encola una búsqueda completa en background; sin tope, un solo
        request encolaba miles."""
        with self.assertRaises(ValidationError):
            PrefetchRequest(cotizacion_ids=["a"] * (MAX_PREFETCH_IDS + 1))

    def test_prefetch_acepta_una_lista_realista(self):
        self.assertEqual(len(PrefetchRequest(cotizacion_ids=["a"] * 20).cotizacion_ids), 20)


class TopesIdentificarTest(unittest.TestCase):
    def test_acepta_una_descripcion_normal(self):
        req = IdentificarRequest(descripcion="necesito 20 tablones de pino")
        self.assertIsNone(req.imagen_url)

    def test_rechaza_descripcion_gigante(self):
        with self.assertRaises(ValidationError):
            IdentificarRequest(descripcion="x" * (MAX_DESCRIPCION + 1))

    def test_rechaza_adjunto_gigante(self):
        with self.assertRaises(ValidationError):
            IdentificarRequest(archivo_base64="x" * (MAX_ADJUNTO_B64 + 1))

    def test_acepta_una_foto_de_celular(self):
        """El tope tiene que dejar pasar el caso real que motiva el endpoint."""
        IdentificarRequest(imagen_base64="x" * 3_000_000)


class TopesAnalisisTest(unittest.TestCase):
    def test_rechaza_demasiadas_opciones(self):
        opcion = {"proveedor_nombre": "p", "precio": 1000}
        with self.assertRaises(ValidationError):
            AnalizarRequest(
                user_id="u", item_nombre="i", opciones=[opcion] * (MAX_OPCIONES + 1),
            )

    def test_rechaza_cantidad_absurda(self):
        with self.assertRaises(ValidationError):
            AnalizarRequest(user_id="u", item_nombre="i", cantidad=0, opciones=[])


class SsrfIdentificarTest(unittest.IsolatedAsyncioTestCase):
    """`imagen_url` se descargaba con un GET directo a lo que mandara el
    cliente: SSRF sin autenticación contra la red interna. Ahora reusa el guard
    de logos."""

    async def test_rechaza_ip_privada(self):
        from app.services.logo_upload import descargar_y_validar_url

        for url in (
            "http://169.254.169.254/latest/meta-data/",  # metadata endpoint
            "https://127.0.0.1/x.png",
            "https://10.0.0.5/x.png",
        ):
            with self.subTest(url=url), self.assertRaises(ValueError):
                await descargar_y_validar_url(url)

    async def test_rechaza_esquema_no_http(self):
        from app.services.logo_upload import descargar_y_validar_url

        with self.assertRaises(ValueError):
            await descargar_y_validar_url("file:///etc/passwd")


if __name__ == "__main__":
    unittest.main()
