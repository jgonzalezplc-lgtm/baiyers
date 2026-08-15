# Baiyer MCP — Contrato operativo (Fase 0)

Estado: **contrato aprobado; Fase 1 implementada y migración 038 aplicada/confirmada**
Fecha: 2026-08-13
Alcance: Codex, Claude Code, Claude Desktop/web y clientes MCP compatibles.

## 1. Objetivo

El MCP de Baiyer será una interfaz conversacional completa sobre el ciclo de
procurement existente. No implementará un segundo backend ni dará acceso SQL
libre. Cada tool deberá reutilizar la misma lógica de negocio, identidad,
organización, agentes y auditoría que la aplicación web.

Flujo objetivo:

```text
prompt o documento
  -> proyecto/cubicación/lista
  -> búsqueda web y proveedores internos
  -> RFQ por Gmail
  -> seguimiento de respuestas
  -> comparación y selección
  -> workflow de aprobación
  -> orden de compra
  -> factura/conciliación
  -> informe y analítica
```

## 2. Decisiones canónicas

1. La lista multiítem de `routers/listas.py` es la entidad operativa principal.
   Se persiste hoy como `proyectos.descripcion` con `tipo=lista_cotizacion`, y
   cada ítem posee un `cotizacion_id` estable.
2. `routers/proyectos.py` (Gantt, `items_proyecto` y
   `cotizaciones_proyecto`) no será la base del proyecto conversacional MCP.
3. Las búsquedas usarán el motor real de `routers/buscar.py`, pero la lógica se
   extraerá a servicios compartidos; ninguna tool llamará a `localhost`.
4. Las solicitudes privadas usarán `rfq_batches`/`rfq_batch_items` y el agente
   Gmail existente.
5. Las aprobaciones usarán el Workflow Builder activo y
   `approval_requests`; el servidor comprobará al responsable real.
6. Las OC usarán `ordenes_compra` y el seguimiento Gmail existente.
7. Los informes de listas usarán el modelo real de listas, no las tablas Gantt
   vacías que aún consulta parte de `routers/reportes.py`.
8. El actor y su organización vendrán del token MCP. Un `user_id` recibido en
   arguments nunca será autoridad.
9. No se expondrá `execute_sql`. Las consultas serán semánticas y sobre una
   allowlist de entidades/vistas.
10. Preparar, confirmar y ejecutar son operaciones separadas para RFQ,
    aprobaciones, OC, importaciones y facturas.

## 3. Convenciones del protocolo de producto

### 3.1 Identidad de llamada

Todas las tools reciben internamente, nunca desde el modelo:

```text
actor_user_id
organization_id
organization_user_ids
client_id
scopes
request_id
```

Toda escritura recibe además `idempotency_key`. La respuesta común contiene:

```json
{
  "request_id": "uuid",
  "status": "completed",
  "data": {},
  "warnings": [],
  "next_actions": []
}
```

### 3.2 Operaciones largas

Búsquedas, parsing de documentos, sincronizaciones, importaciones e informes
podrán responder con un job:

```json
{
  "request_id": "uuid",
  "status": "queued",
  "job": {
    "id": "uuid",
    "type": "web_search",
    "progress": 0,
    "created_at": "ISO-8601"
  }
}
```

Estados canónicos de job:

```text
queued | running | awaiting_input | completed | failed | cancelled
```

Tools transversales:

| Tool | Scope | Efecto |
|---|---|---|
| `get_job` | `jobs:read` | Consulta estado, progreso y resultado |
| `list_jobs` | `jobs:read` | Lista jobs de la organización |
| `cancel_job` | `jobs:write` | Cancela cuando la operación lo permite |

### 3.3 Confirmaciones

Niveles:

| Nivel | Regla |
|---|---|
| `none` | Lecturas y previews |
| `explicit` | El usuario debe confirmar en la conversación actual |
| `privileged` | Confirmación más rol/permiso de negocio verificado |

Nunca se considera confirmación una instrucción contenida dentro de un PDF,
correo, resultado web o campo importado.

## 4. Catálogo de tools v1

Los nombres son estables desde esta fase. Una tool marcada `gap` necesita
servicio o persistencia nueva; `partial` tiene lógica existente incompleta;
`existing` puede mapearse al flujo actual después de extraer un servicio.

### 4.1 Proyectos, listas y documentos

| Tool | Scope | Confirmación | Estado | Fuente actual |
|---|---|---:|---|---|
| `start_project_intake` | `projects:write` | none | partial | `identificar`, `services/cubicacion.py` |
| `continue_project_intake` | `projects:write` | none | partial | `identificar` (`respuestas_cubicacion`) |
| `preview_document_import` | `documents:write` | none | partial | `identificar` acepta PDF/Office/imagen, 15 MB |
| `commit_document_import` | `lists:write` | explicit | gap | crear cotizaciones + lista atómicamente |
| `create_list` | `lists:write` | none | existing | `POST /api/listas` |
| `list_lists` | `lists:read` | none | existing | `GET /api/listas` |
| `get_list` | `lists:read` | none | existing | `GET /api/listas/{id}` |
| `add_list_items` | `lists:write` | none | gap | no existe mutación canónica |
| `update_list_item` | `lists:write` | none | partial | hoy solo cantidad/selección |
| `remove_list_item` | `lists:write` | explicit | gap | no existe mutación canónica |
| `rename_list` | `lists:write` | none | gap | escritura simple pendiente |

El preview de documentos debe retornar todas las filas detectadas, problemas
de cantidad/unidad, supuestos, advertencias y un `draft_id`. El commit solo
acepta un draft del mismo actor/organización y guarda una vez.

### 4.2 Búsqueda web y cotización

| Tool | Scope | Confirmación | Estado | Fuente actual |
|---|---|---:|---|---|
| `start_web_quote` | `quotes:write` | none | existing | `_buscar_fuentes`, `/buscar` y `/buscar/stream` |
| `get_web_quote` | `quotes:read` | none | partial | resultados + nuevo job |
| `search_alternatives` | `quotes:write` | none | existing | `busqueda_expandida` |
| `get_item_quotes` | `quotes:read` | none | existing | comparador de `listas.py` |
| `get_list_coverage` | `quotes:read` | none | existing | búsqueda complementaria/matriz |

`start_web_quote` podrá operar sobre un ítem o una lista. Debe informar
progreso por ítem y fuente, sin mantener una llamada MCP abierta varios
minutos.

### 4.3 Proveedores y RFQ por correo

| Tool | Scope | Confirmación | Estado | Fuente actual |
|---|---|---:|---|---|
| `suggest_suppliers` | `suppliers:read` | none | existing | capability intelligence + sugeridos |
| `get_supplier_matrix` | `rfq:read` | none | existing | proveedores-confianza |
| `set_supplier_matrix` | `rfq:write` | none | existing | PUT proveedores-confianza |
| `select_supplier_for_item` | `rfq:write` | none | existing | materializa sólo sugeridos elegidos |
| `prepare_rfq` | `rfq:write` | none | existing | `POST /{lista}/rfq/preparar` |
| `get_rfq_preview` | `rfq:read` | none | existing | `GET /{lista}/rfq` |
| `update_rfq_draft` | `rfq:write` | none | existing | PATCH batch |
| `send_rfq` | `rfq:send` | explicit | existing | POST batch/enviar |
| `get_rfq_status` | `rfq:read` | none | existing | batches + conversations |
| `sync_supplier_replies` | `mail:sync` | explicit | existing | sincronizar-respuestas |
| `list_supplier_replies` | `mail:read` | none | existing | conversaciones/propuestas |
| `get_supplier_reply` | `mail:read` | none | existing | detalle conversación |
| `apply_reply_proposal` | `quotes:write` | explicit | existing | propuestas/{id}/aplicar |
| `reject_reply_proposal` | `quotes:write` | explicit | existing | propuestas/{id}/rechazar |
| `prepare_supplier_followup` | `mail:read` | none | gap | render sin enviar |
| `send_supplier_followup` | `mail:send` | explicit | partial | agente tiene seguimiento automático |

Una respuesta se considera recibida desde datos persistidos, nunca porque el
modelo infiera que “probablemente respondió”. Deben exponerse por lista,
proveedor e ítem los estados reales de `rfq_batches`, `rfq_batch_items`,
`gmail_conversations` e `item_field_updates`.

### 4.4 Comparación y selección

| Tool | Scope | Confirmación | Estado | Fuente actual |
|---|---|---:|---|---|
| `compare_item` | `quotes:read` | none | existing | detalle de lista/resultados |
| `compare_list` | `quotes:read` | none | existing | detalle + informe de lista |
| `explain_quote_recommendation` | `quotes:read` | none | partial | ranking existente |
| `select_final_quote` | `quotes:write` | explicit | existing | `/{lista}/definitivo` |
| `clear_final_quote` | `quotes:write` | explicit | existing | definitivo con `quitar` |

Los comparativos devolverán precios unitarios, cantidad, total de línea,
moneda original/CLP, plazo, condiciones, disponibilidad, origen, score,
evidencia, campos pendientes y oferta definitiva.

### 4.5 Aprobaciones

| Tool | Scope | Confirmación | Estado | Fuente actual |
|---|---|---:|---|---|
| `get_approval_status` | `approvals:read` | none | existing | lista + approval requests/workflow |
| `get_approval_route` | `approvals:read` | none | existing | workflow execution preview |
| `request_approval` | `approvals:request` | explicit | existing | solicitar-aprobacion |
| `resend_approval_request` | `approvals:request` | explicit | existing | reenviar-aprobacion |
| `approve_request` | `approvals:decide` | privileged | partial | hoy decisión por magic link |
| `reject_request` | `approvals:decide` | privileged | partial | hoy decisión por magic link |
| `correct_and_resubmit` | `lists:write` + `approvals:request` | explicit | gap | composición transaccional pendiente |
| `list_workflow_events` | `approvals:read` | none | existing | `workflow_events` |

Para decidir desde MCP se necesita vincular inequívocamente el actor MCP con
el `responsable_id` del nodo actual. No se reutilizará un magic link como
credencial invisible del servidor.

### 4.6 Órdenes de compra

| Tool | Scope | Confirmación | Estado | Fuente actual |
|---|---|---:|---|---|
| `prepare_purchase_order` | `po:read` | none | partial | datos definitivos + perfil organización |
| `create_purchase_order` | `po:write` | explicit | existing | `POST /api/oc/crear` |
| `list_purchase_orders` | `po:read` | none | gap | falta endpoint canónico |
| `get_purchase_order` | `po:read` | none | partial | falta lectura autenticada completa |
| `update_purchase_order` | `po:write` | explicit | gap | falta endpoint canónico |
| `send_purchase_order` | `po:send` | privileged | existing | `POST /api/oc/enviar` |
| `get_purchase_order_tracking` | `po:read` | none | partial | conversación Gmail/estado OC |

No se permite crear y enviar una OC en la misma tool. `send_purchase_order`
requiere una OC ya persistida, un preview verificable y aprobación válida
cuando el workflow de la organización la exija.

### 4.7 Facturas

| Tool | Scope | Confirmación | Estado | Fuente actual |
|---|---|---:|---|---|
| `preview_invoice_import` | `invoices:write` | none | partial | parser Gmail, falta upload directo |
| `commit_invoice_import` | `invoices:write` | explicit | gap | persistencia desde draft |
| `create_invoice` | `invoices:write` | explicit | existing | POST `/api/facturas` |
| `list_invoices` | `invoices:read` | none | existing | GET `/api/facturas` |
| `get_invoice` | `invoices:read` | none | gap | falta endpoint individual |
| `update_invoice` | `invoices:write` | explicit | gap | hoy solo marcar pagada |
| `match_invoice_to_po` | `invoices:write` | explicit | gap | conciliación pendiente |
| `reconcile_invoice_po` | `invoices:read` | none | gap | comparación estructurada pendiente |
| `mark_invoice_paid` | `invoices:pay` | privileged | existing | PATCH `/pagar` |
| `scan_invoice_inbox` | `mail:sync` | explicit | existing | `/scan-inbox` |

### 4.8 Proveedores e importación

| Tool | Scope | Confirmación | Estado | Fuente actual |
|---|---|---:|---|---|
| `search_suppliers` | `suppliers:read` | none | existing | suppliers/proveedores |
| `get_supplier` | `suppliers:read` | none | existing | ficha proveedor |
| `create_supplier` | `suppliers:write` | explicit | existing | POST proveedores |
| `update_supplier` | `suppliers:write` | explicit | existing | PATCH proveedores |
| `research_supplier` | `suppliers:write` | none | partial | investigar no usa AuthContext |
| `preview_supplier_import` | `suppliers:write` | none | gap | import actual escribe directo |
| `commit_supplier_import` | `suppliers:write` | explicit | partial | proveedores_import |
| `block_supplier` | `suppliers:block` | privileged | existing | suppliers/bloquear |
| `unblock_supplier` | `suppliers:block` | privileged | existing | suppliers/desbloquear |
| `get_supplier_history` | `suppliers:read` | none | existing | suppliers/historial |
| `set_supplier_categories` | `suppliers:write` | explicit | existing | proveedores/categorias |
| `detect_supplier_duplicates` | `suppliers:read` | none | gap | pendiente |
| `merge_suppliers` | `suppliers:merge` | privileged | gap | pendiente |

### 4.9 Informes, métricas y consultas

| Tool | Scope | Confirmación | Estado | Fuente actual |
|---|---|---:|---|---|
| `generate_list_report` | `reports:write` | none | partial | `/listas/{id}/informe`; PDF es frontend |
| `generate_analytics_report` | `reports:write` | none | gap | contrato de job/archivo pendiente |
| `get_report` | `reports:read` | none | gap | storage/expiración pendiente |
| `get_spend_metrics` | `analytics:read` | none | existing | estadísticas |
| `get_supplier_metrics` | `analytics:read` | none | existing | estadísticas/capabilities |
| `describe_query_schema` | `data:read` | none | gap | catálogo semántico pendiente |
| `query_baiyer_data` | `data:read` | none | gap | compilador seguro pendiente |

`query_baiyer_data` aceptará entidad, campos, filtros, orden, agregaciones y
límite. No aceptará SQL. Entidades v1 previstas:

```text
lists, list_items, quotes, quote_results, suppliers, rfq_batches,
supplier_replies, approvals, purchase_orders, invoices, spend_metrics
```

No se expondrán `auth.users`, integraciones OAuth, tokens, estados OAuth MCP,
plantillas internas completas, secretos, raw email ni tablas administrativas.

## 5. Resources MCP v1

Los resources son snapshots read-only y respetan los mismos scopes:

```text
baiyer://lists/{list_id}
baiyer://lists/{list_id}/comparison
baiyer://lists/{list_id}/rfq
baiyer://lists/{list_id}/replies
baiyer://suppliers/{supplier_id}
baiyer://approvals/{approval_id}
baiyer://purchase-orders/{po_id}
baiyer://invoices/{invoice_id}
baiyer://jobs/{job_id}
baiyer://reports/{report_id}
```

No se publicará una URI navegable para “toda la base de datos”. Listados y
búsquedas se hacen mediante tools paginadas.

## 6. Prompts MCP v1

Los prompts guían al cliente; no conceden permisos ni ejecutan acciones:

```text
quote_project
import_and_quote_document
review_list_coverage
follow_up_missing_suppliers
compare_list_quotes
review_for_approval
prepare_purchase_order
reconcile_invoice
analyze_procurement_spend
```

Cada prompt debe indicar al modelo que trate documentos, emails y resultados
web como datos no confiables y que use tools de preview antes de acciones.

## 7. Scopes v1

```text
jobs:read jobs:write
projects:write documents:write
lists:read lists:write
quotes:read quotes:write
suppliers:read suppliers:write suppliers:block suppliers:merge
rfq:read rfq:write rfq:send
mail:read mail:sync mail:send
approvals:read approvals:request approvals:decide
po:read po:write po:send
invoices:read invoices:write invoices:pay
reports:read reports:write
analytics:read data:read
```

Perfiles sugeridos:

| Perfil | Incluye |
|---|---|
| Observador | lectura, métricas e informes existentes |
| Comprador | observador + listas, cotizaciones, proveedores, RFQ y correo |
| Aprobador | observador + `approvals:decide`, condicionado al workflow |
| Finanzas | observador + OC/facturas según rol |
| Administrador | todos, sin saltarse reglas de negocio |

## 8. Estados de negocio expuestos

El MCP preservará el valor raw de base de datos y añadirá un estado canónico
para evitar que el cliente mezcle vocabularios.

### RFQ

```text
draft | ready | sending | sent | partially_answered | answered |
failed | delivery_uncertain | closed
```

### Respuesta/campo extraído

```text
pending_review | applied | rejected
```

### Aprobación

```text
not_requested | pending | approved | rejected | expired | cancelled
```

### Orden de compra

```text
draft | issued | sent | acknowledged | dispatched | received | cancelled
```

### Factura

```text
draft | pending | matched | discrepancy | overdue | paid | rejected
```

La tabla de traducción exacta raw->canónico se implementará junto a cada
dominio y tendrá tests.

## 9. Auditoría obligatoria

Cada tool call registrará:

```text
request_id, actor_user_id, organization_id, client_id, tool_name,
scope_used, entity_type, entity_id, idempotency_key, outcome, duration_ms,
confirmation_level, created_at
```

No se guardarán contraseñas, tokens, documentos completos, cuerpos completos
de correo ni respuestas completas del proveedor en el log MCP. Para evidencia
se guardará identificador/hash y referencia a la entidad autorizada.

## 10. Brechas bloqueantes para las fases siguientes

1. Transporte actual `/sse` + `/rpc` no es Streamable HTTP MCP estándar.
2. OAuth MCP no valida completamente cliente, redirect URI, PKCE y revocación.
3. Muchas tools actuales llaman a `localhost:8000` y usan contratos antiguos.
4. `identificar`, `buscar`, algunos endpoints Gmail, histórico y reportes aún
   aceptan `user_id` o carecen de `AuthContext`.
5. No existe persistencia genérica de jobs, drafts de importación ni informes.
6. Crear lista exige cotizaciones ya existentes; falta una operación atómica
   documento/proyecto -> cotizaciones -> lista.
7. Faltan mutaciones completas de ítems de lista.
8. Aprobar desde MCP necesita resolver actor -> responsable del nodo.
9. OC carece de listado/lectura/edición autenticada completos.
10. Facturas carecen de upload directo, detalle, edición y conciliación.
11. Importación de proveedores escribe directamente, sin preview/commit.
12. Reportes mezclan el modelo Gantt antiguo con cotizaciones actuales y parte
    de la generación PDF vive solo en frontend.
13. No existe catálogo semántico ni vistas seguras para consultas de datos.
14. `mcp_audit_log` actual es insuficiente y puede guardar parámetros/resultados
    sensibles como JSON serializado.
15. Debe verificarse en Supabase producción el estado real de las migraciones
    MCP 011 y 032 antes de diseñar la siguiente migración.

## 11. Criterios de aceptación de la Fase 0

- Existe un catálogo único de tools, resources, prompts y scopes.
- Cada tool tiene confirmación, estado de implementación y fuente canónica.
- Se definieron operaciones asíncronas e idempotencia.
- Se descartó el acceso SQL libre y se definió consulta semántica segura.
- Se fijó `listas.py` como modelo principal y se documentaron módulos legacy.
- Se identificaron todas las brechas bloqueantes de transporte, OAuth, datos y
  dominios operativos.
- Ningún cambio productivo, migración o despliegue forma parte de esta fase.

## 12. Salida hacia Fase 1

La Fase 1 debe comenzar por la fundación compartida, en este orden:

1. `McpActorContext` derivado del token y compatible con `AuthContext`.
2. repositorios/servicios para listas, cotizaciones y resultados;
3. servicio atómico proyecto/documento -> lista;
4. modelo de jobs y drafts;
5. servicio de consulta semántica read-only;
6. migración progresiva de routers para que web y MCP usen esos servicios.

No se implementará el catálogo completo de tools antes de completar esa capa,
porque hacerlo perpetuaría las llamadas HTTP internas y los contratos legacy.

## 13. Avance de Fase 1 (2026-08-13)

Implementado en código:

- `ApplicationActorContext`: identidad y organización verificadas, cliente,
  scopes y request id, independiente de FastAPI/MCP.
- `lista_service.py`: validación, creación y listado compartidos; los endpoints
  web de crear/listar ya delegan en este servicio sin cambiar su contrato.
- `mcp_jobs.py`: contratos de jobs y drafts con aislamiento organizacional e
  idempotencia.
- `semantic_query.py`: allowlist read-only inicial, filtros/orden/límites
  validados e inyección obligatoria de los usuarios de la organización.
- migración `038_mcp_data_foundation.sql`: tablas de jobs/drafts y función SQL
  transaccional e idempotente para convertir ítems identificados en
  cotizaciones + lista.
- tests unitarios de contexto, listas, jobs y consulta semántica.

La migración 038 fue aplicada y confirmada contra Supabase producción el
2026-08-14: `integration_jobs` e `integration_drafts` responden correctamente.
La RPC transaccional no se invocó durante la verificación para evitar crear
cotizaciones/listas productivas de prueba.

## 14. Avance de Fase 2 (2026-08-14)

Implementado en código:

- Streamable HTTP estándar, stateless, en `/api/mcp` usando el SDK Python MCP.
- autenticación HTTP 401 con `WWW-Authenticate` y Protected Resource Metadata;
- discovery RFC 8414/RFC 9728 en raíz y con path del recurso;
- DCR restringido a redirect URI HTTPS o loopback HTTP;
- PKCE S256, state, client, redirect URI, scopes y resource obligatorios;
- access/refresh tokens opacos, hashados, rotativos y revocables;
- resource/audience binding y revalidación de organización en cada tool;
- protección DNS rebinding mediante allowlist de hosts/orígenes;
- tools iniciales de conexión, listas, jobs y consulta semántica;
- pruebas de initialize, tools/list, discovery, 401, DCR, PKCE y audience.

Diseño operativo detallado en `MCP_AUTH_TRANSPORT.md`.

La migración 039 fue aplicada y confirmada en Supabase producción el
2026-08-14. Pendiente operativo: configurar variables MCP en Railway,
desplegar y ejecutar el flujo OAuth real con un cliente. Hasta entonces no
conectar Codex/Claude al endpoint productivo.

## 15. Avance de Fase 3 (2026-08-14)

Implementado en código:

- intake conversacional de proyectos con draft, preguntas y continuación;
- preview/commit de PDF y documentos Office sin persistir el archivo completo;
- commit explícito, idempotente y transaccional hacia cotizaciones + lista;
- lectura, creación, renombrado y mutaciones completas de ítems de lista;
- confirmación obligatoria para commit y eliminación;
- tools MCP publicadas con scopes y aislamiento por organización;
- pruebas específicas de servicios, confirmaciones y catálogo MCP.

Detalle operativo en `MCP_FASE_3_PROYECTOS_DOCUMENTOS_LISTAS.md`. Esta fase
reutiliza las migraciones 038/039 y no agrega una migración nueva.

## 16. Avance de Fase 4 (2026-08-14)

Implementado en código:

- búsqueda web normal y ampliada por ítem o lista;
- ejecución asíncrona con job persistido, progreso y salida parcial por ítem;
- recuperación de búsquedas interrumpidas por restart del worker productivo;
- listado, consulta y cancelación cooperativa de jobs;
- lectura normalizada de ofertas y matriz de cobertura por lista;
- validación de propiedad organizacional antes de leer o escribir resultados;
- tests de autorización, objetivos, metadata, idempotencia y catálogo MCP.

Detalle operativo en `MCP_FASE_4_BUSQUEDA_WEB_COTIZACIONES.md`. Reutiliza la
migración 038 y no requiere SQL adicional.

## 17. Avance de Fase 5 (2026-08-14)

Implementado en código:

- sugerencias y matriz proveedor–ítem con evidencia de capacidades;
- preparación idempotente, preview y edición de RFQ agrupadas;
- envío Gmail con confirmación y protección ante entrega incierta;
- estado canónico combinado de batches y conversaciones;
- sincronización, listado y detalle de respuestas persistidas;
- aplicación/rechazo confirmado de propuestas extraídas por el agente;
- bloqueo de cambios sobre propuestas ya revisadas;
- instrucciones MCP contra prompt injection desde correo/documentos/web.

Detalle operativo en `MCP_FASE_5_PROVEEDORES_RFQ_CORREO.md`. No requiere una
migración adicional. Los follow-ups manuales y el envío RFQ agrupado por
Outlook quedan como brechas explícitas, sin declarar soporte inexistente.

## 18. Avance de Fase 6 (2026-08-14)

Implementado en código:

- comparativos por ítem y lista con totales, campos faltantes y definitivo;
- recomendación determinística y explicable, sin auto-selección;
- selección/quita confirmada usando una oferta persistida autorizada;
- preview de ruta, estado de aprobación y eventos inmutables;
- solicitud de aprobación confirmada mediante Workflow Builder real;
- aprobación/rechazo MCP sólo para el responsable Baiyer vinculado al actor;
- rechazo explícito del flujo legacy por email desde MCP;
- snapshot de aprobación corregido para incluir alternativas reales.

Detalle operativo en `MCP_FASE_6_COMPARACION_APROBACIONES.md`. No requiere
migración adicional.

## 19. Avance de Fase 7 (2026-08-14)

Implementado en código:

- preview, creación, listado, detalle, edición, envío y tracking de OC;
- datos de OC derivados de una oferta definitiva autorizada;
- validación de aprobación cuando existe workflow activo;
- preview/commit de factura documental y lectura autenticada;
- conciliación read-only, vínculo explícito a OC y marcado de pago;
- escaneo confirmado del inbox;
- endurecimiento del endpoint web de envío de OC.

Detalle en `MCP_FASE_7_OC_FACTURAS.md`. No requiere migración adicional.

## 20. Avance de Fase 8 (2026-08-14)

Implementado: gestión/importación preview-commit de proveedores, informes y
métricas, nueve resources, nueve prompts y auditoría ASGI sin payloads
sensibles. `backend/migrations/040_mcp_audit_log.sql` queda pendiente de
aplicación manual. Detalle en
`MCP_FASE_8_PROVEEDORES_REPORTES_RESOURCES_AUDITORIA.md`.
