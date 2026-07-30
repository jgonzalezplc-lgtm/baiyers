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

    def test_pintura_con_supuestos_exige_confirmacion(self):
        datos = {"area": 40, "manos": 2, "rendimiento_m2_l": "no_se", "merma_pct": "no_se", "envase_l": "no_se"}
        r = flujo_determinista("pintar una oficina", datos)
        self.assertEqual(r["estado_flujo"], "requiere_datos")
        self.assertTrue(all(p["es_supuesto"] for p in r["preguntas"]))
        r = flujo_determinista("pintar una oficina", {**datos, "confirmar_rendimiento_m2_l": True, "confirmar_merma_pct": True, "confirmar_envase_l": True})
        self.assertEqual(r["estado_flujo"], "listo")
        self.assertEqual(r["revision_cubicacion"]["items"][0]["cantidad_compra"], 3)

    def test_solar_bloquea_publicacion_y_separa_kw_kwh(self):
        r = flujo_determinista("instalación solar", {"consumo_kwh_mes": 300, "potencia_simultanea_kw": 5, "ubicacion": "Santiago", "orientacion": "sur", "area_techo_m2": 30})
        self.assertEqual(r["estado_flujo"], "requiere_revision")
        self.assertTrue(r["bloquea_publicacion"])
        avisos = " ".join(r["revision_cubicacion"]["advertencias"])
        self.assertIn("kW", avisos); self.assertIn("kWh", avisos); self.assertIn("sur", avisos)


class CubicacionHttpTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app = FastAPI(); app.include_router(router)
        cls.client = TestClient(app)

    def test_endpoint_conserva_estado_estructurado(self):
        primera = self.client.post("/api/identificar", json={"descripcion": "completos para 10 personas", "modo_cubicacion_conversacional": True})
        self.assertEqual(primera.status_code, 200)
        body = primera.json(); self.assertEqual(body["estado_flujo"], "requiere_datos")
        self.assertTrue(all({"id", "texto", "tipo"} <= set(p) for p in body["preguntas"]))
        final = self.client.post("/api/identificar", json={"descripcion": "completos para 10 personas", "modo_cubicacion_conversacional": True,
            "respuestas_cubicacion": {"completos_por_persona": 2, "tipo": "italiano", "veganos": 2, "extras": True}})
        self.assertEqual(final.json()["revision_cubicacion"]["totales"]["completos"], 20)


if __name__ == "__main__":
    unittest.main()
