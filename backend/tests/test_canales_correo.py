import pytest

from app.services.canales.correo import normalizar_correo
from app.services.empleado.contratos import Canal


def test_correo_preserva_el_hilo_y_el_destinatario_original():
    mensaje = normalizar_correo(
        gmail_message_id="m-1", gmail_thread_id="t-1",
        from_email=" Compras@Empresa.cl ", body_text="Necesito cotizar guantes.",
    )
    assert mensaje.canal == Canal.CORREO
    assert mensaje.ruta_respuesta.hilo == "t-1"
    assert mensaje.ruta_respuesta.destinatario == "compras@empresa.cl"


def test_correo_incompleto_se_rechaza_antes_del_cerebro():
    with pytest.raises(ValueError):
        normalizar_correo(
            gmail_message_id="", gmail_thread_id="t-1", from_email="a@empresa.cl", body_text="hola",
        )
