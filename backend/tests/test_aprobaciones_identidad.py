"""Separación de deberes en el link de autorización.

Regresión de una vulnerabilidad real encontrada en producción el 2026-08-30:
`request_approval` (MCP) devolvía el `magic_link` al propio solicitante, y
`POST /api/aprobaciones/token/{token}/decidir` era público y sólo validaba el
token. El solicitante se autoaprobaba una compra sin ser el autorizador.
"""
import unittest
from unittest.mock import MagicMock, patch

from fastapi import HTTPException

from app.routers.aprobaciones import _solicitud_para_actor
from app.services.auth_context import AuthContext


def ctx(user_id="actor-1", miembros=("actor-1", "solicitante-1")):
    return AuthContext(
        actor_user_id=user_id, organization_id="org-1", organization_nombre="Org",
        user_ids_organizacion=list(miembros), es_admin=False,
    )


def sb_con(solicitud, responsable=None):
    """Supabase falso: `approval_requests` devuelve `solicitud` y
    `responsables` devuelve `responsable` (None = el actor no es el asignado)."""
    sb = MagicMock()

    def table(nombre):
        t = MagicMock()
        if nombre == "approval_requests":
            t.select.return_value.eq.return_value.limit.return_value.execute.return_value = \
                MagicMock(data=[solicitud] if solicitud else [])
        else:
            cadena = t.select.return_value.eq.return_value.eq.return_value.eq.return_value
            cadena.maybe_single.return_value = MagicMock(data=responsable)
        return t

    sb.table.side_effect = table
    return sb


class SolicitudParaActorTest(unittest.TestCase):
    def _llamar(self, solicitud, responsable=None, actor=ctx(), email=None):
        with patch("app.services.supabase.get_supabase", return_value=sb_con(solicitud, responsable)), \
             patch("app.services.supabase.ejecutar_maybe_single", side_effect=lambda q: q), \
             patch("app.routers.aprobaciones.ejecutar_maybe_single", side_effect=lambda q: q), \
             patch("app.routers.aprobaciones._email_del_actor", return_value=email):
            return _solicitud_para_actor("tok", actor)

    def test_solicitante_no_puede_autoaprobarse_con_el_link(self):
        """El caso exacto reportado: tiene el token válido, pero no es el
        responsable asignado. Tener el link ya no alcanza."""
        solicitud = {"id": "a1", "user_id": "solicitante-1", "responsable_id": "resp-1", "estado": "pendiente"}
        with self.assertRaises(HTTPException) as e:
            self._llamar(solicitud, responsable=None)
        self.assertEqual(e.exception.status_code, 403)

    def test_responsable_asignado_si_puede(self):
        solicitud = {"id": "a1", "user_id": "solicitante-1", "responsable_id": "resp-1", "estado": "pendiente"}
        self.assertEqual(self._llamar(solicitud, responsable={"id": "resp-1"})["id"], "a1")

    def test_token_de_otra_organizacion_da_404_no_403(self):
        """Un 403 confirmaría que el token existe."""
        solicitud = {"id": "a1", "user_id": "de-otra-empresa", "responsable_id": "resp-1"}
        with self.assertRaises(HTTPException) as e:
            self._llamar(solicitud)
        self.assertEqual(e.exception.status_code, 404)

    def test_legacy_exige_que_la_sesion_sea_del_correo_autorizador(self):
        solicitud = {"id": "a1", "user_id": "solicitante-1", "responsable_id": None,
                     "aprobador_email": "jefa@acme.cl", "estado": "pendiente"}
        with self.assertRaises(HTTPException) as e:
            self._llamar(solicitud, email="otro@acme.cl")
        self.assertEqual(e.exception.status_code, 403)
        self.assertEqual(self._llamar(solicitud, email="jefa@acme.cl")["id"], "a1")

    def test_legacy_sin_email_autorizador_no_habilita_a_nadie(self):
        """Sin destinatario definido no hay a quién comparar: se deniega,
        no se abre. Un `aprobador_email` vacío no puede ser un comodín."""
        solicitud = {"id": "a1", "user_id": "solicitante-1", "responsable_id": None,
                     "aprobador_email": "", "estado": "pendiente"}
        with self.assertRaises(HTTPException) as e:
            self._llamar(solicitud, email=None)
        self.assertEqual(e.exception.status_code, 403)


class SuperficieDelLinkTest(unittest.TestCase):
    def test_los_endpoints_de_decision_ya_no_son_publicos(self):
        from app.services.tenant_guard import RUTAS_PUBLICAS
        for ruta in RUTAS_PUBLICAS:
            self.assertNotIn("/api/aprobaciones/token/", ruta)

    def test_solicitar_no_devuelve_el_link_ni_el_token(self):
        """Con el token se arma la URL: filtrarlo equivale a filtrar el link."""
        import asyncio
        from app.routers.aprobaciones import SolicitudRequest, solicitar_aprobacion
        sol = {"id": "a1", "token": "secreto", "magic_link": "https://x/authorize/secreto",
               "expira_at": "2026-01-01T00:00:00"}
        with patch("app.routers.aprobaciones._crear_solicitud_aprobacion", return_value=sol):
            res = asyncio.run(solicitar_aprobacion(SolicitudRequest(referencia="lista:1"), ctx()))
        self.assertEqual(set(res), {"id", "expira_at"})
        self.assertNotIn("secreto", str(res))


if __name__ == "__main__":
    unittest.main()
