"""El invariante de auditoría: `item_field_updates` no puede decir "aplicado"
sobre un dato que no se escribió en `resultados`.

El bug original insertaba la fila ya marcada como aplicada y recién después
escribía el valor; si ese segundo paso fallaba, la auditoría quedaba mintiendo.
Ocurrió con datos reales, así que el caso de fallo es lo que más importa acá.
"""
import unittest

from app.services.item_field_updates import registrar_actualizacion_campo


class FakeQuery:
    def __init__(self, tabla, log, filas_insert):
        self._tabla, self._log, self._filas = tabla, log, filas_insert
        self.data = None

    def insert(self, fila):
        self._log.append(("insert", self._tabla, dict(fila)))
        self.data = self._filas
        return self

    def update(self, cambios):
        self._pendiente = ("update", self._tabla, dict(cambios))
        return self

    def eq(self, campo, valor):
        tipo, tabla, cambios = self._pendiente
        self._pendiente = (tipo, tabla, cambios, campo, valor)
        return self

    def execute(self):
        if getattr(self, "_pendiente", None):
            self._log.append(self._pendiente)
            self._pendiente = None
        return self


class FakeSupabase:
    def __init__(self, filas_insert=None):
        self.log = []
        self._filas = filas_insert if filas_insert is not None else [{"id": "prop-1"}]

    def table(self, nombre):
        return FakeQuery(nombre, self.log, self._filas)

    def estados_marcados(self):
        return [c.get("estado") for t, *r in self.log if t == "update" for c in [r[1]]]


FILA = {"entity_type": "resultado", "entity_id": "res-1", "field": "precio_unitario"}


class RegistrarActualizacionCampoTest(unittest.TestCase):
    def test_sin_auto_aplicar_no_aplica_ni_marca(self):
        sb = FakeSupabase()
        llamadas = []
        registrar_actualizacion_campo(
            sb, FILA, auto_aplicar=False, agente="gmail_agent",
            cuando_iso="2026-08-20T00:00:00Z", aplicar=lambda: llamadas.append("aplicar"),
        )
        self.assertEqual(llamadas, [])
        self.assertEqual([t for t, *_ in sb.log], ["insert"])

    def test_la_fila_nunca_se_inserta_ya_marcada_como_aplicada(self):
        """El estado honesto lo pone el DEFAULT de la tabla ('propuesta')."""
        sb = FakeSupabase()
        registrar_actualizacion_campo(
            sb, FILA, auto_aplicar=True, agente="gmail_agent",
            cuando_iso="2026-08-20T00:00:00Z", aplicar=lambda: None,
        )
        _, _, fila_insertada = sb.log[0]
        self.assertNotIn("estado", fila_insertada)
        self.assertNotIn("reviewed_by", fila_insertada)

    def test_el_orden_es_insertar_aplicar_marcar(self):
        sb = FakeSupabase()
        orden = []
        original_table = sb.table

        def table_espia(nombre):
            orden.append(f"db:{nombre}")
            return original_table(nombre)

        sb.table = table_espia
        registrar_actualizacion_campo(
            sb, FILA, auto_aplicar=True, agente="gmail_agent",
            cuando_iso="2026-08-20T00:00:00Z", aplicar=lambda: orden.append("aplicar"),
        )
        self.assertEqual(orden, ["db:item_field_updates", "aplicar", "db:item_field_updates"])
        self.assertEqual(sb.estados_marcados(), ["aplicado"])

    def test_si_falla_la_escritura_la_fila_no_queda_marcada_como_aplicada(self):
        """El caso que motivó el fix: la auditoría debe quedar en 'propuesta'
        (revisable a mano), nunca afirmando algo que no ocurrió."""
        sb = FakeSupabase()

        def aplicar_falla():
            raise RuntimeError("resultados no se pudo actualizar")

        with self.assertRaises(RuntimeError):
            registrar_actualizacion_campo(
                sb, FILA, auto_aplicar=True, agente="gmail_agent",
                cuando_iso="2026-08-20T00:00:00Z", aplicar=aplicar_falla,
            )

        self.assertEqual([t for t, *_ in sb.log], ["insert"])
        self.assertEqual(sb.estados_marcados(), [])
        # No alcanza con que no haya UPDATE: el bug original venía por el INSERT,
        # que ya traía estado='aplicado'. Sin esta assert, este test pasaba igual
        # con el bug reintroducido (verificado por mutación).
        _, _, fila_insertada = sb.log[0]
        self.assertNotEqual(fila_insertada.get("estado"), "aplicado")

    def test_sin_id_devuelto_no_marca_nada_a_ciegas(self):
        """Marcar sin saber qué fila es reintroduce el problema por otra vía."""
        sb = FakeSupabase(filas_insert=[])
        registrar_actualizacion_campo(
            sb, FILA, auto_aplicar=True, agente="gmail_agent",
            cuando_iso="2026-08-20T00:00:00Z", aplicar=lambda: None,
        )
        self.assertEqual(sb.estados_marcados(), [])

    def test_marca_con_el_agente_recibido(self):
        sb = FakeSupabase()
        registrar_actualizacion_campo(
            sb, FILA, auto_aplicar=True, agente="outlook_agent",
            cuando_iso="2026-08-20T00:00:00Z", aplicar=lambda: None,
        )
        cambios = [r[1] for t, *r in sb.log if t == "update"][0]
        self.assertEqual(cambios["updated_by"], "outlook_agent")
        self.assertEqual(cambios["reviewed_by"], "outlook_agent_auto")


if __name__ == "__main__":
    unittest.main()
