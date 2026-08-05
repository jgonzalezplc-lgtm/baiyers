"""Tests del resolutor de organización — Fase A.

Sin DB real: se stubbea el cliente Supabase para verificar solo la forma del
contexto que reciben los routers y la política de un-usuario-una-organización.
La lógica de RLS/backfill se prueba manualmente contra producción cuando se
aplica la migración 030.
"""
import unittest
from unittest.mock import MagicMock, patch


class FakeExec:
    def __init__(self, data): self.data = data


class FakeQuery:
    """Encadenable como el builder de supabase-py. `.maybe_single()` marca la
    query como single-row, `.execute()` devuelve `data` según ese modo."""
    def __init__(self, filas):
        self._filas = filas
        self._single = False
    def select(self, *_): return self
    def eq(self, *_): return self
    def maybe_single(self):
        self._single = True
        return self
    def execute(self):
        if self._single:
            return FakeExec(self._filas[0] if self._filas else None)
        return FakeExec(list(self._filas))


class FakeSupabase:
    """Devuelve una FakeQuery distinta según la N-ésima llamada a `.table()`.
    Necesario porque `resolver_organizacion` llama dos veces a
    membresias_organizacion (mi membresía primero, todos los miembros después)."""
    def __init__(self, respuestas_por_tabla):
        self._respuestas = respuestas_por_tabla
        self._contador = {}
    def table(self, nombre):
        self._contador[nombre] = self._contador.get(nombre, 0) + 1
        respuestas = self._respuestas.get(nombre, [])
        idx = min(self._contador[nombre] - 1, len(respuestas) - 1)
        return FakeQuery(respuestas[idx] if respuestas else [])


class ResolverOrganizacionTest(unittest.TestCase):
    def test_usuario_con_organizacion_devuelve_contexto_completo(self):
        fake = FakeSupabase({
            "membresias_organizacion": [
                # 1ª llamada: mi membresía (maybe_single).
                [{
                    "rol": "admin",
                    "organizacion_id": "org-1",
                    "organizaciones": {"id": "org-1", "nombre": "Empresa S.A.", "owner_user_id": "u-owner"},
                }],
                # 2ª llamada: todos los miembros de la organización.
                [{"user_id": "u-owner"}, {"user_id": "u-otro"}],
            ],
        })
        with patch("app.services.organizacion._sb", return_value=fake):
            from app.services.organizacion import resolver_organizacion
            ctx = resolver_organizacion("u-owner")

        self.assertIsNotNone(ctx)
        self.assertEqual(ctx.organizacion_id, "org-1")
        self.assertEqual(ctx.nombre, "Empresa S.A.")
        self.assertEqual(ctx.owner_user_id, "u-owner")
        self.assertEqual(set(ctx.user_ids_miembros), {"u-owner", "u-otro"})
        self.assertEqual(ctx.rol, "admin")
        self.assertTrue(ctx.es_admin)

    def test_usuario_sin_organizacion_devuelve_none(self):
        fake = FakeSupabase({"membresias_organizacion": [[]]})
        with patch("app.services.organizacion._sb", return_value=fake):
            from app.services.organizacion import resolver_organizacion
            self.assertIsNone(resolver_organizacion("u-huerfano"))

    def test_ids_organizacion_incluye_a_todos_los_miembros(self):
        fake = FakeSupabase({
            "membresias_organizacion": [
                [{
                    "rol": "admin",
                    "organizacion_id": "org-1",
                    "organizaciones": {"id": "org-1", "nombre": "X", "owner_user_id": "u-owner"},
                }],
                [{"user_id": "u-owner"}, {"user_id": "u-otro"}, {"user_id": "u-tercero"}],
            ],
        })
        with patch("app.services.organizacion._sb", return_value=fake):
            from app.services.organizacion import ids_organizacion
            ids = ids_organizacion("u-owner")
        self.assertEqual(set(ids), {"u-owner", "u-otro", "u-tercero"})

    def test_ids_organizacion_devuelve_solo_al_usuario_si_no_tiene_org(self):
        """Contrato defensivo: un fallo del resolutor NUNCA amplía visibilidad.
        Aunque no haya organización, la lista incluye al menos al propio usuario,
        preservando el comportamiento pre-Fase B."""
        fake = FakeSupabase({"membresias_organizacion": [[]]})
        with patch("app.services.organizacion._sb", return_value=fake):
            from app.services.organizacion import ids_organizacion
            ids = ids_organizacion("u-huerfano")
        self.assertEqual(ids, ["u-huerfano"])

    def test_miembro_normal_no_es_admin(self):
        fake = FakeSupabase({
            "membresias_organizacion": [
                [{
                    "rol": "miembro",
                    "organizacion_id": "org-1",
                    "organizaciones": {"id": "org-1", "nombre": "X", "owner_user_id": "u-owner"},
                }],
                [{"user_id": "u-owner"}, {"user_id": "u-invitado"}],
            ],
        })
        with patch("app.services.organizacion._sb", return_value=fake):
            from app.services.organizacion import resolver_organizacion
            ctx = resolver_organizacion("u-invitado")
        self.assertEqual(ctx.rol, "miembro")
        self.assertFalse(ctx.es_admin)


class SincronizarMembresiaCapoTest(unittest.TestCase):
    """El puente hacia el modelo de CAPO (`organizations`, migración 028)
    solo sincronizaba en el sentido CAPO → Baiyer. Esto prueba el sentido
    que faltaba: invitar desde Baiyer (Fase C) también debe reflejarse en
    `organization_memberships` cuando el dueño de la organización ya tiene
    fila en CAPO — y no debe lanzar si todavía no la tiene."""

    def test_sin_fila_capo_no_hace_nada_ni_lanza(self):
        from app.services.organizacion import _sincronizar_membresia_capo
        sb = MagicMock()
        sb.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = []
        _sincronizar_membresia_capo(sb, "org-1", "u-owner", "u-invitado", "miembro")
        # Solo se consultó organizations por slug — nunca se llegó a escribir.
        sb.table.assert_any_call("organizations")
        insert_calls = [c for c in sb.table.return_value.insert.call_args_list]
        self.assertEqual(insert_calls, [])

    def test_con_fila_capo_crea_membresia_nueva(self):
        from app.services.organizacion import _sincronizar_membresia_capo

        def table_side_effect(nombre):
            m = MagicMock()
            if nombre == "organizations":
                m.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = [{"id": "org-capo-1"}]
            elif nombre == "organization_memberships":
                # primero el UPDATE de "sacar de otras orgs", luego el SELECT
                # "existente" (vacío → debe insertar).
                m.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value.data = []
            return m

        sb = MagicMock()
        sb.table.side_effect = table_side_effect
        _sincronizar_membresia_capo(sb, "org-1", "u-owner", "u-invitado", "admin")

        memberships_mock = [c for c in sb.table.call_args_list if c.args == ("organization_memberships",)]
        self.assertTrue(len(memberships_mock) >= 1)

    def test_fallo_interno_no_lanza(self):
        """Nunca debe tumbar la invitación real, que ya quedó confirmada
        antes de llamar a esta función."""
        from app.services.organizacion import _sincronizar_membresia_capo
        sb = MagicMock()
        sb.table.side_effect = Exception("boom")
        try:
            _sincronizar_membresia_capo(sb, "org-1", "u-owner", "u-invitado", "miembro")
        except Exception:
            self.fail("_sincronizar_membresia_capo no debe propagar excepciones")


if __name__ == "__main__":
    unittest.main()
