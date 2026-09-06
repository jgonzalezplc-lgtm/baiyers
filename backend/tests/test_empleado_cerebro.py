import asyncio
from types import SimpleNamespace

from app.services.canales.correo import normalizar_correo
from app.services.empleado.cerebro import CerebroEmpleado
from app.services.empleado.ejecutor import EjecutorTools
from app.services.mcp_context import ApplicationActorContext


class ClienteFalso:
    def __init__(self, respuestas):
        self.respuestas = iter(respuestas)
        self.messages = self
        self.llamadas = []

    async def create(self, **kwargs):
        self.llamadas.append(kwargs)
        return next(self.respuestas)


def _actor():
    return ApplicationActorContext("u-1", "org-1", "Empresa", ("u-1",),
        scopes=frozenset({"quotes:write", "lists:write"}))


def test_el_cerebro_conserva_ruta_y_controla_idempotencia():
    llamada = SimpleNamespace(type="tool_use", name="quote_new_project", id="tool-1", input={"descripcion": "20 cascos"})
    fin = SimpleNamespace(type="text", text="Listo, inicié la cotización.")
    cliente = ClienteFalso([SimpleNamespace(content=[llamada]), SimpleNamespace(content=[fin])])
    recibidos = []

    async def handler(_actor, args):
        recibidos.append(args)
        return {"estado": "cotizando"}

    cerebro = CerebroEmpleado(EjecutorTools({"quote_new_project": handler}, validar_autorizacion=lambda *_: True), cliente)
    mensaje = normalizar_correo(gmail_message_id="m-1", gmail_thread_id="t-1", from_email="solicitante@empresa.cl", body_text="Necesito cascos")
    respuesta = asyncio.run(cerebro.procesar(_actor(), mensaje))

    assert respuesta.ruta == mensaje.ruta_respuesta
    assert respuesta.texto == "Listo, inicié la cotización."
    assert recibidos[0]["idempotency_key"].startswith("empleado:")
    assert "idempotency_key" not in cliente.llamadas[0]["tools"][0]["input_schema"]["properties"]


def test_una_herramienta_no_habilitada_no_se_ejecuta():
    llamada = SimpleNamespace(type="tool_use", name="send_rfq", id="tool-1", input={})
    fin = SimpleNamespace(type="text", text="No está habilitado.")
    cliente = ClienteFalso([SimpleNamespace(content=[llamada]), SimpleNamespace(content=[fin])])
    cerebro = CerebroEmpleado(EjecutorTools({}, validar_autorizacion=lambda *_: True), cliente)
    mensaje = normalizar_correo(gmail_message_id="m-1", gmail_thread_id="t-1", from_email="solicitante@empresa.cl", body_text="envía esto")
    assert asyncio.run(cerebro.procesar(_actor(), mensaje)).texto == "No está habilitado."
