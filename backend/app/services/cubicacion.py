"""Motor determinista de cubicación.

El LLM puede ayudar a entender lenguaje natural, pero nunca ejecuta las fórmulas ni
decide redondeos comerciales. Las recetas de este módulo son pequeñas, versionadas y
testeables.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any


class ErrorDimensional(ValueError):
    pass


@dataclass(frozen=True)
class Unidad:
    dimension: str
    factor_base: float


UNIDADES = {
    "mm": Unidad("longitud", .001), "cm": Unidad("longitud", .01),
    "m": Unidad("longitud", 1), "km": Unidad("longitud", 1000),
    "cm2": Unidad("area", .0001), "m2": Unidad("area", 1),
    "ml": Unidad("volumen", .001), "L": Unidad("volumen", 1), "m3": Unidad("volumen", 1000),
    "g": Unidad("masa", .001), "kg": Unidad("masa", 1),
    "Wh": Unidad("energia", .001), "kWh": Unidad("energia", 1),
    "W": Unidad("potencia", .001), "kW": Unidad("potencia", 1),
    "min": Unidad("tiempo", 1 / 60), "h": Unidad("tiempo", 1), "día": Unidad("tiempo", 24),
}
CONTEOS = {"persona", "porción", "completo", "unidad", "paquete", "caja", "panel", "plancha", "saco", "rollo"}


def convertir(valor: float, origen: str, destino: str) -> float:
    if not math.isfinite(valor) or abs(valor) > 1e12:
        raise ValueError("valor fuera de rango")
    if origen in CONTEOS or destino in CONTEOS:
        if origen != destino:
            raise ErrorDimensional(f"no se puede convertir {origen} a {destino}")
        return valor
    if origen not in UNIDADES or destino not in UNIDADES:
        raise ValueError("unidad no soportada")
    if UNIDADES[origen].dimension != UNIDADES[destino].dimension:
        raise ErrorDimensional(f"dimensiones incompatibles: {origen} y {destino}")
    return valor * UNIDADES[origen].factor_base / UNIDADES[destino].factor_base


def cantidad_compra(neto: float, merma_pct: float, contenido_envase: float) -> tuple[float, int, float]:
    if not all(math.isfinite(x) and x >= 0 for x in (neto, merma_pct, contenido_envase)) or contenido_envase == 0:
        raise ValueError("cantidades inválidas")
    bruto = neto * (1 + merma_pct / 100)
    envases = math.ceil(bruto / contenido_envase)
    return bruto, envases, envases * contenido_envase


PREGUNTAS_COMPLETOS = [
    {"id": "personas", "texto": "¿Para cuántas personas es?", "tipo": "numero", "unidad": "persona"},
    {"id": "completos_por_persona", "texto": "¿Cuántos completos por persona?", "tipo": "numero", "unidad": "completo"},
    {"id": "tipo", "texto": "¿Italianos, tradicionales u otra variedad?", "tipo": "texto"},
    {"id": "veganos", "texto": "¿Cuántas personas necesitan opción vegana?", "tipo": "numero", "unidad": "persona", "permite_no_se": True},
    {"id": "extras", "texto": "¿Incluimos bebidas y desechables?", "tipo": "booleano"},
]

PREGUNTAS_PINTURA = [
    {"id": "area", "texto": "¿Qué superficie total se pintará?", "tipo": "numero", "unidad": "m2"},
    {"id": "manos", "texto": "¿Cuántas manos de pintura necesitas?", "tipo": "numero", "unidad": "mano"},
    {"id": "rendimiento_m2_l", "texto": "¿Qué rendimiento indica la pintura?", "tipo": "numero", "unidad": "m2/L", "permite_no_se": True},
    {"id": "merma_pct", "texto": "¿Qué porcentaje de merma confirmas?", "tipo": "numero", "unidad": "%", "permite_no_se": True},
    {"id": "envase_l", "texto": "¿Qué tamaño de envase quieres cotizar?", "tipo": "numero", "unidad": "L", "permite_no_se": True},
]

PREGUNTAS_SOLAR = [
    {"id": "consumo_kwh_mes", "texto": "¿Cuál es el consumo mensual de energía?", "tipo": "numero", "unidad": "kWh/mes"},
    {"id": "potencia_simultanea_kw", "texto": "¿Cuál es la potencia máxima usada simultáneamente?", "tipo": "numero", "unidad": "kW", "permite_no_se": True},
    {"id": "ubicacion", "texto": "¿En qué comuna se instalaría?", "tipo": "texto"},
    {"id": "orientacion", "texto": "¿Cuál es la orientación principal del techo?", "tipo": "texto", "permite_no_se": True},
    {"id": "area_techo_m2", "texto": "¿Cuántos m2 útiles de techo hay aproximadamente?", "tipo": "numero", "unidad": "m2", "permite_no_se": True},
]

PREGUNTAS_PARQUE_SOLAR = [
    {"id": "energia_mwh", "texto": "¿Cuál es la energía objetivo en MWh?", "tipo": "numero", "unidad": "MWh"},
    {"id": "tipo_objetivo", "texto": "¿Quisiste decir potencia instalada en MWp, generación objetivo en MWh/año o almacenamiento BESS en MWh?", "tipo": "texto"},
    {"id": "ubicacion", "texto": "¿En qué comuna o coordenadas estará el parque?", "tipo": "texto"},
    {"id": "area_terreno_ha", "texto": "¿Cuántas hectáreas útiles de terreno hay?", "tipo": "numero", "unidad": "ha", "permite_no_se": True},
    {"id": "potencia_interconexion_mw", "texto": "¿Qué potencia admite el punto de conexión?", "tipo": "numero", "unidad": "MW", "permite_no_se": True},
    {"id": "tipo_montaje", "texto": "¿Estructura fija o seguidores solares?", "tipo": "texto", "permite_no_se": True},
]


def detectar_receta(texto: str) -> str | None:
    t = texto.lower()
    if "completo" in t or "hot dog" in t:
        return "completos@1"
    if "pintar" in t or "pintura" in t:
        return "pintura@1"
    if ("solar" in t or "fotovolta" in t) and (re.search(r"\b(parque|planta|central)\b", t) or re.search(r"mwh|mwp", t)):
        return "parque-solar@1"
    if "solar" in t or "paneles fotovolta" in t:
        return "solar-evaluacion@1"
    return None


def extraer_completos(texto: str) -> dict[str, Any]:
    """Extractor conservador: lo dudoso se pregunta, nunca se inventa."""
    t = texto.lower()
    datos: dict[str, Any] = {}
    m = re.search(r"(?:para|somos)\s+(\d+)\s*(?:personas?)?", t)
    if m: datos["personas"] = int(m.group(1))
    m = re.search(r"(\d+)\s+completos?\s+(?:por|cada)\s+persona", t)
    if m: datos["completos_por_persona"] = int(m.group(1))
    if "italiano" in t: datos["tipo"] = "italiano"
    m = re.search(r"(\d+)\s+(?:personas?\s+)?vegan", t)
    if m: datos["veganos"] = int(m.group(1))
    if "con bebidas" in t or "bebidas y desechables" in t: datos["extras"] = True
    return datos


def cubicar_completos(datos: dict[str, Any]) -> dict[str, Any]:
    personas = int(datos["personas"]); por_persona = int(datos["completos_por_persona"])
    veganos_raw = datos.get("veganos", 0)
    veganos = 0 if veganos_raw == "no_se" else int(veganos_raw)
    extras_raw = datos.get("extras", False)
    extras = extras_raw if isinstance(extras_raw, bool) else str(extras_raw).strip().lower() in {"si", "sí", "s", "true", "1", "con", "incluir"}
    total = personas * por_persona
    if personas <= 0 or por_persona <= 0 or not 0 <= veganos <= personas:
        raise ValueError("datos de comensales inválidos")
    vegan = veganos * por_persona; tradicionales = total - vegan
    # Receta completa italiana v1: tomate 70 g, palta útil 80 g, rendimiento palta 70%.
    tomate_kg = total * .070
    palta_neta = total * .080
    palta_bruta = palta_neta / .70
    reserva_pan = math.ceil(total * 1.10)
    items = [
        _item("Pan de completo", reserva_pan, "unidad", 8, "paquete", "consumible", f"{total} × 1,10 reserva = {reserva_pan}; paquetes de 8"),
        _item("Salchicha tradicional", tradicionales, "unidad", 5, "paquete", "consumible", f"{tradicionales} completos tradicionales"),
        _item("Salchicha vegana", vegan, "unidad", 4, "paquete", "consumible", f"{vegan} completos veganos; manipular por separado"),
        _item("Tomate", tomate_kg, "kg", 1, "kg", "consumible", f"{total} × 70 g = {tomate_kg:.2f} kg"),
        _item("Palta", palta_bruta, "kg", 1, "kg", "consumible", f"{total} × 80 g / 70% rendimiento = {palta_bruta:.3f} kg"),
    ]
    if extras:
        items += [_item("Bebida", personas * .5, "L", 1.5, "botella", "consumible", "0,5 L por persona"), _item("Servilletas", total * 2, "unidad", 50, "paquete", "consumible", "2 por completo")]
    return {"receta": "completos@1", "nombre_lista_sugerido": "Completos", "totales": {"completos": total, "tradicionales": tradicionales, "veganos": vegan}, "items": items,
            "supuestos": ["10% de reserva de pan", "palta con 70% de rendimiento útil"], "advertencias": (["Separar utensilios y superficies para las opciones veganas"] if vegan else [])}


def cubicar_pintura(area: float, unidad_area: str, manos: int, rendimiento_m2_l: float, merma_pct: float = 10, envase_l: float = 4) -> dict[str, Any]:
    """Receta pintura@1: (área × manos / rendimiento) + merma."""
    area_m2 = convertir(area, unidad_area, "m2")
    if manos <= 0 or rendimiento_m2_l <= 0:
        raise ValueError("manos y rendimiento deben ser positivos")
    neto = area_m2 * manos / rendimiento_m2_l
    bruto, envases, comercial = cantidad_compra(neto, merma_pct, envase_l)
    return {"receta": "pintura@1", "area_m2": area_m2, "litros_netos": round(neto, 3), "litros_con_merma": round(bruto, 3),
            "envases": envases, "litros_compra": comercial,
            "calculo": f"{area_m2:g} m2 × {manos} manos / {rendimiento_m2_l:g} m2/L + {merma_pct:g}% merma"}


def _item(nombre: str, neto: float, unidad: str, envase: float, unidad_envase: str, categoria: str, calculo: str) -> dict[str, Any]:
    compra = math.ceil(neto / envase)
    return {"nombre_tecnico": nombre, "categoria": categoria, "cantidad_neta": round(neto, 3), "unidad": unidad,
            "cantidad_compra": compra, "unidad_compra": unidad_envase, "contenido_envase": envase,
            "cantidad_comercial": round(compra * envase, 3), "calculo": calculo,
            "terminos_busqueda_es": [nombre], "terminos_busqueda_en": []}


def flujo_determinista(descripcion: str, respuestas: dict[str, Any] | None = None) -> dict[str, Any] | None:
    receta = detectar_receta(descripcion)
    if receta not in {"completos@1", "pintura@1", "solar-evaluacion@1", "parque-solar@1"}:
        return None
    if receta == "pintura@1":
        return _flujo_pintura(respuestas or {})
    if receta == "solar-evaluacion@1":
        return _flujo_solar(respuestas or {})
    if receta == "parque-solar@1":
        return _flujo_parque_solar(descripcion, respuestas or {})
    datos = {**extraer_completos(descripcion), **(respuestas or {})}
    faltantes = [p for p in PREGUNTAS_COMPLETOS if p["id"] not in datos]
    if faltantes:
        return {"estado_flujo": "requiere_datos", "receta": receta, "mensaje": "Confirma estos datos para calcular sin inventar cantidades.",
                "preguntas": faltantes[:3], "datos_confirmados": datos, "lista_items": [], "es_proyecto": True}
    calculo = cubicar_completos(datos)
    items = [{**i, "cantidad": i["cantidad_compra"], "marca": None, "numero_parte": None} for i in calculo["items"] if i["cantidad_compra"] > 0]
    return {"estado_flujo": "listo", "mensaje": None, "preguntas": [], "es_proyecto": True, "confianza": "alto",
            "nombre_lista_sugerido": calculo["nombre_lista_sugerido"], "lista_items": items, "revision_cubicacion": calculo,
            "nombre_tecnico": items[0]["nombre_tecnico"], "marca": None, "numero_parte": None, "categoria": items[0]["categoria"],
            "terminos_busqueda_es": items[0]["terminos_busqueda_es"], "terminos_busqueda_en": []}


def _preguntar(receta: str, preguntas: list[dict[str, Any]], datos: dict[str, Any], mensaje: str) -> dict[str, Any]:
    faltantes = [p for p in preguntas if p["id"] not in datos]
    return {"estado_flujo": "requiere_datos", "receta": receta, "mensaje": mensaje, "preguntas": faltantes[:3],
            "datos_confirmados": datos, "lista_items": [], "es_proyecto": True}


def _flujo_pintura(datos: dict[str, Any]) -> dict[str, Any]:
    faltantes = [p for p in PREGUNTAS_PINTURA if p["id"] not in datos]
    if faltantes:
        return _preguntar("pintura@1", PREGUNTAS_PINTURA, datos, "Necesito superficie, manos y rendimiento para cerrar dimensionalmente el cálculo.")
    # Los valores desconocidos llegan como marcador explícito, nunca como cero silencioso.
    if any(datos.get(k) == "no_se" for k in ("rendimiento_m2_l", "merma_pct", "envase_l")):
        supuestos = {"rendimiento_m2_l": 10, "merma_pct": 10, "envase_l": 4}
        pendientes = [
            {"id": k, "texto": f"¿Confirmas usar {v} { {'rendimiento_m2_l':'m2/L','merma_pct':'%','envase_l':'L'}[k] } como supuesto?", "tipo": "booleano", "es_supuesto": True}
            for k, v in supuestos.items() if datos.get(k) == "no_se" and datos.get(f"confirmar_{k}") is not True
        ]
        if pendientes:
            return {"estado_flujo": "requiere_datos", "receta": "pintura@1", "mensaje": "Estos valores son supuestos propuestos; confírmalos antes de calcular.",
                    "preguntas": [{**p, "id": f"confirmar_{p['id']}"} for p in pendientes[:3]], "datos_confirmados": datos, "lista_items": [], "es_proyecto": True}
        datos = {**datos, **{k: v for k, v in supuestos.items() if datos.get(k) == "no_se"}}
    r = cubicar_pintura(float(datos["area"]), "m2", int(datos["manos"]), float(datos["rendimiento_m2_l"]), float(datos["merma_pct"]), float(datos["envase_l"]))
    item = _item("Pintura", r["litros_con_merma"], "L", float(datos["envase_l"]), "lata", "construccion", r["calculo"])
    revision = {"receta": "pintura@1", "items": [item], "supuestos": [f"Rendimiento {datos['rendimiento_m2_l']} m2/L", f"Merma {datos['merma_pct']}%"], "advertencias": []}
    return _respuesta_lista("Pintura", [item], revision)


def _flujo_solar(datos: dict[str, Any]) -> dict[str, Any]:
    faltantes = [p for p in PREGUNTAS_SOLAR if p["id"] not in datos]
    if faltantes:
        return _preguntar("solar-evaluacion@1", PREGUNTAS_SOLAR, datos, "Para evaluar energía y potencia necesito datos separados; kWh y kW no son intercambiables.")
    consumo = float(datos["consumo_kwh_mes"])
    if not math.isfinite(consumo) or consumo <= 0:
        raise ValueError("el consumo kWh/mes debe ser positivo")
    orientacion = str(datos.get("orientacion", "no_se")).lower()
    avisos = ["La potencia simultánea (kW) debe verificarse con las cargas reales; no se deduce del consumo (kWh).",
              "Requiere inspección eléctrica y estructural en terreno antes de cotizar una solución contractual."]
    if "sur" in orientacion:
        avisos.append("La orientación sur reduce el aprovechamiento solar y requiere revisión especializada.")
    # Dimensionamiento energético preliminar versionado. No sustituye el cálculo
    # eléctrico: 4,5 h solares pico, 80% de rendimiento global y panel de 550 W.
    energia_dia = consumo / 30
    potencia_fv_kwp = energia_dia / (4.5 * .80)
    panel_w = 550
    paneles = math.ceil(potencia_fv_kwp * 1000 / panel_w)
    potencia_instalada_kwp = paneles * panel_w / 1000
    inversor_kw = max(1, math.ceil(potencia_instalada_kwp))
    area_requerida = round(paneles * 2.4, 1)
    area_disponible = datos.get("area_techo_m2")

    items = [
        _item(f"Panel solar fotovoltaico monocristalino {panel_w} W", paneles, "unidad", 1, "unidad", "electrico", f"{consumo:g} kWh/mes ÷ 30 ÷ (4,5 h × 80%) = {potencia_fv_kwp:.2f} kWp; {paneles} paneles de {panel_w} W"),
        _item(f"Inversor solar de aproximadamente {inversor_kw} kW", 1, "unidad", 1, "unidad", "electrico", f"Potencia preliminar del campo: {potencia_instalada_kwp:.2f} kWp; validar por potencia simultánea y diseño de strings"),
        _item("Estructura de montaje para panel solar en techo", paneles, "panel", 1, "panel", "construccion", f"Estructura para {paneles} paneles; fijaciones sujetas al tipo y estado del techo"),
        _item("Kit de protecciones eléctricas fotovoltaicas DC y AC", 1, "unidad", 1, "kit", "electrico", "Un conjunto preliminar; calibres y protecciones dependen del diseño eléctrico"),
        _item("Conectores solares MC4 macho y hembra", paneles, "paquete", 1, "par", "electrico", f"Estimación de un par por panel; validar configuración de strings"),
    ]
    servicio = _item(
        "Servicio de evaluación, diseño e instalación fotovoltaica",
        1, "unidad", 1, "servicio", "servicio",
        f"Evaluación para {consumo:g} kWh/mes en {datos.get('ubicacion')}; dimensionamiento final sujeto a visita técnica",
    )
    servicio["nombre_tecnico"] += " (opcional)"
    servicio["terminos_busqueda_es"] = ["instalación paneles solares hogar", "empresa energía solar fotovoltaica", "diseño sistema solar residencial"]
    servicio["terminos_busqueda_en"] = ["residential solar installation service", "photovoltaic system design"]
    items.append(servicio)
    if isinstance(area_disponible, (int, float)) and area_disponible < area_requerida:
        avisos.append(f"La estimación requiere aproximadamente {area_requerida:g} m2 y declaraste {area_disponible:g} m2 disponibles; se debe ajustar el diseño.")
    avisos.append("Baterías y cableado no se incluyen: requieren autonomía deseada, trazado y distancias reales.")
    revision = {"receta": "solar-evaluacion@1", "items": items,
                "supuestos": ["4,5 horas solares pico", "80% de rendimiento global", f"Paneles de {panel_w} W y 2,4 m2"], "advertencias": avisos,
                "resumen": {"consumo_kwh_mes": consumo, "potencia_simultanea_kw": datos.get("potencia_simultanea_kw"), "ubicacion": datos.get("ubicacion"), "orientacion": datos.get("orientacion"), "area_techo_m2": datos.get("area_techo_m2")}}
    respuesta = _respuesta_lista("Sistema solar fotovoltaico preliminar", items, revision)
    respuesta["mensaje"] = "Lista preliminar de materiales; puedes quitar el servicio opcional. El proveedor deberá validar el diseño final."
    return respuesta


def _flujo_parque_solar(descripcion: str, datos: dict[str, Any]) -> dict[str, Any]:
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*mwh", descripcion.lower())
    energia_mwh = float(m.group(1).replace(",", ".")) if m else None
    datos = {**({"energia_mwh": energia_mwh} if energia_mwh else {}), **datos}
    faltantes = [p for p in PREGUNTAS_PARQUE_SOLAR if p["id"] not in datos]
    if faltantes:
        return _preguntar("parque-solar@1", PREGUNTAS_PARQUE_SOLAR, datos, "Un parque solar se dimensiona por generación, terreno e interconexión; no por superficie u orientación de techo.")

    energia_mwh = float(datos["energia_mwh"])
    alcance = str(datos["tipo_objetivo"]).lower()
    if "almacen" in alcance or "bater" in alcance:
        item = _item(f"Sistema BESS de {energia_mwh:g} MWh", 1, "unidad", 1, "sistema", "electrico", "Capacidad energética declarada; potencia MW, duración, química y conexión requieren ingeniería")
        servicio = _item("Ingeniería y estudio de interconexión para BESS (opcional)", 1, "unidad", 1, "servicio", "servicio", "Definición de potencia, duración, protecciones y conexión")
        revision = {"receta": "parque-solar@1", "items": [item, servicio], "supuestos": [], "advertencias": ["MWh expresa energía almacenada; falta definir potencia MW y horas de descarga."]}
        return _respuesta_lista(f"Sistema de almacenamiento {energia_mwh:g} MWh", [item, servicio], revision)

    potencia_directa = "mwp" in alcance or "potencia" in alcance or "una hora" in alcance or "1 hora" in alcance
    if potencia_directa:
        potencia_mwp = energia_mwh
        energia_dia_mwh = potencia_mwp * 4.5 * .80
    elif "dia" in alcance or "día" in alcance:
        energia_dia_mwh = energia_mwh
    elif "mes" in alcance:
        energia_dia_mwh = energia_mwh / 30
    elif "ano" in alcance or "año" in alcance or "anual" in alcance:
        energia_dia_mwh = energia_mwh / 365
    else:
        return _preguntar("parque-solar@1", [{"id": "tipo_objetivo", "texto": "Indica MWp si es potencia instalada, MWh/año si es generación o MWh BESS si es almacenamiento.", "tipo": "texto"}], {k: v for k, v in datos.items() if k != "tipo_objetivo"}, "Para dimensionar la planta necesito distinguir potencia, generación y almacenamiento.")

    if not potencia_directa:
        potencia_mwp = energia_dia_mwh / (4.5 * .80)
    panel_w = 550
    paneles = math.ceil(potencia_mwp * 1_000_000 / panel_w)
    inversores_100kw = math.ceil(potencia_mwp * 1000 / 100)
    area_estimada_ha = round(potencia_mwp * 1.8, 2)
    items = [
        _item(f"Módulo fotovoltaico bifacial {panel_w} W", paneles, "unidad", 1, "unidad", "electrico", f"{energia_dia_mwh:.3f} MWh/día ÷ (4,5 h × 80%) = {potencia_mwp:.3f} MWp; {paneles} módulos"),
        _item("Inversor string fotovoltaico 100 kW", inversores_100kw, "unidad", 1, "unidad", "electrico", f"{potencia_mwp:.3f} MWp ÷ 0,1 MW por inversor"),
        _item("Estructura de montaje para parque fotovoltaico", paneles, "panel", 1, "panel", "construccion", f"Estructura para {paneles} módulos; tipo final: {datos.get('tipo_montaje')}"),
        _item("Centro de transformación y celdas de media tensión", 1, "unidad", 1, "sistema", "electrico", "Cantidad y tensión sujetas al estudio de interconexión"),
        _item("Sistema SCADA y monitoreo de planta fotovoltaica", 1, "unidad", 1, "sistema", "electronica", "Supervisión, meteorología y comunicaciones de planta"),
        _item("Ingeniería, permisos y estudio de interconexión (opcional)", 1, "unidad", 1, "servicio", "servicio", "Validación eléctrica, civil, ambiental y de conexión"),
    ]
    avisos = ["Dimensionamiento preliminar con 4,5 horas solares pico y 80% de rendimiento global.", "Cableado, obras civiles y subestación se definen con layout y punto de conexión."]
    area = datos.get("area_terreno_ha")
    if area != "no_se" and float(area) < area_estimada_ha:
        avisos.append(f"Se estiman {area_estimada_ha:g} ha y declaraste {float(area):g} ha; revisa potencia o tecnología.")
    revision = {"receta": "parque-solar@1", "items": items, "supuestos": ["4,5 horas solares pico", "80% rendimiento global", "1,8 ha/MWp"], "advertencias": avisos}
    nombre = f"Parque solar {potencia_mwp:g} MWp" if potencia_directa else f"Parque solar para {energia_mwh:g} MWh"
    return _respuesta_lista(nombre, items, revision)


def _respuesta_lista(nombre: str, items_base: list[dict[str, Any]], revision: dict[str, Any]) -> dict[str, Any]:
    items = [{**i, "cantidad": i["cantidad_compra"], "marca": None, "numero_parte": None} for i in items_base]
    return {"estado_flujo": "listo", "mensaje": None, "preguntas": [], "es_proyecto": True, "confianza": "alto", "nombre_lista_sugerido": nombre,
            "lista_items": items, "revision_cubicacion": revision, "nombre_tecnico": items[0]["nombre_tecnico"], "marca": None, "numero_parte": None,
            "categoria": items[0]["categoria"], "terminos_busqueda_es": items[0]["terminos_busqueda_es"], "terminos_busqueda_en": []}
