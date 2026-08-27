# Diseño — Servicio de inventario con alimentación por WhatsApp y reposición automática

Estado: **investigación / propuesta**. No hay código escrito ni migración aplicada.
Fecha: 2026-08-20.

## 0. Punto de partida real (verificado, no supuesto)

- **Baiyer hoy no tiene inventario.** Grep en todo el repo: la palabra "inventario" sólo aparece
  dos veces, en el sentido de "listado" (`PLAN_DATA_FOUNDATION.md:288`,
  `PRD_WORKFLOW_COMUNICACIONES_UNIFICADO.md:972`). No hay tabla, router, servicio ni pantalla.
- **No hay maestro de productos.** El listado de tablas realmente usadas por el backend no
  contiene ningún catálogo: los ítems nacen ad-hoc en `cotizaciones` (una fila por ítem, texto
  identificado por Gemini) y se agrupan en listas (`proyectos.descripcion` como JSON). No existe
  una entidad "producto/SKU" estable a la cual colgarle un stock. **Esto es el hueco central del
  proyecto, no el WhatsApp.**
- **No hay integración WhatsApp.** Lo único existente es scraping de números y armado de links
  `wa.me` con texto pre-hecho (`services/contacto_scraper.py`) — es saliente, manual y sin API.
- **Sí existe todo el resto de la cadena**, y hay que reusarlo, no reimplementarlo:
  - `services/recurrencia_service.py` + `check_recurrencias()` — compras periódicas por fecha, con
    modo `re_cotizar` / `oc_directa`, tope `monto_maximo` y aviso de aprobación. **Es el ancestro
    directo de lo que se pide acá**: reposición por stock es la misma máquina con otro disparador.
  - `services/workflow_execution.py:153` `iniciar_autorizacion_workflow(user_id, lista_id, monto_total)`
    — entrada única al ciclo de autorización real. Ya resuelve el nodo por monto, los responsables y
    la instancia. **El disparador de inventario debe terminar acá, no en un flujo paralelo.**
  - `services/lista_service.py` `create_list()` — crea la lista operativa desde código.
  - Fases A–G del motor unificado (RFQ → autorización → homologación → OC → despacho), con cola
    durable `workflow_scheduled_actions` y lease atómico (`workflow_scheduler.py`, cron 1 min).
  - `services/cron.py` — APScheduler in-process, ya corriendo jobs de 1 min y 1 h.

## 1. Alcance propuesto

1. Maestro de ítems de inventario + saldo por ubicación.
2. Kardex: **movimientos como fuente de verdad**, saldo derivado.
3. Captura por WhatsApp conversacional (reemplaza la pistola en la etapa inicial).
4. Puntos de reorden que disparan cotización + ciclo de autorización existente.

Fuera de alcance en el primer corte (decir que no explícitamente): valorización contable
(FIFO/PMP para balance), lotes/series/vencimientos, multi-bodega con transferencias, conteo
cíclico completo, integración SII/ERP.

## 2. Modelo de datos

Cinco tablas nuevas. Nombres en español, coherentes con `proveedores`/`organizaciones`.

```
inventario_items            -- maestro: sku, nombre, unidad, organizacion_id, categoria,
                               proveedor_preferido_id, cotizacion_referencia_id (link al mundo
                               de compras), activo
inventario_ubicaciones      -- bodega/obra/pañol. Una default por organización.
inventario_saldos            -- (item_id, ubicacion_id) → cantidad, actualizado_at.
                               DERIVADO, reconstruible desde movimientos.
inventario_movimientos       -- KARDEX. append-only: item, ubicacion, tipo
                               (entrada|salida|ajuste|conteo|reserva|liberacion),
                               cantidad_delta, motivo, origen (whatsapp|web|oc|api),
                               actor_user_id | telefono_origen, referencia (oc_id / lista_id),
                               idempotency_key UNIQUE, created_at
inventario_reglas_reposicion -- item_id, ubicacion_id, minimo, punto_reorden, cantidad_objetivo,
                               proveedor_preferido_id, modo (re_cotizar|oc_directa),
                               monto_maximo, activa, cooldown_horas, ultima_ejecucion_at
```

Decisiones que importan:

- **Kardex append-only, saldo derivado.** Un `UPDATE saldos SET cantidad = cantidad - 5` es
  irreconciliable cuando alguien reclama. El movimiento se inserta primero; el saldo se actualiza
  vía RPC/trigger en la misma transacción y siempre se puede recalcular con
  `SUM(cantidad_delta)`. Es el mismo criterio que ya rige `workflow_events` y
  `recalcular_capacidad()` en Supplier Capability Intelligence ("siempre recalculada desde los
  eventos, nunca incrementada in-place").
- **`idempotency_key` UNIQUE en movimientos, obligatoria.** WhatsApp reintenta webhooks; un
  reintento no puede descontar dos veces. Clave = `wa:{message_id}`. Mismo patrón que
  `reserve_mail_delivery_event()` de la 041.
- **`punto_reorden` separado de `minimo`.** El pedido explícito es "gatillar cuando esté *cerca*
  del mínimo": el mínimo es el piso que no se quiere tocar, el punto de reorden es el umbral que
  dispara, y la diferencia es el colchón para el lead time del proveedor. Con un solo número se
  dispara siempre tarde.
- **RLS por organización** desde la migración, igual que la 031. No repetir el agujero de
  `procurement.py`.
- **Aplicar la migración a mano** en el SQL Editor (gotcha conocido: el service key no hace DDL) y
  **verificar con una query real** que las tablas existen antes de dar nada por hecho.

### El maestro de ítems es el trabajo de fondo

Sin SKU estable, "quedan 3 tornillos" no se puede resolver contra nada. Propuesta pragmática:
`inventario_items` se puebla (a) manualmente / por importación CSV, (b) desde una compra
recibida — cuando una OC pasa a `recibido_conforme`, se ofrece crear/vincular el ítem de
inventario a esa `cotizacion_id`. Así el catálogo crece con el uso real y queda ligado al historial
de precios y proveedores que la app ya tiene. **No inventar un catálogo genérico chileno.**

## 3. Captura por WhatsApp

### Proveedor: WhatsApp Cloud API de Meta, directo

Alternativas descartadas: Twilio/360dialog (markup sobre el precio de Meta, una dependencia más);
librerías no oficiales tipo `whatsapp-web.js` (violan los ToS, el número se banea, inaceptable
para un dato operativo de un cliente).

Lo que hay que saber del modelo comercial (verificado agosto 2026):

- Desde julio 2025 Meta cobra **por mensaje de plantilla entregado**, por categoría
  (marketing/utility/authentication) y país del destinatario.
- La **ventana de servicio de 24 h** se abre cuando el usuario escribe. Dentro de ella, las
  respuestas del negocio y las plantillas *utility* son gratis **hoy**, pero eso **se acaba el
  1 de octubre de 2026**: desde esa fecha las utility y los mensajes de servicio dentro de la
  ventana también se cobran.
- Consecuencia de diseño: el flujo de inventario es casi todo **iniciado por el bodeguero**
  ("recibí 20 sacos"), así que cae dentro de la ventana y hoy sale ~gratis. Lo que sí cuesta —
  y hay que presupuestar desde ya, y limitar — son los mensajes **salientes proactivos**
  (recordatorio de conteo, aviso de quiebre de stock). Ese costo escala con el número de ítems
  bajo mínimo, así que necesita agregación diaria, no un mensaje por ítem.

Requisitos operativos: número de teléfono dedicado (no el WhatsApp personal del dueño),
verificación de Meta Business, y las plantillas proactivas **pre-aprobadas** por Meta (revisión de
horas a días). Esto es plazo de calendario, no de programación — conviene arrancar el trámite
antes de escribir el código.

### Flujo conversacional

```
Bodeguero: "salieron 20 sacos de cemento a la obra centro"
Bot:       "20 sacos Cemento Melón 25kg · salida · Obra Centro. Quedan 34. ¿Confirmas?" [Sí][No]
Bodeguero: [Sí]
Bot:       "Registrado. ⚠️ Cemento quedó bajo el punto de reorden (40). Preparo cotización."
```

- **El LLM sólo interpreta; el movimiento lo decide y lo escribe Python.** Es exactamente la
  regla que ya se estableció en `workflow_proceso_slots.py` y en el onboarding conversacional:
  Gemini propone `{item, cantidad, unidad, tipo, ubicacion}` con `response_schema` (structured
  output, como `ESQUEMA_EXTRACCION`), y el matching contra el maestro, la conversión de unidades y
  la validación son determinísticos.
- **Confirmación explícita antes de escribir**, con botones interactivos. Un movimiento errado
  contamina el kardex y termina disparando una compra falsa. Si el match del ítem es ambiguo,
  botones con los 3 candidatos; nunca adivinar.
- **Foto de la guía de despacho**: el pipeline de visión ya existe (`/identificar` acepta imagen).
  Reusarlo, no escribir otro.
- **Autenticación por número**: tabla `inventario_telefonos_autorizados` (telefono → user_id +
  organizacion_id + ubicacion default). Un número desconocido no recibe respuesta útil ni crea
  nada. El webhook además valida la firma `X-Hub-Signature-256` de Meta — sin eso cualquiera
  puede POSTear movimientos.

### Riesgo de seguridad a nombrar

El mensaje de WhatsApp es **entrada no confiable**, igual que los correos de proveedor y los
resultados web (las propias instrucciones del MCP de Baiyer lo dicen). El texto del bodeguero no
puede terminar en un prompt que decida acciones: interpreta a estructura, y punto. Y el ciclo
completo "WhatsApp → cotización → OC" nunca debe cerrarse sin humano: el disparador llega hasta
*preparar la cotización y pedir autorización*, jamás emite una OC solo.

## 4. Reposición automática

Un job en `cron.py` (`_check_reposicion`, cada 1 h — la misma cadencia que `_check_recurrencias`,
no hace falta menos):

1. Buscar `inventario_saldos` donde `cantidad <= punto_reorden` con regla activa.
2. Descartar los que estén en `cooldown_horas` desde `ultima_ejecucion_at`, o que ya tengan una
   lista de reposición abierta para ese ítem. **Sin esto, un ítem bajo mínimo genera una
   cotización por hora hasta que llegue la mercadería.** Es el bug más probable de todo el diseño.
3. **Agrupar por proveedor preferido**: 8 ítems bajo mínimo del mismo proveedor son *una* lista y
   *una* autorización, no ocho. El agrupamiento es también lo que hace tolerable el costo de
   WhatsApp y el ruido de correo.
4. Crear la lista con `lista_service.create_list()`, marcada `origen: "reposicion_inventario"`.
5. Según `modo`: `re_cotizar` entra al flujo RFQ existente (Fase D); `oc_directa` con último precio
   conocido salta a autorización.
6. Llamar `iniciar_autorizacion_workflow(user_id, lista_id, monto_total)`. **Cero lógica de
   aprobación nueva**: el canvas del cliente ya define quién autoriza según monto, y si no hay
   workflow activo cae al flujo legado igual que hoy.
7. Notificar por la campanita (`notificaciones`) y, agregado, por WhatsApp.

`cantidad_objetivo - saldo_actual` da la cantidad a pedir (reposición hasta nivel objetivo), no
`punto_reorden - saldo`, que pide siempre migajas.

## 5. Exposición por MCP

Requisito explícito: el inventario debe ser consultable desde MCP. Se hace en **dos capas**, no
una — el servidor ya tiene ambas y mezclarlas sería inventar un tercer patrón.

### Capa A — consulta genérica read-only (`query_baiyer_data`)

`services/semantic_query.py` ya expone un DSL sin SQL (`entity` + `fields` + `filters` + `order` +
`limit`, allowlist estricta, máx. 200 filas) usado por `describe_query_schema` y
`query_baiyer_data`. Agregar tres `EntitySpec`:

```python
"inventory_items":     ("inventario_items",       {id, sku, nombre, unidad, categoria, activo, ...})
"inventory_balances":  ("inventario_saldos",      {item_id, ubicacion_id, cantidad, actualizado_at})
"inventory_movements": ("inventario_movimientos", {id, item_id, ubicacion_id, tipo, cantidad_delta,
                                                   motivo, origen, referencia, created_at})
```

Con eso, "¿qué ítems están bajo el mínimo?" o "¿cuánto cemento salió en julio?" funcionan el día 1
sin escribir una tool por pregunta. Costo: ~10 líneas.

**Problema real de ownership que hay que resolver antes.** `query_data()` filtra siempre con
`.in_(spec.ownership, actor.organization_user_ids)`, es decir asume que la tabla tiene una columna
con un **user_id** y que la pertenencia se deriva de la lista de usuarios de la organización. Las
tablas de inventario son naturalmente de la **organización** (`organizacion_id`), no de un usuario:
el stock no le pertenece a quien lo cargó. Dos salidas:

1. Enseñarle a `EntitySpec` un modo `ownership_kind = "organizacion"` que filtre por
   `.eq("organizacion_id", actor.organizacion_id)`. **Recomendada** — es el modelo correcto y
   destraba a futuro cualquier otra entidad organizacional.
2. Duplicar `user_id` en las filas de inventario sólo para encajar en el filtro. Rechazada: replica
   exactamente la clase de modelo paralelo que `PLAN_DATA_FOUNDATION.md` está tratando de limpiar.

Sin resolver esto, exponer inventario por la capa A o **filtra mal** (0 filas) o, peor, **no filtra**.

### Capa B — tools dedicadas de lectura (donde hay lógica de dominio)

La capa A devuelve filas; no sabe qué es un punto de reorden ni agrupa por proveedor. Tools nuevas,
siguiendo el patrón de `mcp/streamable.py` (`@mcp.tool` + `_actor(scope)` + `asyncio.to_thread`
sobre el servicio síncrono):

| Tool | Scope | Qué hace |
|---|---|---|
| `get_inventory_item` | `inventory:read` | Ficha: saldo por ubicación, regla de reposición, últimos movimientos, proveedor preferido |
| `get_stock_levels` | `inventory:read` | Saldos con filtro `solo_bajo_minimo`, ordenado por criticidad (saldo/punto_reorden) |
| `get_item_movements` | `inventory:read` | Kardex paginado por ítem/ubicación/rango de fechas |
| `get_reorder_suggestions` | `inventory:read` | Lo que el cron *propondría* ahora: agrupado por proveedor, con cantidad a pedir y monto estimado. Diagnóstico puro, no crea nada |

### MCP es SÓLO consultivo — decisión explícita

**No hay tools de escritura de inventario, ni ahora ni como pendiente "para más adelante".** No
existe `register_inventory_movement`, `set_reorder_rule` ni `trigger_replenishment`. El saldo se
modifica únicamente por los caminos con humano y trazabilidad de origen: WhatsApp con confirmación
del bodeguero, la pantalla `/inventario`, o el propio ciclo de compra al recibir una OC.

El motivo no es prudencia genérica, es que **el kardex es el insumo del disparador de compras**.
Cualquier escritura por MCP tendría tres problemas que las otras entidades no tienen:

- **Rompe la atribución.** Todo movimiento lleva `origen` y un actor humano identificable
  (`telefono_origen` o `actor_user_id`). Un agente escribiendo deja un movimiento cuyo responsable
  real es una conversación que no está en la base. Cuando el saldo no cuadre —y va a pasar— eso es
  justamente lo que hay que poder auditar.
- **Es un disparador de gasto indirecto.** Bajar un saldo por MCP no "edita un dato": empuja el
  ítem bajo el punto de reorden y arranca cotización + ciclo de autorización. La separación
  preview → commit que usa `prepare_purchase_order` acá no alcanza, porque el commit peligroso
  ocurre *después*, en el cron, sin que nadie lo relacione con la tool que lo causó.
- **El inventario refleja el mundo físico.** Una lista o una OC son objetos internos que se
  corrigen; el stock es una afirmación sobre lo que hay en la bodega. Sólo quien lo ve puede
  afirmarlo.

Por eso `get_reorder_suggestions` es deliberadamente un **diagnóstico y no un preview**: sirve para
que el agente explique *por qué* se va a comprar algo, no para habilitar un "y ahora ejecútalo".
Si más adelante se quiere un atajo tipo "el agente propone un ajuste", la forma correcta es que
deje una **sugerencia pendiente de aprobación humana** en la web —nunca un movimiento—, y eso sería
un proyecto aparte con su propia decisión.

Criterios que ya rigen el resto del servidor MCP y aplican igual acá:

- **Un solo scope nuevo: `inventory:read`.** No crear `inventory:write` — un scope que no se puede
  ejercer es una invitación a que alguien lo cablee después sin volver a discutir esto.
- `annotations=ToolAnnotations(readOnlyHint=True)` en las cuatro tools.
- Todo pasa por `McpAuditMiddleware` y `mcp_audit_log`, sin argumentos sensibles.

### Orden

Capa A entra con la **Fase 1** (es casi gratis y hace el inventario consultable apenas existan las
tablas). Capa B, en Fase 1–2 según estén los datos: `get_reorder_suggestions` necesita que existan
las reglas de reposición, así que va con la Fase 2. Al ser todo lectura, ninguna depende de que el
flujo de compra esté validado.

## 6. Fases sugeridas

| Fase | Contenido | Verificable por |
|---|---|---|
| 1 | Migración + maestro + kardex + saldos + pantalla `/inventario` con carga manual + MCP capa A (`ownership_kind` organizacional) | Un ajuste manual mueve el saldo, queda en el kardex y `query_baiyer_data` lo devuelve |
| 2 | Reglas de reposición + cron + creación de lista + `iniciar_autorizacion_workflow` + tools MCP de lectura (`inventory:read`) | Bajar un saldo a mano dispara una autorización real |
| 3 | WhatsApp Cloud API: webhook, firma, teléfonos autorizados, texto → movimiento con confirmación | Un mensaje real registra un movimiento idempotente |
| 4 | Foto de guía de despacho, avisos proactivos agregados, conteo cíclico | — |

**Fase 2 antes que fase 3 a propósito.** La reposición automática es donde está el valor y el
riesgo real; WhatsApp es un canal de entrada que se puede probar con la web primero. Además la
fase 3 depende de un trámite con Meta que no controlamos.

## 7. Deudas del repo que este proyecto toca

- El maestro de ítems roza directamente `PLAN_DATA_FOUNDATION.md` (`proveedores`/`suppliers`,
  `organizaciones`/`organizations`, `procurement.py` huérfano). Crear `inventario_items` sin
  mirar ese plan agrega un modelo paralelo más al problema que el plan quiere resolver.
- Los endpoints nuevos deben usar `Depends(get_auth_context)` y
  `ejecutar_maybe_single()` (gotchas conocidos), no `user_id` del body ni
  `.maybe_single().execute()`.
- El webhook de WhatsApp es un endpoint público más que llama a Gemini: necesita el mismo
  tratamiento que `services/llm_rate_limit.py` da a los de workflows, y topes de tamaño de body.

Fuentes sobre precios/ventana de WhatsApp:
[Authgear](https://www.authgear.com/post/whatsapp-api-pricing/) ·
[Wati](https://www.wati.io/en/blog/whatsapp-api-pricing-guide/) ·
[Blueticks](https://blueticks.co/blog/whatsapp-business-pricing-change-2026-per-message)
