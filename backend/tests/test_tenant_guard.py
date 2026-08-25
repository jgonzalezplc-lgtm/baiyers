"""El guardia deny-by-default no puede erosionarse en silencio.

Estos tests son el mecanismo real: si alguien agrega un endpoint sin
`Depends(get_auth_context)` y sin declararlo en `tenant_guard`, falla acá y no
en producción con datos de un cliente.
"""
import asyncio

import pytest
from fastapi import HTTPException

from app.main import app
from app.services.tenant_guard import (
    DEUDA_SIN_AUTENTICAR,
    RUTAS_PUBLICAS,
    exigir_sesion,
    rutas_desprotegidas,
)


def test_ninguna_ruta_queda_abierta_sin_declararla():
    """Toda ruta /api sin AuthContext tiene que estar explícitamente en una de
    las dos listas. Una ruta nueva y abierta rompe este test."""
    declaradas = RUTAS_PUBLICAS | DEUDA_SIN_AUTENTICAR
    abiertas = set(rutas_desprotegidas(app))
    no_declaradas = abiertas - declaradas
    assert not no_declaradas, (
        "Estos endpoints no exigen sesión y no están declarados en tenant_guard. "
        "Agregales Depends(get_auth_context) — no los agregues a la allowlist:\n  "
        + "\n  ".join(sorted(no_declaradas))
    )


def test_las_listas_no_tienen_entradas_muertas():
    """Una entrada que ya no corresponde a ninguna ruta abierta es basura que
    hace parecer el problema más grande de lo que es (o, peor, tapa que la
    ruta se renombró y quedó abierta con otro nombre)."""
    abiertas = set(rutas_desprotegidas(app))
    sobrantes = (RUTAS_PUBLICAS | DEUDA_SIN_AUTENTICAR) - abiertas
    assert not sobrantes, (
        "Entradas de tenant_guard que ya no corresponden a ninguna ruta abierta:\n  "
        + "\n  ".join(sorted(sobrantes))
    )


def test_la_deuda_solo_puede_achicarse():
    """Candado contra el modo más probable de que esto se pudra: que alguien
    'arregle' un 401 agregando la ruta a la deuda en vez de autenticarla."""
    assert len(DEUDA_SIN_AUTENTICAR) <= 0, (
        "La deuda de endpoints sin autenticar creció. Un endpoint nuevo se "
        "escribe con Depends(get_auth_context); esta lista sólo se achica."
    )


def _request(metodo: str, plantilla: str, headers: dict | None = None):
    """Request mínimo con la ruta ya resuelta, que es lo que el guardia lee."""
    class _Ruta:
        path = plantilla

    class _Estado:
        pass

    class _Request:
        method = metodo
        scope = {"route": _Ruta()}
        state = _Estado()

        def __init__(self):
            self.headers = headers or {}

        @property
        def url(self):
            class _U:
                path = plantilla
            return _U()

    return _Request()


def test_ruta_no_declarada_sin_token_es_401():
    with pytest.raises(HTTPException) as exc:
        asyncio.run(exigir_sesion(_request("GET", "/api/inventario/saldos")))
    assert exc.value.status_code == 401


def test_ruta_publica_pasa_sin_token():
    asyncio.run(exigir_sesion(_request("GET", "/api/health")))


def test_preflight_cors_pasa():
    asyncio.run(exigir_sesion(_request("OPTIONS", "/api/listas")))


def test_la_plantilla_no_se_puede_falsificar_desde_la_url():
    """`/api/health` está permitida; `/api/proyectos/health` no debe colarse
    por parecerse. El guardia usa la plantilla resuelta por el router, no el
    path crudo."""
    with pytest.raises(HTTPException) as exc:
        asyncio.run(exigir_sesion(_request("GET", "/api/proyectos/health")))
    assert exc.value.status_code == 401


def test_prefijo_con_guardia_propio_pasa_sin_token():
    """`/api/v1/cotizar` se autentica con su api_key, no con sesión web."""
    asyncio.run(exigir_sesion(_request("POST", "/api/v1/cotizar")))


def test_emitir_api_key_exige_sesion_pese_a_estar_bajo_api_v1():
    """Los tres endpoints de `/api/v1/keys` son los que EMITEN la api_key, así
    que no pueden autenticarse con ella. La exención por prefijo los dejaba sin
    ninguna capa: la identidad salía del header `X-Claria-User-Id` sin
    verificar, y con el UUID de otro usuario se emitía una key contra su
    organización eligiendo el plan por `X-Claria-User-Plan`."""
    for metodo, plantilla in (
        ("POST", "/api/v1/keys"),
        ("GET", "/api/v1/keys"),
        ("DELETE", "/api/v1/keys/{key_id}"),
    ):
        with pytest.raises(HTTPException) as exc:
            asyncio.run(exigir_sesion(_request(metodo, plantilla)))
        assert exc.value.status_code == 401, f"{metodo} {plantilla} quedó abierto"
