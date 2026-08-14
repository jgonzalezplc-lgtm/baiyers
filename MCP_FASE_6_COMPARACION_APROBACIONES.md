# Baiyer MCP — Fase 6: comparación, selección y aprobaciones

Estado: **implementada en código y pruebas locales**
Fecha: 2026-08-14

## Alcance

Esta fase permite revisar cuadros comparativos por ítem o lista, elegir la
oferta definitiva y operar el Workflow Builder desde MCP. Las decisiones no
usan el magic link como credencial invisible: el servidor enlaza al actor MCP
con `responsables.usuario_baiyer_id` antes de aprobar o rechazar.

## Tools de comparación

- `compare_item(list_id, cotizacion_id)`
- `compare_list(list_id)`
- `explain_quote_recommendation(list_id, cotizacion_id)`
- `select_final_quote(..., confirmed)`
- `clear_final_quote(..., confirmed)`

Los cuadros incluyen precio unitario, cantidad, total de línea, moneda,
fuente, plazo, disponibilidad/stock conocido, campos pendientes y selección
actual. La recomendación es determinística: prioriza ofertas relevantes con
datos completos, menor precio y luego rating. No selecciona automáticamente.

Al elegir una oferta, los datos de proveedor y precio se vuelven a leer desde
`resultados`; el modelo no puede inventarlos. Para moneda extranjera se exige
un `price_clp` explícito para calcular el total de la lista.

## Tools de aprobación

- `get_approval_status(list_id)`
- `get_approval_route(list_id)`
- `request_approval(..., confirmed)`
- `approve_request(request_id, confirmed, comment?, item_decisions?)`
- `reject_request(request_id, comment, confirmed)`
- `list_workflow_events(list_id)`

`get_approval_route` es sólo preview: muestra nodo, modalidad y responsables
sin crear instancia ni enviar correo. `request_approval` exige confirmación y
usa el Workflow Builder activo; sólo cae al email legado si no hay ruta.

## Regla de decisión MCP

Para aprobar o rechazar deben cumplirse todas:

1. la solicitud pertenece a la organización del actor;
2. sigue en estado `pendiente`;
3. tiene `responsable_id` de un workflow real;
4. ese responsable está activo;
5. `responsable.usuario_baiyer_id` coincide exactamente con el usuario del
   token MCP;
6. el usuario confirmó la acción en la conversación actual.

Las solicitudes legacy con sólo `aprobador_email` se rechazan desde MCP y
continúan decidiéndose mediante magic link.

## Correcciones y reenvío

Las correcciones se realizan con las tools de fase 3 (`update_list_item`) y
fase 6 (`clear_final_quote`/`select_final_quote`). Luego se consulta nuevamente
el comparativo y se ejecuta `request_approval`. No se incorporó una tool
monolítica que edite y envíe correo en una sola operación, porque una falla de
correo dejaría una falsa apariencia de transacción atómica.

## Mejoras al flujo web existente

- El snapshot enviado al aprobador ahora incluye las alternativas reales de
  `resultados`. Antes intentaba leer `comparados` desde el JSON de la lista,
  donde ese campo no existe, y el snapshot quedaba vacío.
- Las ofertas por correo ahora conservan `moneda_cotizada`, condiciones de
  pago, notas y fecha de respuesta en el contrato comparativo.

## Verificación

- 56 pruebas específicas de MCP aprobadas.
- 233 pruebas generales aprobadas, excluyendo únicamente el test preexistente
  que llama Gemini en vivo.
- 47 tools publicadas en el catálogo MCP total.
- No se enviaron solicitudes de aprobación reales durante las pruebas.
- No requiere migración SQL adicional: `usuario_baiyer_id` y las relaciones
  de workflow ya existen en producción.
