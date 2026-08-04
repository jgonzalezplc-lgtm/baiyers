"""Tests del resolutor de organización — Fase A.

Sin DB real: se stubbea el cliente Supabase para verificar solo la forma del
contexto que reciben los routers y la política de un-usuario-una-organización.
La lógica de RLS/backfill se prueba manualmente contra producción cuando se
aplica la migración 030.
"""
import unittest
from unittest.mock import patch


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


if __name__ == "__main__":
    unittest.main()
