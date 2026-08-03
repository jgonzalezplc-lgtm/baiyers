import unittest

from app.services.workflow_engine import (
    evaluar_condicion,
    procesar_evento,
    resolver_autorizadores,
    siguiente_nodo,
    validar_grafo,
)


def _nodo(id_, tipo, **kw):
    return {"id": id_, "tipo": tipo, "nombre": kw.pop("nombre", id_), **kw}


def _conexion(origen, destino, resultado=None):
    c = {"origen_nodo_id": origen, "destino_nodo_id": destino}
    if resultado:
        c["resultado"] = resultado
    return c


class ValidarGrafoTest(unittest.TestCase):
    def test_workflow_valido(self):
        nodos = [
            _nodo("inicio", "inicio"),
            _nodo("cotizar", "tarea_humana", roles=["cotizador"]),
            _nodo("revisar", "revision", roles=["revisor"]),
            _nodo("autorizar", "autorizacion", roles=["autorizador"], resultados=["aprobado", "rechazado"]),
            _nodo("comprar", "emision_oc", roles=["comprador"]),
            _nodo("fin", "fin"),
        ]
        conexiones = [
            _conexion("inicio", "cotizar"),
            _conexion("cotizar", "revisar"),
            _conexion("revisar", "autorizar"),
            _conexion("autorizar", "comprar", "aprobado"),
            _conexion("autorizar", "cotizar", "rechazado"),
            _conexion("comprar", "fin"),
        ]
        self.assertEqual(validar_grafo(nodos, conexiones), [])

    def test_nodo_sin_responsable(self):
        nodos = [
            _nodo("inicio", "inicio"),
            _nodo("revisar", "revision"),  # sin roles ni responsables
            _nodo("fin", "fin"),
        ]
        conexiones = [_conexion("inicio", "revisar"), _conexion("revisar", "fin")]
        errores = validar_grafo(nodos, conexiones)
        self.assertTrue(any(e["codigo"] == "nodo_sin_responsable" for e in errores))

    def test_decision_sin_salida(self):
        nodos = [
            _nodo("inicio", "inicio"),
            _nodo("decidir", "decision", resultados=["si", "no"]),
            _nodo("fin", "fin"),
        ]
        # Solo se conecta la rama "si" — falta "no"
        conexiones = [_conexion("inicio", "decidir"), _conexion("decidir", "fin", "si")]
        errores = validar_grafo(nodos, conexiones)
        self.assertTrue(any(e["codigo"] == "decision_sin_salida" and e["nodo_id"] == "decidir" for e in errores))

    def test_nodo_inaccesible(self):
        nodos = [
            _nodo("inicio", "inicio"),
            _nodo("fin", "fin"),
            _nodo("huerfano", "tarea_humana", roles=["cotizador"]),  # sin conexión de entrada
        ]
        conexiones = [_conexion("inicio", "fin")]
        errores = validar_grafo(nodos, conexiones)
        self.assertTrue(any(e["codigo"] == "nodo_inaccesible" and e["nodo_id"] == "huerfano" for e in errores))

    def test_ciclo_sin_salida(self):
        nodos = [
            _nodo("inicio", "inicio"),
            _nodo("a", "tarea_humana", roles=["cotizador"]),
            _nodo("b", "tarea_humana", roles=["cotizador"]),
            _nodo("fin", "fin"),
        ]
        # a <-> b se llaman entre sí para siempre, nunca llegan a fin
        conexiones = [_conexion("inicio", "a"), _conexion("a", "b"), _conexion("b", "a")]
        errores = validar_grafo(nodos, conexiones)
        self.assertTrue(any(e["codigo"] == "ciclo_sin_salida" for e in errores))

    def test_devolucion_legitima_no_es_ciclo_sin_salida(self):
        """Una devolución para corrección (rechazo vuelve a una etapa anterior,
        pero desde ahí SÍ hay camino de vuelta a fin) es válida."""
        nodos = [
            _nodo("inicio", "inicio"),
            _nodo("cotizar", "tarea_humana", roles=["cotizador"]),
            _nodo("autorizar", "autorizacion", roles=["autorizador"], resultados=["aprobado", "rechazado"]),
            _nodo("fin", "fin"),
        ]
        conexiones = [
            _conexion("inicio", "cotizar"),
            _conexion("cotizar", "autorizar"),
            _conexion("autorizar", "fin", "aprobado"),
            _conexion("autorizar", "cotizar", "rechazado"),  # devolución
        ]
        self.assertEqual(validar_grafo(nodos, conexiones), [])

    def test_un_unico_inicio(self):
        nodos = [_nodo("i1", "inicio"), _nodo("i2", "inicio"), _nodo("fin", "fin")]
        conexiones = [_conexion("i1", "fin"), _conexion("i2", "fin")]
        errores = validar_grafo(nodos, conexiones)
        self.assertTrue(any(e["codigo"] == "inicio_invalido" for e in errores))

    def test_conexion_rota(self):
        nodos = [_nodo("inicio", "inicio"), _nodo("fin", "fin")]
        conexiones = [_conexion("inicio", "no_existe")]
        errores = validar_grafo(nodos, conexiones)
        self.assertTrue(any(e["codigo"] == "conexion_rota" for e in errores))


class SiguienteNodoTest(unittest.TestCase):
    def test_determinista_con_resultado(self):
        conexiones = [
            _conexion("autorizar", "comprar", "aprobado"),
            _conexion("autorizar", "cotizar", "rechazado"),
        ]
        self.assertEqual(siguiente_nodo(conexiones, "autorizar", "aprobado"), "comprar")
        self.assertEqual(siguiente_nodo(conexiones, "autorizar", "rechazado"), "cotizar")
        self.assertIsNone(siguiente_nodo(conexiones, "autorizar", "otro"))

    def test_default_sin_resultado(self):
        conexiones = [_conexion("a", "b")]
        self.assertEqual(siguiente_nodo(conexiones, "a"), "b")


class CondicionesTest(unittest.TestCase):
    def test_regla_por_monto(self):
        regla_jefe = {"campo": "monto_total", "operador": "<=", "valor": 500000}
        regla_finanzas = {"campo": "monto_total", "operador": ">", "valor": 500000}
        self.assertTrue(evaluar_condicion(regla_jefe, {"monto_total": 300000}))
        self.assertFalse(evaluar_condicion(regla_jefe, {"monto_total": 600000}))
        self.assertTrue(evaluar_condicion(regla_finanzas, {"monto_total": 600000}))

    def test_proveedor_nuevo_requiere_homologacion(self):
        condicion = {"campo": "proveedor_homologado", "operador": "==", "valor": False}
        self.assertTrue(evaluar_condicion(condicion, {"proveedor_nuevo": True, "proveedor_homologado": False}))
        self.assertFalse(evaluar_condicion(condicion, {"proveedor_homologado": True}))

    def test_compra_con_oc(self):
        condicion = {"campo": "requiere_oc", "operador": "==", "valor": True}
        self.assertTrue(evaluar_condicion(condicion, {"requiere_oc": True}))

    def test_compra_sin_oc(self):
        condicion = {"campo": "requiere_oc", "operador": "==", "valor": False}
        self.assertTrue(evaluar_condicion(condicion, {"requiere_oc": False}))
        self.assertFalse(evaluar_condicion(condicion, {"requiere_oc": True}))

    def test_condicion_vacia_siempre_verdadera(self):
        self.assertTrue(evaluar_condicion(None, {}))

    def test_campo_o_operador_invalido_no_pasa(self):
        self.assertFalse(evaluar_condicion({"campo": "hackeo", "operador": ">", "valor": 1}, {"hackeo": 999}))
        self.assertFalse(evaluar_condicion({"campo": "monto_total", "operador": "eval", "valor": 1}, {"monto_total": 999}))


class AutorizadoresTest(unittest.TestCase):
    def test_autorizacion_paralela(self):
        nodo = {
            "modo_autorizacion": "paralela",
            "responsables": [{"id": "r1"}, {"id": "r2"}],
        }
        estado = resolver_autorizadores(nodo, {})
        self.assertFalse(estado["resuelto"])
        self.assertCountEqual(estado["pendientes"], ["r1", "r2"])

        estado = resolver_autorizadores(nodo, {"r1": "aprobado", "r2": "aprobado"})
        self.assertTrue(estado["resuelto"])
        self.assertEqual(estado["resultado"], "aprobado")

    def test_autorizacion_paralela_corta_al_primer_rechazo(self):
        nodo = {"modo_autorizacion": "paralela", "responsables": [{"id": "r1"}, {"id": "r2"}]}
        estado = resolver_autorizadores(nodo, {"r1": "rechazado"})
        self.assertTrue(estado["resuelto"])
        self.assertEqual(estado["resultado"], "rechazado")

    def test_autorizacion_secuencial(self):
        nodo = {
            "modo_autorizacion": "secuencial",
            "responsables": [
                {"id": "jefe", "orden_autorizacion": 1},
                {"id": "finanzas", "orden_autorizacion": 2},
            ],
        }
        estado = resolver_autorizadores(nodo, {})
        self.assertEqual(estado["pendientes"], ["jefe"])
        self.assertFalse(estado["resuelto"])

        # Finanzas no puede actuar todavía aunque decida antes que el jefe
        estado = resolver_autorizadores(nodo, {"finanzas": "aprobado"})
        self.assertEqual(estado["pendientes"], ["jefe"])

        estado = resolver_autorizadores(nodo, {"jefe": "aprobado"})
        self.assertEqual(estado["pendientes"], ["finanzas"])

        estado = resolver_autorizadores(nodo, {"jefe": "aprobado", "finanzas": "aprobado"})
        self.assertTrue(estado["resuelto"])
        self.assertEqual(estado["resultado"], "aprobado")


class IdempotenciaTest(unittest.TestCase):
    def test_reintento_idempotente(self):
        procesados: set[str] = set()
        contador = {"n": 0}

        def aplicar():
            contador["n"] += 1
            return contador["n"]

        r1 = procesar_evento(procesados, "evento-1", aplicar)
        r2 = procesar_evento(procesados, "evento-1", aplicar)  # mismo id, reintento
        r3 = procesar_evento(procesados, "evento-2", aplicar)

        self.assertTrue(r1["aplicado"])
        self.assertFalse(r2["aplicado"])
        self.assertTrue(r3["aplicado"])
        self.assertEqual(contador["n"], 2)  # solo evento-1 y evento-2 reales


if __name__ == "__main__":
    unittest.main()
