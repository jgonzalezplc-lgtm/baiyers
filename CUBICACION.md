# CUBICACIÓN — Motor de cantidades para Baiyer

## Objetivo

Convertir antecedentes de un proyecto (descripción, planos, planillas o mediciones) en una
lista de materiales cuantificada, verificable y lista para cotizar en Baiyer.

Una cubicación no debe ser solo una lista generada por IA. Cada cantidad debe conservar:

- su origen;
- la fórmula o regla de cálculo;
- la unidad base y sus conversiones;
- la merma aplicada;
- los supuestos;
- el nivel de confianza;
- la posibilidad de revisión humana.

## Motores de cubicación posibles

### 1. Motor paramétrico basado en reglas

Calcula cantidades desde dimensiones y parámetros ingresados por el usuario. Es la primera
opción recomendada para Baiyer porque es determinística, auditable y fácil de probar.

Ejemplos:

- hormigón: `largo × ancho × espesor`;
- revestimiento: `área de muros − vanos`;
- pintura: `área × manos / rendimiento`;
- perfiles: `longitud total / largo comercial`, redondeado hacia arriba;
- tornillos: `puntos de fijación × unidades por punto`;
- cable: `longitud de recorrido × conductores × factor de holgura`.

### 2. Motor de recetas o assemblies

Una partida se descompone en insumos mediante una receta versionada. Sirve para soluciones
repetibles como tabiques, radieres, techumbres, canalizaciones o redes de agua.

Ejemplo: un tabique por m² puede generar placas, montantes, canales, aislación, tornillos y
cinta, cada uno con su coeficiente y merma.

### 3. Motor desde planillas

Importa Excel/CSV, detecta columnas, normaliza nombres y unidades y conserva la fila de
origen. Baiyer ya tiene un prototipo en `POST /api/proyectos/parsear-cubicacion`, pero debe
evolucionar desde extracción con Gemini hacia importación validada y trazable.

### 4. Motor desde planos 2D

Extrae escalas, recintos, longitudes, áreas, símbolos y conteos desde PDF/DWG. Requiere una
etapa de calibración y confirmación visual; la IA puede proponer mediciones, pero no debería
aprobarlas silenciosamente.

### 5. Motor BIM/QTO

Lee cantidades y propiedades desde IFC/Revit: volúmenes, áreas, longitudes, familias y
clasificaciones. Es potente cuando el modelo está bien construido, pero depende de la
calidad y nivel de desarrollo del BIM.

### 6. Motor de estimación por IA

Descompone una descripción o imagen en materiales y propone cantidades. Baiyer ya hace una
versión básica en `/api/identificar`. Debe usarse para borradores o para completar datos,
marcando siempre supuestos y confianza; no como fuente única de una cubicación contractual.

### Recomendación para Baiyer

Usar un motor híbrido:

1. IA para interpretar el proyecto y elegir una plantilla o receta.
2. Reglas determinísticas para calcular cantidades.
3. Catálogo para convertir la cantidad técnica a formatos comerciales.
4. Validaciones automáticas y revisión humana.
5. El sistema de listas (`listas.py`) para buscar proveedores y cotizar cada ítem aprobado.

## Contrato mínimo de una cubicación

```json
{
  "proyecto": "Radier bodega",
  "version": 1,
  "estado": "borrador",
  "moneda": "CLP",
  "supuestos_generales": [],
  "items": [
    {
      "codigo": "HOR-001",
      "partida": "Radier",
      "item": "Hormigón premezclado H25",
      "categoria": "construccion",
      "cantidad_neta": 12.0,
      "unidad_base": "m3",
      "merma_pct": 5,
      "cantidad_compra": 12.6,
      "unidad_compra": "m3",
      "redondeo": "proveedor",
      "formula": "largo * ancho * espesor",
      "variables": {"largo_m": 20, "ancho_m": 4, "espesor_m": 0.15},
      "origen": {"tipo": "entrada_usuario", "referencia": null},
      "supuestos": ["espesor uniforme"],
      "confianza": "alta",
      "requiere_revision": false
    }
  ]
}
```

## Flujo propuesto

1. **Ingreso:** texto, formulario, Excel/CSV, plano o modelo BIM.
2. **Clasificación:** tipo de proyecto, disciplina, partidas y sistema constructivo.
3. **Datos faltantes:** pedir solo dimensiones o decisiones que cambian materialmente el
   resultado.
4. **Cálculo neto:** ejecutar fórmulas y recetas versionadas.
5. **Compra:** aplicar merma, conversión a formatos comerciales y redondeo.
6. **Validación:** unidades compatibles, cantidades positivas, duplicados, rangos y balance
   entre partidas.
7. **Revisión:** presentar fórmula, origen, supuestos y alertas al usuario.
8. **Publicación:** crear las cotizaciones individuales y agruparlas mediante el sistema real
   de listas de Baiyer.

### Comportamiento en “Nueva cotización”

El chat debe decidir entre dos rutas antes de mostrar resultados:

- **Ítem o lista explícita:** si existen especificación y cantidades suficientes, identifica y
  continúa directamente.
- **Proyecto a cubicar:** si faltan variables críticas, responde `requiere_datos`, formula como
  máximo tres preguntas concretas y espera. Puede repetir este ciclo. Solo responde `listo` y
  genera materiales cuando tiene datos suficientes o supuestos confirmados por el usuario.

Ejemplo:

```text
Usuario: Quiero construir una bodega de 20 m².
Baiyer: ¿Qué dimensiones tendrá? ¿Qué altura tendrán los muros? ¿La estructura será de
        madera o perfiles metálicos?
Usuario: 5 × 4 m, 2,4 m de alto y perfiles metálicos.
Baiyer: ¿Qué revestimiento y tipo de cubierta utilizarás?
Usuario: Planchas OSB y techo de zinc.
Baiyer: [calcula y presenta la cubicación revisable]
```

## Reglas obligatorias

- Guardar cantidades como números, nunca dentro de texto.
- Separar `cantidad_neta` de `cantidad_compra`.
- No mezclar unidad técnica y unidad comercial.
- Toda conversión debe indicar su factor y fuente.
- Toda merma debe ser explícita y editable.
- Redondear al formato comercial solo al final.
- Una edición de reglas o coeficientes crea una nueva versión.
- Un dato inferido por IA debe llevar confianza y supuesto.
- Si falta una dimensión crítica, el motor debe detener esa partida o marcarla para revisión.
- Nunca reemplazar una cantidad confirmada por una inferencia sin autorización.

## Análisis dimensional obligatorio

El motor debe tratar cada cálculo como una ecuación con unidades, no como una operación entre
números sueltos. Una cantidad solo es válida si las unidades de entrada se cancelan o
transforman correctamente hasta producir la unidad declarada de salida.

### Cadena de cálculo

Cada ítem debe separar y conservar estas etapas:

1. **Unidad impulsora:** personas, m² de muro, metros de recorrido, horas de autonomía, etc.
2. **Coeficiente de consumo:** unidades/persona, kg/m², L/h, tornillos/placa, etc.
3. **Cantidad neta:** necesidad física antes de pérdidas.
4. **Rendimiento útil:** fracción aprovechable después de cáscara, cortes, traslapos o
   eficiencia técnica.
5. **Merma o reserva:** porcentaje adicional explícito.
6. **Conversión comercial:** unidades por paquete, kg por saco, m² por plancha, litros por
   envase, etc.
7. **Redondeo de compra:** normalmente hacia arriba al múltiplo comercial disponible.

Fórmula general:

```text
cantidad_neta = unidad_impulsora × coeficiente_consumo
cantidad_bruta = cantidad_neta / rendimiento_util
cantidad_con_merma = cantidad_bruta × (1 + merma_pct / 100)
envases_compra = techo(cantidad_con_merma / contenido_por_envase)
cantidad_compra = envases_compra × contenido_por_envase
```

No se deben aplicar simultáneamente `rendimiento_util` y `merma_pct` para representar la
misma pérdida.

### Ejemplos de cancelación de unidades

Hormigón:

```text
20 m × 4 m × 0,15 m = 12 m³
```

Pintura:

```text
80 m² × 2 manos ÷ 10 m²/L = 16 L
```

Completos:

```text
10 personas × 2 completos/persona = 20 completos
20 completos × 70 g tomate/completo = 1.400 g = 1,4 kg de tomate neto
```

Palta con rendimiento comestible de 70%:

```text
20 completos × 80 g pulpa/completo = 1.600 g de pulpa
1.600 g ÷ 0,70 = 2.286 g = 2,286 kg de palta bruta
```

Compra en paquetes:

```text
20 panes requeridos × 1,10 de reserva = 22 panes
techo(22 panes ÷ 8 panes/paquete) = 3 paquetes
3 paquetes × 8 panes/paquete = 24 panes comprados
```

### Conversión y normalización de unidades

- Mantener una unidad canónica por dimensión: longitud (`m`), área (`m2`), volumen (`m3`),
  masa (`kg`), líquido (`L`), energía (`kWh`), potencia (`kW`), tiempo (`h`) y conteo (`unidad`).
- Convertir a la unidad canónica antes de calcular: `15 cm = 0,15 m`, `1.400 g = 1,4 kg`.
- No confundir magnitudes: `kW` no es intercambiable con `kWh`; `m` no es `m²`; peso bruto
  no es peso neto; una persona no es una porción.
- Los coeficientes deben incluir numerador y denominador (`g/completo`, `L/persona`, `m²/L`).
- Las unidades libres escritas por el usuario deben normalizarse, conservando también el
  texto original para auditoría.

### Rendimientos y cobertura

El modelo puede proponer un rendimiento solo cuando:

- está definido por una receta versionada o una fuente identificable; o
- se presenta como supuesto explícito y el usuario lo confirma.

El rendimiento debe guardarse como factor entre 0 y 1. La cobertura comercial debe guardarse
por separado, por ejemplo `12 m2/panel` o `8 unidades/paquete`.

### Reglas de redondeo

- Material continuo vendido a granel: conservar decimales admitidos por el proveedor.
- Unidades indivisibles: redondear hacia arriba al entero.
- Paquetes, cajas, rollos, planchas y sacos: redondear hacia arriba al múltiplo comercial.
- Mostrar siempre la diferencia entre necesidad calculada y compra resultante.
- Nunca redondear resultados intermedios; redondear únicamente la compra final.

### Validación dimensional automática

Antes de aceptar un ítem, el motor debe comprobar:

- que todas las variables poseen valor y unidad;
- que la ecuación produce la misma dimensión que `unidad_base`;
- que toda conversión declara factor, unidad de origen y unidad de destino;
- que los denominadores no son cero y los rendimientos están entre 0 y 1;
- que la cantidad comercial cubre la cantidad requerida;
- que el redondeo corresponde al formato de venta;
- que no se mezclan consumos por persona, por porción o por evento sin conversión explícita.

Si una ecuación no cierra dimensionalmente, el ítem debe quedar en `requiere_revision`; el
modelo no puede corregirlo inventando una unidad.

### Datos adicionales por ítem

Además del contrato mínimo, un cálculo completo puede incorporar:

```json
{
  "dimension": "masa",
  "unidad_impulsora": {"valor": 20, "unidad": "completo"},
  "coeficiente_consumo": {"valor": 70, "unidad": "g/completo"},
  "rendimiento_util": 1,
  "merma_pct": 0,
  "conversiones": [
    {"desde": "g", "hacia": "kg", "factor": 0.001}
  ],
  "formato_comercial": {"contenido": 1, "unidad": "kg", "unidades_por_pack": 1},
  "cantidad_neta": 1.4,
  "cantidad_compra": 2,
  "unidad_compra": "kg",
  "formula_legible": "20 completos × 70 g/completo ÷ 1000 g/kg"
}
```

## Validaciones mínimas

- Unidad de salida compatible con la fórmula.
- Variables requeridas presentes y mayores que cero.
- Merma dentro de un rango configurable.
- Cantidad de compra igual o superior a la neta.
- Trazabilidad hasta archivo, página, fila, recinto o entrada del usuario.
- Detección de ítems equivalentes o duplicados.
- Alerta por valores atípicos contra ratios históricos, sin corregirlos automáticamente.
- Cierre dimensional de cada fórmula y de cada conversión intermedia.

## Alcance recomendado del MVP

### Fase 1 — Paramétrico y planillas

- Definir esquema de cubicación y versionado.
- Crear biblioteca inicial de fórmulas y recetas.
- Mejorar el importador Excel/CSV con mapeo de columnas y validación de unidades.
- Añadir pantalla de revisión antes de crear la lista de cotización.
- Publicar únicamente ítems aprobados al flujo de `listas.py`.

### Fase 2 — Catálogo y aprendizaje controlado

- Formatos comerciales y factores de conversión por producto.
- Coeficientes y mermas configurables por empresa.
- Comparación contra cubicaciones históricas.
- Plantillas por industria y tipo de proyecto.

### Fase 3 — Planos y BIM

- PDF 2D con calibración y confirmación visual.
- Importación IFC y mapeo de propiedades.
- Vínculo entre cada cantidad y el elemento o medición de origen.

## Criterio de aceptación del MVP

Dado un proyecto con parámetros completos o una planilla válida, Baiyer genera una lista
cuantificada donde el usuario puede verificar cada fórmula, unidad, conversión, merma y
supuesto; corregirla; aprobarla; y enviarla al flujo de cotización sin perder trazabilidad.

## Lo que este archivo no debe ser

Este documento define el comportamiento y contrato del motor. No debe convertirse en una
base de datos gigante de rendimientos dentro de Markdown. Fórmulas, recetas, conversiones y
coeficientes deben vivir como datos versionados y testeables en la aplicación; este archivo
explica sus reglas y decisiones de diseño.
# Implementación funcional (30-jul-2026)

La implementación ejecutable vive en `backend/app/services/cubicacion.py`. Incluye el registro
dimensional, conversiones validadas, redondeo comercial y las recetas versionadas
`completos@1`, `pintura@1` y la evaluación `solar-evaluacion@1`. `/api/identificar` mantiene compatibilidad: sólo activa el motor
cuando `modo_cubicacion_conversacional=true`; los clientes antiguos siguen por el contrato IA.

El estado nuevo usa `respuestas_cubicacion` (objeto por ID estable), devuelve como máximo tres
preguntas estructuradas por turno y no necesita reenviar la imagen. Al terminar entrega
`revision_cubicacion` con neto, compra, formato, fórmula, supuestos y advertencias. `/cotizar`
muestra esta revisión antes de que el usuario confirme y recién entonces reutiliza el flujo real
de `cotizaciones` + `listas.py`.

Pintura propone rendimiento, merma y envase únicamente cuando el usuario marca “No lo sé”, y
exige confirmar cada supuesto. Solar mantiene separados kW y kWh y advierte orientación sur e
inspección. Entrega una lista preliminar de paneles, inversor, estructura, protecciones y conectores
con supuestos visibles; el servicio profesional queda como ítem opcional. Baterías y cableado se
excluyen mientras no existan datos de autonomía y trazado.

Pruebas deterministas: `backend/tests/test_cubicacion.py`.
