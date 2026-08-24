import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.routers.identificar import router

from app.services.cubicacion import (
    ErrorDimensional,
    cantidad_compra,
    convertir,
    cubicar_completos,
    cubicar_pintura,
    flujo_determinista,
)


class CubicacionTest(unittest.TestCase):
    def test_conversiones_y_dimensiones(self):
        self.assertEqual(convertir(1000, "mm", "m"), 1)
        self.assertEqual(convertir(1000, "Wh", "kWh"), 1)
        with self.assertRaises(ErrorDimensional):
            convertir(1, "m", "L")
        with self.assertRaises(ErrorDimensional):
            convertir(1, "kW", "kWh")

    def test_redondeo_comercial(self):
        self.assertEqual(cantidad_compra(22, 0, 8), (22, 3, 24))

    def test_receta_tecnica_pintura(self):
        r = cubicar_pintura(40, "m2", 2, 10, 10, 4)
        self.assertEqual(r["litros_netos"], 8)
        self.assertEqual((r["envases"], r["litros_compra"]), (3, 12))
        with self.assertRaises(ErrorDimensional):
            cubicar_pintura(40, "m", 2, 10)

    def test_pregunta_maximo_tres_y_no_repregunta(self):
        primero = flujo_determinista("completos para 10 personas")
        self.assertEqual(primero["estado_flujo"], "requiere_datos")
        self.assertLessEqual(len(primero["preguntas"]), 3)
        self.assertNotIn("personas", [p["id"] for p in primero["preguntas"]])

    def test_completos_italianos(self):
        resultado = cubicar_completos({"personas": 10, "completos_por_persona": 2, "tipo": "italiano", "veganos": 2, "extras": True})
        self.assertEqual(resultado["totales"], {"completos": 20, "tradicionales": 16, "veganos": 4})
        tomate = next(i for i in resultado["items"] if i["nombre_tecnico"] == "Tomate")
        palta = next(i for i in resultado["items"] if i["nombre_tecnico"] == "Palta")
        pan = next(i for i in resultado["items"] if i["nombre_tecnico"] == "Pan de completo")
        self.assertEqual(tomate["cantidad_neta"], 1.4)
        self.assertAlmostEqual(palta["cantidad_neta"], 2.286, places=3)
        self.assertEqual((pan["cantidad_compra"], pan["cantidad_comercial"]), (3, 24))

    def test_no_lo_se_no_rompe_completos(self):
        resultado = cubicar_completos({"personas": "10", "completos_por_persona": "2", "tipo": "italiano", "veganos": "no_se", "extras": "no"})
        self.assertEqual(resultado["totales"]["veganos"], 0)
        self.assertFalse(any(i["nombre_tecnico"] == "Bebida" for i in resultado["items"]))

    def test_pintura_con_supuestos_exige_confirmacion(self):
        datos = {"area": 40, "manos": 2, "rendimiento_m2_l": "no_se", "merma_pct": "no_se", "envase_l": "no_se"}
        r = flujo_determinista("pintar una oficina", datos)
        self.assertEqual(r["estado_flujo"], "requiere_datos")
        self.assertTrue(all(p["es_supuesto"] for p in r["preguntas"]))
        r = flujo_determinista("pintar una oficina", {**datos, "confirmar_rendimiento_m2_l": True, "confirmar_merma_pct": True, "confirmar_envase_l": True})
        self.assertEqual(r["estado_flujo"], "listo")
        self.assertEqual(r["revision_cubicacion"]["items"][0]["cantidad_compra"], 3)

    def test_solar_advierte_pero_permite_cotizar_servicio(self):
        r = flujo_determinista("instalación solar", {"consumo_kwh_mes": 300, "potencia_simultanea_kw": 5, "ubicacion": "Santiago", "orientacion": "sur", "area_techo_m2": 30})
        self.assertEqual(r["estado_flujo"], "listo")
        self.assertNotIn("bloquea_publicacion", r)
        self.assertEqual(len(r["lista_items"]), 6)
        self.assertEqual(r["lista_items"][0]["categoria"], "electrico")
        self.assertIn("550 W", r["lista_items"][0]["nombre_tecnico"])
        self.assertIn("opcional", r["lista_items"][-1]["nombre_tecnico"])
        self.assertEqual(r["lista_items"][-1]["categoria"], "servicio")
        avisos = " ".join(r["revision_cubicacion"]["advertencias"])
        self.assertIn("kW", avisos); self.assertIn("kWh", avisos); self.assertIn("sur", avisos)

    def test_parque_solar_no_pregunta_por_techo(self):
        r = flujo_determinista("parque solar de 3MWh")
        self.assertEqual(r["receta"], "parque-solar@1")
        textos = " ".join(p["texto"].lower() for p in r["preguntas"])
        self.assertNotIn("techo", textos)
        self.assertIn("mwp", textos)
        self.assertIn("bess", textos)

    def test_parque_solar_genera_lista_utility_scale(self):
        r = flujo_determinista("parque solar de 3MWh", {"tipo_objetivo": "generación diaria", "ubicacion": "Copiapó", "area_terreno_ha": 2,
            "potencia_interconexion_mw": "no_se", "tipo_montaje": "seguidores"})
        self.assertEqual(r["estado_flujo"], "listo")
        self.assertGreater(r["lista_items"][0]["cantidad"], 1000)
        self.assertTrue(any("SCADA" in i["nombre_tecnico"] for i in r["lista_items"]))
        self.assertFalse(any("techo" in i["nombre_tecnico"].lower() for i in r["lista_items"]))

    def test_parque_solar_mwp_dimensiona_por_potencia(self):
        r = flujo_determinista("parque solar de 3MWh", {"tipo_objetivo": "quise decir 3 MWp de potencia instalada", "ubicacion": "Copiapó", "area_terreno_ha": 6,
            "potencia_interconexion_mw": 3, "tipo_montaje": "seguidores"})
        self.assertEqual(r["nombre_lista_sugerido"], "Parque solar 3 MWp")
        self.assertEqual(r["lista_items"][0]["cantidad"], 5455)


class CubicacionHttpTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from app.services.auth_context import AuthContext, get_auth_context

        app = FastAPI(); app.include_router(router)
        # `/api/identificar` exige sesión desde que se cerró el borde HTTP.
        # Acá se prueba la cubicación, no la autenticación: se inyecta un actor
        # fijo en vez de aflojar el endpoint.
        app.dependency_overrides[get_auth_context] = lambda: AuthContext(
            actor_user_id="test-user", organization_id="test-org",
            organization_nombre="Test", user_ids_organizacion=["test-user"],
            es_admin=True,
        )
        cls.client = TestClient(app)

    def test_endpoint_conserva_estado_estructurado(self):
        primera = self.client.post("/api/identificar", json={"descripcion": "completos para 10 personas", "modo_cubicacion_conversacional": True})
        self.assertEqual(primera.status_code, 200)
        body = primera.json(); self.assertEqual(body["estado_flujo"], "requiere_datos")
        self.assertTrue(all({"id", "texto", "tipo"} <= set(p) for p in body["preguntas"]))
        final = self.client.post("/api/identificar", json={"descripcion": "completos para 10 personas", "modo_cubicacion_conversacional": True,
            "respuestas_cubicacion": {"completos_por_persona": 2, "tipo": "italiano", "veganos": 2, "extras": True}})
        self.assertEqual(final.json()["revision_cubicacion"]["totales"]["completos"], 20)

    def test_endpoint_solar_no_expone_servicios_generados(self):
        res = self.client.post("/api/identificar", json={"descripcion": "parque solar de 3MWh", "modo_cubicacion_conversacional": True,
            "respuestas_cubicacion": {"tipo_objetivo": "3 MWp", "ubicacion": "Copiapó", "area_terreno_ha": 6, "potencia_interconexion_mw": 3, "tipo_montaje": "fijo"}})
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertTrue(body["lista_items"])
        self.assertFalse(any(i["categoria"] == "servicio" for i in body["lista_items"]))
        self.assertFalse(any(i["categoria"] == "servicio" for i in body["revision_cubicacion"]["items"]))


if __name__ == "__main__":
    unittest.main()
