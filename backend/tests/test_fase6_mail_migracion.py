"""Tests de la migración de emisores reales al renderer de plantillas
(Fase 6) — confirman que cada sitio migrado llama a render() con el evento
y las variables correctas, y que el subject/body que sale del renderer es
lo que efectivamente se manda a enviar. Todo mockeado, sin red/Supabase/
Gmail reales."""
import asyncio
import unittest
from unittest.mock import MagicMock, patch


class SeguimientoAutomaticoTest(unittest.TestCase):
    def _conv(self, **overrides):
        base = {
            "id": "conv-1", "user_id": "u-1", "gmail_thread_id": "thread-1",
            "subject": "Cotización", "proveedor_nombre": "Acme", "proveedor_email": "acme@prov.cl",
        }
        base.update(overrides)
        return base

    def _sb_mock(self):
        sb = MagicMock()
        sb.table.return_value.select.return_value.eq.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value.data = []
        return sb

    def test_agradecimiento_usa_evento_rfq_received_thanks(self):
        from app.services import gmail_conversation_agent as agente

        sb = self._sb_mock()
        service = MagicMock()
        conv = self._conv()

        class FakeCtx:
            organizacion_id = "org-1"

        with patch("app.services.mail_template_service.render", return_value={"subject": "x", "body": "Cuerpo renderizado"}) as mock_render, \
             patch("app.services.organizacion.resolver_organizacion", return_value=FakeCtx()), \
             patch("app.services.gmail_service.send_email_threaded", return_value={"id": "msg-1"}) as mock_send, \
             patch("app.services.mail_template_service.registrar_envio") as mock_registrar:
            resultado = agente.seguimiento_automatico(sb, service, conv, "yo@baiyer.cl", set())

        self.assertTrue(resultado)
        mock_render.assert_called_once()
        self.assertEqual(mock_render.call_args.args[0], "rfq_received_thanks")
        self.assertEqual(mock_render.call_args.kwargs["organizacion_id"], "org-1")
        mock_send.assert_called_once()
        self.assertEqual(mock_send.call_args.args[3], "Cuerpo renderizado")
        mock_registrar.assert_called_once()
        self.assertEqual(mock_registrar.call_args.args[1], "rfq_received_thanks")

    def test_pendientes_usa_evento_rfq_missing_information_con_campos(self):
        from app.services import gmail_conversation_agent as agente

        sb = self._sb_mock()
        service = MagicMock()
        conv = self._conv()

        with patch("app.services.mail_template_service.render", return_value={"subject": "x", "body": "y"}) as mock_render, \
             patch("app.services.organizacion.resolver_organizacion", return_value=None), \
             patch("app.services.gmail_service.send_email_threaded", return_value={"id": "msg-2"}):
            agente.seguimiento_automatico(sb, service, conv, "yo@baiyer.cl", {"precio_unitario", "plazo_entrega"})

        self.assertEqual(mock_render.call_args.args[0], "rfq_missing_information")
        variables = mock_render.call_args.args[1]
        self.assertIn("precio unitario", variables["campos_faltantes"])
        self.assertIsNone(mock_render.call_args.kwargs["organizacion_id"])

    def test_render_falla_cae_al_texto_default_sin_romper_el_envio(self):
        from app.services import gmail_conversation_agent as agente

        sb = self._sb_mock()
        service = MagicMock()
        conv = self._conv()

        with patch("app.services.mail_template_service.render", side_effect=Exception("boom")), \
             patch("app.services.organizacion.resolver_organizacion", return_value=None), \
             patch("app.services.gmail_service.send_email_threaded", return_value={"id": "msg-3"}) as mock_send:
            resultado = agente.seguimiento_automatico(sb, service, conv, "yo@baiyer.cl", set())

        self.assertTrue(resultado)
        cuerpo_enviado = mock_send.call_args.args[3]
        self.assertIn("Acme", cuerpo_enviado)


class RecurrenciaRfqTest(unittest.TestCase):
    def test_ejecutar_recurrencia_usa_evento_rfq_requested(self):
        from app.services import recurrencia_service

        rec = {
            "id": "rec-1", "user_id": "u-1", "nombre": "Compra mensual",
            "items": "papel, tóner", "cotizar_antes": True, "activa": True,
            "proveedor_id": "prov-1",
        }

        def table_side_effect(nombre):
            m = MagicMock()
            if nombre == "recurrencias":
                m.select.return_value.eq.return_value.single.return_value.execute.return_value.data = rec
            elif nombre == "proveedores":
                m.select.return_value.eq.return_value.single.return_value.execute.return_value.data = {"nombre": "Acme", "email": "acme@prov.cl"}
            elif nombre == "user_integrations":
                m.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value.data = {
                    "access_token": "a", "refresh_token": "b", "email": "yo@baiyer.cl",
                }
            return m

        sb = MagicMock()
        sb.table.side_effect = table_side_effect

        class FakeCtx:
            organizacion_id = "org-1"

        with patch("app.services.supabase.get_supabase", return_value=sb), \
             patch("app.services.gmail_service.get_gmail_service", return_value=(MagicMock(), MagicMock(token="a"))), \
             patch("app.services.gmail_service.send_email") as mock_send, \
             patch("app.services.mail_template_service.render", return_value={"subject": "Asunto", "body": "Cuerpo"}) as mock_render, \
             patch("app.services.mail_template_service.registrar_envio"), \
             patch("app.services.organizacion.resolver_organizacion", return_value=FakeCtx()), \
             patch("app.services.organizacion.obtener_perfil_organizacion", return_value={"nombre": "Acme Corp"}):
            recurrencia_service.ejecutar_recurrencia("rec-1")

        mock_render.assert_called_once()
        self.assertEqual(mock_render.call_args.args[0], "rfq_requested")
        variables = mock_render.call_args.args[1]
        self.assertEqual(variables["recurrencia_nombre"], "Compra mensual")
        self.assertEqual(variables["empresa_nombre"], "Acme Corp")
        mock_send.assert_called_once()
        self.assertEqual(mock_send.call_args.kwargs["subject"], "Asunto")
        self.assertEqual(mock_send.call_args.kwargs["body"], "Cuerpo")


class ListasAprobacionRequestedTest(unittest.TestCase):
    def test_crear_y_enviar_solicitudes_usa_evento_approval_requested(self):
        from app.routers import listas

        sb = MagicMock()
        sb.table.return_value.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value.data = [
            {"access_token": "a", "refresh_token": "b", "email": "yo@baiyer.cl"}
        ]

        resumen = {"solicitante": "Ana", "empresa": "Acme", "monto_total": 500000, "items": []}
        resolucion = {"responsables_a_notificar": [{"id": "r-1", "nombre": "Pedro", "email": "pedro@acme.cl"}], "nodo_nombre": "jefe directo", "workflow_instance_id": "wi-1", "nodo_id": "n-1"}

        sol_fake = {"id": "sol-1", "token": "tok-1", "magic_link": "https://x/authorize/tok-1", "expira_at": "2026-01-01T00:00:00"}

        with patch("app.routers.aprobaciones._crear_solicitud_aprobacion", return_value=sol_fake), \
             patch("app.services.gmail_service.get_gmail_service", return_value=(MagicMock(), MagicMock(token="a"))), \
             patch("app.services.gmail_service.send_email") as mock_send, \
             patch("app.services.mail_template_service.render", return_value={"subject": "Asunto", "body": "Cuerpo"}) as mock_render, \
             patch("app.services.mail_template_service.registrar_envio") as mock_registrar:
            asyncio.run(listas._crear_y_enviar_solicitudes(
                sb, "u-1", "lista-1", "Compra de insumos", resumen, resolucion, organizacion_id="org-1",
            ))

        mock_render.assert_called_once()
        self.assertEqual(mock_render.call_args.args[0], "approval_requested")
        variables = mock_render.call_args.args[1]
        self.assertEqual(variables["nombre_autorizador"], "Pedro")
        self.assertEqual(variables["lista_nombre"], "Compra de insumos")
        self.assertEqual(variables["nodo_nombre"], "jefe directo")
        mock_send.assert_called_once_with(mock_send.call_args.args[0], "pedro@acme.cl", "Asunto", "Cuerpo", "yo@baiyer.cl")
        mock_registrar.assert_called_once()

    def test_sin_organizacion_id_no_llama_registrar_envio(self):
        from app.routers import listas

        sb = MagicMock()
        sb.table.return_value.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value.data = [
            {"access_token": "a", "refresh_token": "b", "email": "yo@baiyer.cl"}
        ]
        resumen = {"items": []}
        resolucion = {"responsables_a_notificar": [{"id": "r-1", "nombre": "Pedro", "email": "pedro@acme.cl"}], "nodo_nombre": "jefe", "workflow_instance_id": "wi-1", "nodo_id": "n-1"}
        sol_fake = {"id": "sol-1", "token": "tok-1", "magic_link": "https://x/authorize/tok-1", "expira_at": "2026-01-01T00:00:00"}

        with patch("app.routers.aprobaciones._crear_solicitud_aprobacion", return_value=sol_fake), \
             patch("app.services.gmail_service.get_gmail_service", return_value=(MagicMock(), MagicMock(token="a"))), \
             patch("app.services.gmail_service.send_email"), \
             patch("app.services.mail_template_service.render", return_value={"subject": "s", "body": "b"}), \
             patch("app.services.mail_template_service.registrar_envio") as mock_registrar:
            asyncio.run(listas._crear_y_enviar_solicitudes(sb, "u-1", "lista-1", "L", resumen, resolucion))

        mock_registrar.assert_not_called()


if __name__ == "__main__":
    unittest.main()
