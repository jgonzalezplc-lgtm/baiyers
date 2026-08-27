# Baiyer — Plan Data Foundation para una plataforma API/MCP multiempresa

## Propósito

Este documento propone cómo convertir la persistencia actual de Baiyer en una plataforma de datos B2B organizada, multiempresa, auditable y preparada para ser consumida mediante API y MCP.

Está escrito como especificación de trabajo para Claude Code. **No implementar todo de una vez.** Primero se debe auditar el esquema real de producción, cerrar los riesgos de autorización y presentar un plan de migraciones pequeñas, retrocompatibles y verificables.

## Resultado esperado

Mantener **Supabase PostgreSQL como fuente operacional de verdad**, usando:

- PostgreSQL para entidades y relaciones del negocio.
- Supabase Auth únicamente para identidad y autenticación.
- Supabase Storage privado para documentos y archivos.
- FastAPI como única puerta de acceso al dominio.
- Una misma capa de servicios para frontend, API pública y MCP.
- Un warehouse separado sólo cuando el volumen analítico lo justifique.

El tenant y propietario real de los datos debe ser la **organización**, no un usuario individual.

---

## 1. Estado actual observado

### Infraestructura

- Backend: FastAPI en `backend/`, desplegado en Railway.
- Frontend: Next.js en `frontend/`, desplegado en Railway.
- Base de datos, Auth y archivos: Supabase.
- El backend crea el cliente Supabase con `SUPABASE_SERVICE_KEY`, por lo que sus consultas bypasséan RLS.
- Las migraciones se aplican manualmente en el SQL Editor; que exista un archivo SQL no demuestra que esté aplicado en producción.

### Persistencia actual por dominio

| Dominio | Persistencia actual |
|---|---|
| Identidad | Supabase Auth `auth.users` |
| Perfil de comprador/onboarding | `user_metadata` (`empresa`, `industria`, `rut`, `pais`, etc.) |
| Organizaciones | `organizaciones`, `membresias_organizacion` |
| Cotizaciones | `cotizaciones` |
| Ofertas/resultados | `resultados` |
| Listas multiítem | JSON serializado en `proyectos.descripcion` |
| Proveedores | `proveedores`, `proveedor_contactos` |
| Inteligencia de proveedores | `supplier_capability_events`, `supplier_capabilities` |
| RFQ agrupadas | `rfq_batches`, `rfq_batch_items` |
| Órdenes de compra | `ordenes_compra` |
| Facturas | `facturas` |
| Gmail | `gmail_conversations`, `gmail_messages`, `gmail_attachments`, `item_field_updates` |
| Workflows | `workflow_definitions`, `workflow_roles`, `responsables`, `responsable_roles`, `workflow_instances`, `workflow_events` |
| Búsquedas/feedback | `search_sessions`, `search_feedback` |
| API pública | `api_keys`, `api_usage_log`, `webhooks`, `webhook_logs` |
| MCP | `mcp_connections`, `mcp_audit_log` |
| Documentos | buckets Storage `ordenes-compra` y `boletas` |

### Problemas a resolver

1. **Autorización basada en `user_id` enviado por el cliente.** Muchos routers reciben `user_id` por query/body mientras usan la service key. RLS no protege esas consultas.
2. **Tenant histórico por usuario.** Las organizaciones agrupan usuarios, pero la propiedad material sigue representada por `user_id`/`owner_user_id`.
3. **Datos centrales dentro de JSON.** Las listas reales viven en `proyectos.descripcion`, dificultando consultas, validaciones, concurrencia, API y analítica.
4. **Modelos paralelos o inconclusos.** Existen `proveedores` y `suppliers`; `organizaciones` y `organizations`; el flujo real de listas y el alternativo `quote_items`/`quote_suppliers`; `proyectos` mezcla lista y Gantt.
5. **Datos de empresa en Auth metadata.** El perfil de una compañía no debería depender de metadata flexible de un usuario.
6. **Documentos comerciales con URL pública.** OC y boletas deben migrar a buckets privados y signed URLs.
7. **API/MCP ligados al usuario.** API keys y tokens MCP deben tener organización, scopes y actor verificable.
8. **Esquema productivo no reproducible con certeza.** Hay tablas referenciadas por código que no existen en producción y migraciones aplicadas parcialmente.

---

## 2. Principios obligatorios

1. No crear una segunda base operacional ni introducir MongoDB/Firebase.
2. No hacer una migración big-bang.
3. Toda migración debe ser aditiva, idempotente y tener estrategia de rollback o desactivación.
4. Mantener funcionando el frontend y los flujos actuales durante la transición.
5. No confiar en un `user_id` enviado por navegador, API o MCP.
6. Derivar `actor_user_id` y `organization_id` desde credenciales verificadas.
7. Una entidad de negocio debe tener una única fuente canónica.
8. Usar JSONB para extensiones, snapshots o grafos; no para esconder entidades consultables.
9. Todos los accesos deben quedar limitados por organización, incluso cuando se use service key.
10. No registrar secretos, tokens OAuth, cuerpos sensibles ni PII innecesaria en logs.
11. Toda acción externa o reintentable debe aceptar una clave de idempotencia.
12. Los eventos de auditoría deben ser append-only.

---

## 3. Arquitectura objetivo

```text
Supabase Auth
    └── usuarios
         └── membresías ── organizaciones
                              ├── listas ── ítems
                              │              ├── RFQ/ofertas
                              │              └── órdenes/recepciones/facturas
                              ├── proveedores/contactos/capacidades
                              ├── conversaciones/adjuntos
                              ├── workflows
                              ├── documentos privados
                              └── eventos/auditoría

Frontend ─┐
API v1 ───┼── FastAPI + AuthContext + servicios de dominio ── PostgreSQL/Storage
MCP ──────┘
```

### Contexto de autorización común

Crear una estructura equivalente a:

```python
class AuthContext:
    organization_id: str
    actor_user_id: str
    client_id: str | None
    scopes: set[str]
    request_id: str
```

Debe existir una dependencia FastAPI que:

1. Verifique JWT de Supabase o credencial de integración.
2. Obtenga el usuario autenticado sin confiar en parámetros del request.
3. Resuelva la membresía activa.
4. Determine `organization_id`, rol y scopes.
5. Entregue `AuthContext` a routers y servicios.

Los endpoints públicos con magic links son una excepción controlada: deben validar un token aleatorio, hasheado, expirable, de un solo uso y asociado al recurso exacto.

---

## 4. Modelo canónico propuesto

Los nombres definitivos deben respetar las convenciones del proyecto. Antes de crear tablas, decidir si se conservarán nombres en español o se migrará gradualmente a inglés. **No mantener dos modelos de organización.**

### Identidad y tenancy

- `organizations`
- `organization_memberships`
- `user_profiles`
- `api_clients`
- `api_keys`
- `integration_connections`

Campos mínimos de toda tabla propiedad del cliente:

```sql
organization_id uuid not null
created_at timestamptz not null default now()
updated_at timestamptz
created_by_user_id uuid
updated_by_user_id uuid
```

Cuando corresponda:

```sql
version integer not null default 1
deleted_at timestamptz
external_id text
metadata jsonb not null default '{}'::jsonb
```

### Procurement

- `projects`: proyecto de obra/compra, no una lista serializada.
- `requisition_lists`: solicitud o lista de compra.
- `requisition_items`: cada material/servicio solicitado.
- `rfqs`: proceso de solicitud de cotización.
- `rfq_items`: ítems incluidos.
- `rfq_suppliers`: proveedores invitados y estado de envío.
- `supplier_quotes`: respuesta/cotización de un proveedor.
- `supplier_quote_items`: precio y condiciones por ítem.
- `purchase_orders`: cabecera de OC.
- `purchase_order_items`: líneas de OC.
- `goods_receipts`: recepción conforme/despacho.
- `invoices`: cabecera de factura.
- `invoice_items`: líneas de factura.

### Proveedores y catálogo

- `suppliers`: directorio canónico por organización.
- `supplier_contacts`
- `supplier_addresses`
- `supplier_categories`
- `supplier_capabilities`
- `supplier_capability_events`
- `products`
- `product_aliases`
- `supplier_products`

No fusionar proveedores privados entre clientes sin una decisión explícita de producto y privacidad. Si en el futuro existe un directorio global, separar:

- identidad pública/global del proveedor;
- relación privada organización–proveedor;
- notas, preferencias, bloqueos, contactos y evidencia privada.

### Comunicaciones y documentos

- `conversations`
- `messages`
- `message_attachments`
- `field_extraction_proposals`
- `documents`

`documents` debe guardar metadata, no el binario:

```text
id, organization_id, storage_bucket, storage_path, mime_type,
size_bytes, sha256, document_type, source, status, created_by_user_id
```

Todos los buckets con OC, boletas, facturas y adjuntos deben ser privados. Generar signed URLs breves después de comprobar acceso a la organización.

### Automatización y auditoría

- Mantener `workflow_definitions`, `workflow_instances`, `workflow_events`.
- Agregar o consolidar `domain_events` mediante patrón transactional outbox.
- Consolidar auditoría en `audit_log` con organización y actor.
- Mantener webhooks como suscripciones y entregas separadas.

Evento mínimo:

```text
id, organization_id, event_type, aggregate_type, aggregate_id,
actor_user_id, payload, occurred_at, idempotency_key, schema_version
```

---

## 5. API y MCP

### Regla central

Frontend, API y MCP deben llamar la misma capa de servicios. MCP no debe replicar consultas ni llamar al backend mediante un `localhost` hardcodeado.

Ejemplo:

```python
list_purchase_orders(ctx, filters)
get_supplier(ctx, supplier_id)
create_requisition(ctx, payload, idempotency_key)
search_procurement_history(ctx, query)
```

### API

- Mantener una ruta versionada `/api/v1`.
- API keys vinculadas a `organization_id` y `api_client_id`.
- Guardar sólo hashes de keys.
- Scopes granulares.
- Paginación por cursor.
- Filtros explícitos y límites máximos.
- Idempotency-Key en POST críticos.
- Webhooks firmados con HMAC, timestamp, reintentos y dead-letter.
- OpenAPI como contrato publicado.

Scopes iniciales:

```text
suppliers:read suppliers:write
requisitions:read requisitions:write
quotes:read quotes:write
purchase_orders:read purchase_orders:write
invoices:read
analytics:read
organization:admin
```

### MCP

- Tokens asociados a usuario, organización, cliente y scopes.
- Validar scopes en cada tool, no sólo al emitir el token.
- Códigos OAuth y refresh tokens persistentes o administrados por infraestructura adecuada; no usar memoria del proceso en producción.
- Refresh token distinto del access token, rotatorio y revocable.
- Registrar invocación, actor, organización, tool, duración y resultado resumido.
- Nunca incluir tokens ni contenido sensible completo en `mcp_audit_log`.

---

## 6. Plan de ejecución

### Fase 0 — Auditoría y cierre de seguridad

Entregables:

1. Script SQL/read-only que inventaríe tablas, columnas, constraints, índices, RLS, policies, buckets y conteos por tabla en producción.
2. Matriz `tabla → existe en prod → dueño → RLS → router → estado de uso`.
3. Inventario de endpoints que reciben `user_id` desde el cliente.
4. Clasificación de endpoints: autenticado, API key, MCP, magic link, público deliberado.
5. Diseño de `AuthContext` y middleware/dependencias.
6. Plan específico para buckets privados.

Criterios de aceptación:

- Ningún endpoint privado nuevo confía en `user_id` del request.
- Existe una prueba que intenta leer datos de otra organización y recibe 403/404.
- Se conoce con evidencia qué migraciones/tablas existen realmente.
- No se hacen cambios de esquema destructivos.

### Fase 1 — Organización como tenant real

Entregables:

1. Elegir y documentar el modelo canónico entre `organizaciones` y `organizations`.
2. Agregar `organization_id` de forma nullable inicialmente a tablas de negocio.
3. Backfill determinístico desde membresías/owner histórico.
4. Agregar índices por `organization_id` y claves de consulta frecuentes.
5. Hacer `organization_id NOT NULL` sólo después de validar el backfill.
6. RLS por organización.
7. API keys, conexiones MCP y webhooks vinculados a organización.
8. Mantener `user_id` temporalmente como actor/compatibilidad, con fecha o condición de retiro.

Criterios de aceptación:

- Dos miembros de una organización ven los mismos datos autorizados.
- Un miembro de otra organización no puede leerlos ni modificarlos.
- Backend, API y MCP aplican el mismo límite de tenant.
- Todas las queries principales tienen índice compatible con el filtro organizacional.

### Fase 2 — Normalización de listas

Entregables:

1. Crear tablas canónicas de listas e ítems.
2. Migrar el contenido de `proyectos.descripcion` conservando IDs y `cotizacion_id`.
3. Implementar dual-read o adapter temporal.
4. Implementar dual-write controlado sólo si es necesario y con reconciliación.
5. Comparar JSON antiguo con filas nuevas usando checks automáticos.
6. Cambiar gradualmente frontend y servicios al modelo normalizado.
7. Mantener snapshot JSON temporal para rollback, no como fuente primaria.

Criterios de aceptación:

- Se puede consultar por SQL cada ítem, cantidad, unidad, estado y selección.
- El flujo de crear lista, buscar, comparar, RFQ, aprobar y comprar continúa funcionando.
- No cambia el resultado visible de listas históricas.
- Existe verificación de reconciliación antes de retirar la lectura antigua.

### Fase 3 — Consolidación de modelos

Resolver explícitamente:

- `proveedores` versus `suppliers`;
- `organizaciones` versus `organizations`;
- listas reales versus `quote_items`/`quote_suppliers`;
- proyecto/lista versus Gantt;
- `recurrencia_logs` versus `recurrencias_log`;
- tablas referenciadas pero inexistentes.

Para cada modelo duplicado producir una decisión:

```text
KEEP / MIGRATE / DEPRECATE / DELETE LATER
```

No borrar tablas en esta fase. Marcar código deprecado, dejar métricas de uso y definir una migración posterior.

#### Decisiones ya ejecutadas

**2026-08-24 — `quote_items` / `quote_suppliers` / `purchase_events` / `procurement_ledger`: DELETE.**

Se eliminó el código, no tablas: **las cuatro nunca existieron en producción** (verificado con
consultas reales contra la DB, no leyendo `backend/migrations/`; vienen de las migraciones 013 y 014,
aplicadas sólo a medias). Por lo tanto no hay datos que migrar ni rollback de esquema que definir.

Se borraron `backend/app/routers/procurement.py` (14 endpoints), `backend/app/routers/ledger.py`
(4 endpoints), `frontend/app/procurement/` y la rama `quote_supplier:` de `aprobaciones.py`, que era
inalcanzable. Nada importaba esos módulos, ninguna pantalla enlazaba a `/procurement`, y sus endpoints
respondían 500.

Motivo de ejecutarlo ahora y no como "DELETE LATER": eran 18 de las 20 rutas que todavía quedaban sin
autenticar tras el cierre del borde HTTP (ver la sección de aislamiento en `CLAUDE.md`). Asegurar
código muerto contra tablas inexistentes era mantenimiento puro. El ciclo de compra real —listas →
RFQ → autorización → OC → despacho, con las migraciones 041-045 aplicadas— ya reemplazó
funcionalmente a ese modelo: no es una feature pendiente, es una descartada.

### Fase 4 — API/MCP de datos

Entregables:

1. Servicios de dominio compartidos.
2. API v1 sobre entidades canónicas.
3. MCP tools llamando servicios, no endpoints localhost.
4. Scopes e idempotencia.
5. Cursor pagination y límites.
6. Webhooks confiables.
7. Auditoría consistente.
8. Documentación y ejemplos por organización.

Criterios de aceptación:

- La misma identidad recibe resultados equivalentes desde UI, API y MCP.
- Ningún canal puede saltarse scopes o tenancy.
- Revocar una API key o conexión MCP corta el acceso.
- Las operaciones reintentadas no crean duplicados.

### Fase 5 — Plataforma analítica

No comenzar hasta medir necesidad real.

- Outbox/eventos para cambios de dominio.
- Exportación CDC o incremental a un warehouse.
- Modelos analíticos para gasto, ahorro, desempeño, cobertura y tiempos.
- Datos sensibles clasificados y minimizados.
- Retención, exportación y eliminación por organización.
- Backups y simulacros de restauración.

---

## 7. Índices y rendimiento

Evitar índices aislados sólo por `organization_id` cuando las consultas reales filtran y ordenan por más campos. Evaluar índices compuestos como:

```sql
(organization_id, created_at desc)
(organization_id, status, created_at desc)
(organization_id, supplier_id)
(organization_id, external_id)
(organization_id, normalized_name)
```

Usar `EXPLAIN (ANALYZE, BUFFERS)` con datos representativos antes de agregar índices masivos. Definir paginación por cursor para colecciones que crecerán y evitar `offset` alto.

Particionar eventos sólo cuando las métricas lo justifiquen. El particionamiento prematuro aumenta complejidad.

---

## 8. Privacidad, seguridad y gobierno

- Clasificar RUT, emails, teléfonos, mensajes, facturas y boletas como datos sensibles.
- Cifrar tokens OAuth en reposo o moverlos a un gestor de secretos adecuado.
- Definir retención de mensajes y adjuntos.
- Signed URLs breves para archivos.
- Auditoría para lecturas administrativas y exportaciones.
- Borrado de organización con período de gracia y proceso verificable.
- Exportación completa y portable de datos del cliente.
- Logs sin cuerpos completos de correos, tokens ni documentos.
- Rotar las credenciales que fueron expuestas durante desarrollo, según `CLAUDE.md`.

---

## 9. Observabilidad y operación

Agregar métricas por organización, sin exponer datos sensibles:

- Requests y errores por endpoint/tool.
- Latencia p50/p95/p99.
- Consultas lentas.
- Tamaño y crecimiento de tablas.
- Fallos y reintentos de webhooks.
- Jobs Gmail atrasados.
- RFQ en estado ambiguo.
- Eventos outbox pendientes.
- Uso de Storage.
- Consumo de IA y costo estimado.

Todo request debe recibir un `request_id` trazable entre FastAPI, eventos, auditoría, webhooks y MCP.

---

## 10. Archivos iniciales a revisar

- `CLAUDE.md`
- `backend/app/services/supabase.py`
- `backend/app/services/organizacion.py`
- `backend/app/routers/organizacion.py`
- `backend/app/routers/listas.py`
- `backend/app/routers/cotizaciones.py`
- `backend/app/api_publica/auth.py`
- `backend/app/api_publica/`
- `backend/app/mcp/oauth.py`
- `backend/app/mcp/transport.py`
- `backend/app/mcp/tools/`
- `backend/migrations/011_mcp.sql`
- `backend/migrations/012_api_publica.sql`
- `backend/migrations/013_procurement_flow.sql`
- `backend/migrations/014_smart_procurement.sql`
- `backend/migrations/019_gmail_agent.sql`
- `backend/migrations/024_supplier_capability_intelligence.sql`
- `backend/migrations/026_rfq_batches.sql`
- `backend/migrations/027_workflow_builder.sql`
- `backend/migrations/028_capo_control_plane.sql`
- `backend/migrations/030_organizaciones.sql`
- `backend/migrations/031_rls_organizacion.sql`

Hay trabajo no relacionado sin commitear en el repositorio. No sobrescribirlo ni revertirlo.

---

## 11. Primera tarea solicitada a Claude Code

Antes de implementar, realizar únicamente una fase de diagnóstico y diseño:

1. Leer `CLAUDE.md` completo.
2. Revisar los archivos de la sección anterior.
3. No asumir que una migración está aplicada por existir en disco.
4. Preparar una consulta read-only para inspeccionar el esquema real de Supabase.
5. Crear una matriz del modelo actual y señalar:
   - fuente canónica;
   - duplicados;
   - tablas inexistentes;
   - JSON que debe normalizarse;
   - endpoints con autorización insegura;
   - dependencias y orden de migración.
6. Proponer un ADR para el modelo organizacional canónico.
7. Proponer el contrato de `AuthContext`.
8. Diseñar las migraciones de Fase 0 y Fase 1, sin aplicarlas.
9. Entregar riesgos, rollback, pruebas y criterios de aceptación.
10. Esperar aprobación antes de modificar código o ejecutar SQL en producción.

### Formato esperado de la respuesta

```text
1. Hallazgos confirmados
2. Incertidumbres que requieren consulta real
3. Riesgos de seguridad priorizados
4. Modelo canónico recomendado
5. ADR de organizaciones
6. AuthContext y flujo de autorización
7. Plan de migraciones numeradas
8. Plan de backfill y reconciliación
9. Plan de pruebas
10. Rollback
11. Estimación por fases
12. Decisiones que requieren aprobación humana
```

## Definición global de terminado

La iniciativa estará terminada cuando:

- La organización sea el tenant real de todas las entidades de negocio.
- El backend no confíe en `user_id` controlado por el cliente.
- RLS y servicios apliquen aislamiento consistente.
- Las listas e ítems sean consultables relacionalmente.
- Exista un único modelo canónico por dominio.
- API y MCP compartan servicios, scopes, idempotencia y auditoría.
- Los documentos comerciales sean privados.
- Haya migración reconciliable, observabilidad, backup y rollback documentados.
- Se pueda exportar de forma segura toda la información de una organización.

