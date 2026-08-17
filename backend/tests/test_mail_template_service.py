"""Tests del renderer/persistencia de plantillas de correo — DB en memoria,
sin Supabase real."""
import unittest
from unittest.mock import patch

from app.services import mail_template_service as svc
from app.services.mail_events import EVENTOS


class FakeExec:
    def __init__(self, data):
        self.data = data


class FakeQuery:
    """Emula lo suficiente del query builder de supabase-py (select/insert/
    update/eq/is_/order/limit/maybe_single/execute) contra una lista de
    filas en memoria — sin red ni Supabase real."""
    def __init__(self, rows: list):
        self.rows = rows
        self.filters: dict = {}
        self._is_null: set = set()
        self._order = None
        self._desc = False
        self._limit = None
        self._payload = None
        self._mode = "select"
        self._single = False

    def select(self, *_):
        self._mode = "select"
        return self

    def insert(self, payload):
        self._mode = "insert"
        self._payload = payload
        return self

    def update(self, payload):
        self._mode = "update"
        self._payload = payload
        return self

    def eq(self, col, val):
        self.filters[col] = val
        return self

    def is_(self, col, _valor_null):
        self._is_null.add(col)
        return self

    def order(self, col, desc=False):
        self._order = col
        self._desc = desc
        return self

    def limit(self, n):
        self._limit = n
        return self

    def maybe_single(self):
        self._single = True
        return self

    def _filtrar(self):
        out = []
        for r in self.rows:
            ok = all(r.get(c) == v for c, v in self.filters.items())
            ok = ok and all(r.get(c) is None for c in self._is_null)
            if ok:
                out.append(r)
        return out

    def execute(self):
        if self._mode == "insert":
            row = dict(self._payload)
            row.setdefault("id", f"id-{len(self.rows) + 1}")
            self.rows.append(row)
            return FakeExec([row])
        if self._mode == "update":
            matched = self._filtrar()
            for r in matched:
                r.update(self._payload)
            return FakeExec(matched)
        matched = self._filtrar()
        if self._order:
            matched = sorted(matched, key=lambda r: r.get(self._order) or 0, reverse=self._desc)
        if self._limit:
            matched = matched[: self._limit]
        if self._single:
            return FakeExec(matched[0] if matched else None)
        return FakeExec(matched)


class FakeSupabaseDB:
    def __init__(self):
        self._tablas: dict[str, list] = {
            "mail_template_definitions": [], "mail_template_versions": [], "mail_delivery_events": [],
        }

    def table(self, nombre):
        return FakeQuery(self._tablas.setdefault(nombre, []))


class FakeRpcQuery:
    def __init__(self, data):
        self.data = data

    def execute(self):
        return FakeExec(self.data)


class FakeSupabaseConReserva(FakeSupabaseDB):
    def __init__(self):
        super().__init__()
        self.claves_reservadas = set()

    def rpc(self, nombre, params):
        assert nombre == "reserve_mail_delivery_event"
        clave = params["p_idempotency_key"]
        if clave in self.claves_reservadas:
            return FakeRpcQuery([])
        self.claves_reservadas.add(clave)
        row = {
            "id": f"reserva-{len(self.claves_reservadas)}",
            "organizacion_id": params["p_organizacion_id"],
            "evento": params["p_evento"],
            "destinatario_email": params["p_destinatario_email"],
            "idempotency_key": clave,
            "estado": "reservada",
            "reservation_token": params["p_reservation_token"],
        }
        self._tablas["mail_delivery_events"].append(row)
        return FakeRpcQuery([row])


class ExtraerPlaceholdersTest(unittest.TestCase):
    def test_extrae_variables_usadas(self):
        self.assertEqual(svc.extraer_placeholders("Hola {{nombre}}, tu OC {{numero_oc}} llegó"), {"nombre", "numero_oc"})

    def test_texto_sin_placeholders(self):
        self.assertEqual(svc.extraer_placeholders("Texto plano"), set())


class ValidarVariablesTest(unittest.TestCase):
    def test_variable_permitida_no_lanza(self):
        svc.validar_variables("rfq_requested", ["proveedor_nombre", "items"])

    def test_variable_no_permitida_lanza(self):
        with self.assertRaises(ValueError):
            svc.validar_variables("rfq_requested", ["password_secreto"])

    def test_evento_desconocido_lanza(self):
        with self.assertRaises(ValueError):
            svc.validar_variables("evento_inventado", [])


class PreviewTest(unittest.TestCase):
    def test_preview_no_toca_supabase(self):
        with patch("app.services.mail_template_service._sb") as mock_sb:
            resultado = svc.preview("rfq_requested", "Hola {{proveedor_nombre}}", "Cuerpo {{items}}", ["proveedor_nombre", "items"])
        mock_sb.assert_not_called()
        self.assertIn("[proveedor_nombre]", resultado["subject"])
        self.assertTrue(resultado["es_preview"])

    def test_preview_con_placeholder_no_declarado_lanza(self):
        with self.assertRaises(ValueError):
            svc.preview("rfq_requested", "Hola {{proveedor_nombre}}", "{{items}} {{no_declarada}}", ["proveedor_nombre", "items"])


class RenderTest(unittest.TestCase):
    def test_sin_organizacion_usa_default(self):
        resultado = svc.render("rfq_received_thanks", {"proveedor_nombre": "Acme"})
        self.assertEqual(resultado["origen"], "default")
        self.assertIn("Acme", resultado["subject"] + resultado["body"])

    def test_variable_faltante_lanza_antes_de_enviar(self):
        with self.assertRaises(ValueError):
            svc.render("rfq_received_thanks", {})

    def test_evento_desconocido_lanza(self):
        with self.assertRaises(ValueError):
            svc.render("evento_inventado", {})


class GuardarVersionYResolverTest(unittest.TestCase):
    def setUp(self):
        self.fake = FakeSupabaseDB()
        self.patcher = patch("app.services.mail_template_service._sb", return_value=self.fake)
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()

    def test_guardar_crea_definicion_y_version_1(self):
        resultado = svc.guardar_version("org-1", "rfq_requested", "Asunto {{proveedor_nombre}}", "Cuerpo {{items}} {{empresa_nombre}} {{plazo_respuesta}}", ["proveedor_nombre", "items", "empresa_nombre", "plazo_respuesta"], "user-1")
        self.assertEqual(resultado["version"]["version"], 1)
        self.assertEqual(len(self.fake._tablas["mail_template_definitions"]), 1)

    def test_guardar_dos_veces_crea_version_2_sin_borrar_la_1(self):
        svc.guardar_version("org-1", "rfq_received_thanks", "A1", "{{proveedor_nombre}}", ["proveedor_nombre"], "user-1")
        svc.guardar_version("org-1", "rfq_received_thanks", "A2", "{{proveedor_nombre}} v2", ["proveedor_nombre"], "user-1")
        versiones = self.fake._tablas["mail_template_versions"]
        self.assertEqual(len(versiones), 2)
        self.assertEqual({v["version"] for v in versiones}, {1, 2})

    def test_variable_no_declarada_no_se_guarda(self):
        with self.assertRaises(ValueError):
            svc.guardar_version("org-1", "rfq_received_thanks", "A", "{{proveedor_nombre}} {{secreto}}", ["proveedor_nombre"], "user-1")
        self.assertEqual(self.fake._tablas["mail_template_definitions"], [])

    def test_resolver_usa_override_de_organizacion(self):
        svc.guardar_version("org-1", "rfq_received_thanks", "Personalizado", "{{proveedor_nombre}} gracias!", ["proveedor_nombre"], "user-1")
        resultado = svc.render("rfq_received_thanks", {"proveedor_nombre": "Acme"}, organizacion_id="org-1")
        self.assertEqual(resultado["origen"], "organizacion")
        self.assertIn("gracias!", resultado["body"])

    def test_precedencia_nodo_sobre_workflow_sobre_organizacion(self):
        vars_declaradas = ["nombre_autorizador", "nombre_solicitante", "lista_nombre", "monto", "organizacion_nombre", "link_autorizacion"]
        cuerpo = "{{nombre_autorizador}} {{nombre_solicitante}} {{lista_nombre}} {{monto}} {{organizacion_nombre}} {{link_autorizacion}}"
        svc.guardar_version("org-1", "approval_requested", "Org", cuerpo, vars_declaradas, "user-1")
        svc.guardar_version("org-1", "approval_requested", "Workflow", cuerpo, vars_declaradas, "user-1", workflow_id="wf-1")
        svc.guardar_version("org-1", "approval_requested", "Nodo", cuerpo, vars_declaradas, "user-1", workflow_id="wf-1", nodo_id="n1")

        variables = {"nombre_autorizador": "x", "nombre_solicitante": "y", "lista_nombre": "z", "monto": "1", "organizacion_nombre": "o", "link_autorizacion": "l"}
        solo_org = svc.render("approval_requested", variables, organizacion_id="org-1")
        self.assertEqual(solo_org["subject"], "Org")

        con_workflow = svc.render("approval_requested", variables, organizacion_id="org-1", workflow_id="wf-1")
        self.assertEqual(con_workflow["subject"], "Workflow")

        con_nodo = svc.render("approval_requested", variables, organizacion_id="org-1", workflow_id="wf-1", nodo_id="n1")
        self.assertEqual(con_nodo["subject"], "Nodo")

    def test_restaurar_default_crea_version_nueva_no_borra(self):
        svc.guardar_version("org-1", "rfq_received_thanks", "Custom", "{{proveedor_nombre}} custom", ["proveedor_nombre"], "user-1")
        svc.restaurar_default("org-1", "rfq_received_thanks", "user-1")
        versiones = self.fake._tablas["mail_template_versions"]
        self.assertEqual(len(versiones), 2)
        resultado = svc.render("rfq_received_thanks", {"proveedor_nombre": "Acme"}, organizacion_id="org-1")
        self.assertNotIn("custom", resultado["body"])

    def test_listar_plantillas_fusiona_default_y_override(self):
        svc.guardar_version("org-1", "rfq_received_thanks", "Custom", "{{proveedor_nombre}} custom", ["proveedor_nombre"], "user-1")
        listado = svc.listar_plantillas("org-1")
        self.assertEqual(len(listado), len(EVENTOS))
        por_evento = {p["evento"]: p for p in listado}
        self.assertEqual(por_evento["rfq_received_thanks"]["origen"], "organizacion")
        self.assertEqual(por_evento["rfq_requested"]["origen"], "default")

    def test_restaurar_herencia_archiva_override_sin_borrar_versiones(self):
        svc.guardar_version("org-1", "rfq_received_thanks", "Nodo", "{{proveedor_nombre}} nodo", ["proveedor_nombre"], "user-1", workflow_id="wf-1", nodo_id="n1")
        resultado = svc.restaurar_herencia("org-1", "rfq_received_thanks", "wf-1", "n1")
        self.assertTrue(resultado["heredando"])
        definicion = self.fake._tablas["mail_template_definitions"][0]
        self.assertEqual(definicion["estado"], "archivada")
        self.assertEqual(len(self.fake._tablas["mail_template_versions"]), 1)


class RegistrarEnvioTest(unittest.TestCase):
    def setUp(self):
        self.fake = FakeSupabaseDB()
        self.patcher = patch("app.services.mail_template_service._sb", return_value=self.fake)
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()

    def test_reintento_con_misma_clave_no_duplica(self):
        primero = svc.registrar_envio("org-1", "rfq_requested", "prov@x.cl", "clave-1", estado="enviado")
        segundo = svc.registrar_envio("org-1", "rfq_requested", "prov@x.cl", "clave-1", estado="enviado")
        self.assertEqual(primero["id"], segundo["id"])
        self.assertEqual(len(self.fake._tablas["mail_delivery_events"]), 1)


class ReservarEnvioTest(unittest.TestCase):
    def setUp(self):
        self.fake = FakeSupabaseConReserva()
        self.patcher = patch("app.services.mail_template_service._sb", return_value=self.fake)
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()

    def test_solo_el_primer_worker_adquiere_derecho_a_enviar(self):
        primero = svc.reservar_envio("org-1", "rfq_requested", "PROV@X.CL", "clave-reserva")
        segundo = svc.reservar_envio("org-1", "rfq_requested", "prov@x.cl", "clave-reserva")
        self.assertTrue(primero["adquirida"])
        self.assertFalse(segundo["adquirida"])
        self.assertEqual(primero["entrega"]["id"], segundo["entrega"]["id"])
        self.assertEqual(len(self.fake._tablas["mail_delivery_events"]), 1)

    def test_valida_evento_email_y_clave_antes_de_reservar(self):
        with self.assertRaises(ValueError):
            svc.reservar_envio("org-1", "inventado", "prov@x.cl", "k")
        with self.assertRaises(ValueError):
            svc.reservar_envio("org-1", "rfq_requested", "sin-arroba", "k")
        with self.assertRaises(ValueError):
            svc.reservar_envio("org-1", "rfq_requested", "prov@x.cl", "")


if __name__ == "__main__":
    unittest.main()
