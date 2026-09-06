import pytest
from fastapi import HTTPException

from app.services.auth_context import AuthContext
from app.services.empleado.canales import crear_canal_correo


class Tabla:
    def __init__(self): self.fila = None
    def upsert(self, fila, **_kwargs): self.fila = fila; return self
    def execute(self): return type("R", (), {"data": [self.fila]})()


class SupabaseFalso:
    def __init__(self): self.tabla = Tabla()
    def table(self, nombre): assert nombre == "canales_empleado"; return self.tabla


def _ctx(admin=True):
    return AuthContext("u-1", "org-1", "Empresa", ["u-1"], admin)


def test_canal_corporativo_nunca_devuelve_tokens():
    sb = SupabaseFalso()
    resultado = crear_canal_correo(sb, _ctx(), direccion_operativa="Compras@Empresa.cl", etiqueta_gmail="Baiyer/Compras")
    assert resultado["direccion_operativa"] == "compras@empresa.cl"
    assert resultado["etiqueta_gmail"] == "Baiyer/Compras"
    assert "access_token" not in resultado
    assert "refresh_token" not in resultado


def test_solo_admin_configura_canal():
    with pytest.raises(HTTPException, match="administrador"):
        crear_canal_correo(SupabaseFalso(), _ctx(admin=False), direccion_operativa="compras@empresa.cl", etiqueta_gmail="Baiyer")


@pytest.mark.parametrize("email", ["", "sin-arroba", "a@b"])
def test_direccion_operativa_se_valida(email):
    with pytest.raises(HTTPException, match="correo válido"):
        crear_canal_correo(SupabaseFalso(), _ctx(), direccion_operativa=email, etiqueta_gmail="Baiyer")
