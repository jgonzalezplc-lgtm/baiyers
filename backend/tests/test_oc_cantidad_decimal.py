"""La emisión de OC acepta cantidades positivas con hasta tres decimales."""
import pytest
from pydantic import ValidationError

from app.routers.oc import CrearOCRequest


def _request(cantidad: float, unidad: str = "und") -> CrearOCRequest:
    return CrearOCRequest(
        cotizacion_id="c1", nombre_item="Material", proveedor_nombre="Proveedor",
        cantidad=cantidad, unidad=unidad, precio_unitario=1000,
    )


@pytest.mark.parametrize("cantidad,unidad", [(5.0, "und"), (0.5, "kg"), (1.25, "m"), (2.75, "L")])
def test_admite_cantidad_decimal_positiva(cantidad, unidad):
    request = _request(cantidad, unidad)
    assert request.cantidad == cantidad
    assert request.unidad == unidad


@pytest.mark.parametrize("cantidad", [0, -0.5, 1.2345])
def test_rechaza_cantidad_no_positiva_o_con_mas_de_tres_decimales(cantidad):
    with pytest.raises(ValidationError):
        _request(cantidad)
