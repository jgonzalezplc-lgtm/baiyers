# CLAUDE.md — Baiyer (Cotizador Inteligente B2B)

Contexto de proyecto para retomar en cualquier sesión. Léelo antes de trabajar.

## Qué es
**Baiyer** — plataforma de procurement/cotización B2B para Chile. El usuario describe qué
necesita comprar (texto natural o foto), la IA lo identifica y categoriza, busca proveedores
(scrapers de tiendas chilenas + MercadoLibre + Google Shopping vía Serper), compara precios,
cotiza por correo y genera órdenes de compra. Incluye onboarding inteligente que detecta la
empresa desde el correo, listas multi-ítem, proyectos con Gantt, y un módulo de proyectos/materiales.

## Stack y despliegue
- **Backend:** FastAPI (Python 3.11), carpeta `backend/`, Dockerfile (usa `$PORT`). Prod en Railway.
- **Frontend:** Next.js 16 App Router (TS), carpeta `frontend/`. Prod en Railway (escucha en 8080 interno).
- **DB + Auth:** Supabase (project ref `zsssebwpnmsiklzwbrxh`, región us-west-2).
- **Dominio:** `www.baiyer.cl` → Cloudflare (DNS) → Railway. SSL emitido.
- **Repo:** github.com/jgonzalezplc-lgtm/baiyers (público). Push a `main` → Railway auto-deploya ambos servicios.
- **Railway:** plan Hobby (~$5-10/mes). Proyecto **`genuine-connection`** con 2 servicios: `baiyers` (backend, root `backend`) y `sweet-trust` (frontend, root `frontend`). Hay un proyecto huérfano `bountiful-presence` que conviene borrar (falla builds y manda correos).

## Comandos
```bash
# Backend local
cd backend && .venv/bin/uvicorn app.main:app --port 8000 --host 127.0.0.1
# Frontend local
cd frontend && npm run dev            # localhost:3000
# Verificar que backend importa
cd backend && .venv/bin/python -c "import app.main"
# Type-check frontend (build real ignora errores TS por config)
cd frontend && npx tsc --noEmit
```

## Convenciones
- **Estilo Swiss:** IBM Plex Mono, acento `#c0392b`, `border-radius: 0`. Usa variables CSS (`var(--accent)`, `var(--bg-surface)`, `var(--text-primary)`, etc.). Botones `.btn-swiss-primary` / `.btn-swiss-secondary`, chips `.label`.
- **Idioma:** UI y comentarios en español.
- **Commits:** terminar con `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`. Commit/push solo cuando corresponde; `main` es la rama de deploy.
- El build de Next **ignora errores de TS/lint** (`next.config.js`: `ignoreBuildErrors`/`ignoreDuringBuilds`) — hay deuda de tipos pre-existente. No confíes en el build para atrapar tipos; corre `tsc --noEmit`.

## Arquitectura del backend (routers clave en `backend/app/routers/`)
- `identificar.py` — IA (Gemini) separa el prompt en ítems, asigna **categoría por ítem**, genera términos ES/EN. Detecta proyectos (`es_proyecto`) → lista de materiales. Acepta `industria_empresa` como contexto.
- `buscar.py` — orquesta búsqueda en paralelo: `_ml_query` (MercadoLibre), `_google_query` (→ Serper.dev si `SERPER_API_KEY`, sino SerpAPI), scrapers de tiendas, electrónica. `_marcar_relevancia` filtra basura. `/buscar` (batch) y `/buscar/stream` (SSE, lo usa el frontend). `/buscar/prefetch` para listas.
- `onboarding.py` — `investigar-empresa`: desde dominio o nombre, con Gemini + scraping, devuelve empresa/industria/país/logo/RUT/dirección/categorías. Además, sesión conversacional persistida (`POST /api/onboarding/sesion`, `/turno`, `/confirmar`, `/logo/candidato`, `/logo/subir`) — ver sección "Onboarding conversacional" más abajo.
- `mail_templates.py` — API de plantillas de correo versionadas por organización (ver sección "Plantillas de correo" más abajo).
- `contacto.py` + `services/contacto_scraper.py` — al cotizar, scrapea email + WhatsApp del proveedor y arma mensaje pre-hecho (`wa.me`).
- `cuenta.py` — `/api/cuenta/eliminar` (darse de baja; verifica token, borra usuario auth).
- `listas.py` — listas de cotización multi-ítem (guardadas como JSON en `proyectos.descripcion`; lock por lista). **Es el sistema real y en uso** para proyectos multi-ítem — no confundir con `proyectos.py` (Gantt, tablas `items_proyecto`/`cotizaciones_proyecto`, existen pero con 0 filas reales) ni con `procurement.py` (`quote_items`/`quote_suppliers`/`purchase_events`, **tablas que no existen en producción** — ver Gotchas). Cada ítem de una lista ya tiene identidad estable real: `it.cotizacion_id` es una fila propia de `cotizaciones`, no depende de su posición en el JSON.
- `procurement_profile.py` / `search_feedback.py` — Fase 1 de Supplier Capability Intelligence (ver sección dedicada más abajo).
- Otros: `cotizaciones`, `oc`, `aprobaciones`, `proyectos` (Gantt, sin uso real), `analisis` (IA), `gmail`, `facturas` (parser de correos entrantes), `procurement` (roto, ver Gotchas), `ledger`, `recurrencias`, `estadisticas`, `chat`, `historico`, `suppliers`, `proveedores_import`, `notificaciones`, MCP + API pública.

### Agente de Gmail
- Migraciones **019, 020 y 021 aplicadas en producción**: conversaciones/mensajes/adjuntos/propuestas, contactos multi-proveedor y etapa `compra_iniciada`.
- `services/cron.py` llama `sincronizar_todos_los_usuarios()` cada **1 minuto**. El agente trae mensajes del hilo, interpreta el cuerpo con Gemini, asocia proveedor/contacto, guarda metadata de adjuntos y auto-aplica campos core con confianza `>= 0.85`.
- Mapeo real hacia `resultados`: `precio_unitario → precio_cotizado`, `moneda → moneda_cotizada`, `plazo_entrega → plazo_entrega`, `condiciones_pago → condiciones_pago`; disponibilidad queda en `notas_respuesta`. El estado válido es **`respondido`** y el timestamp es `respuesta_recibida_at`.
- Si faltan campos, envía seguimiento; si recibe todo, envía agradecimiento y cierra. Al aprobar una lista **sin observaciones**, `aprobaciones.py` llama `iniciar_proceso_compra()` por cada resultado definitivo asociado a Gmail; es idempotente y cambia la conversación a `compra_iniciada`.
- UI: `/conversaciones` muestra actividad/propuestas y permite sincronización manual; `/conversaciones/[id]` permite aplicar/rechazar propuestas; el comparador permite agregar un proveedor del directorio.
- El contenido de PDF/Excel adjunto todavía **no se parsea**: sólo se guarda metadata en `gmail_attachments`. El webhook Gmail Pub/Sub sigue siendo stub; producción usa polling.

### Ruteo por categoría (`services/categoria_mapper.py`)
Cada categoría → set de fuentes. **carpinteria** = maderas + retail construcción (SIN eléctrico). **construccion/mecanico/consumible** sin eléctrico. **electrico/electronica** = electrónica + eléctrico CL. Fuentes de madera tienen gate de keywords (se auto-filtran). **Pendiente:** el bucket electrónica/eléctrico aún mezcla componentes (arduino) con materiales eléctricos (cables) — falta afinar.

### Matching de relevancia (`services/relevancia.py`)
Descarta derivados/accesorios (ej: "barniz de madera" al buscar tablones) con negativas por categoría + patrón "X para <ítem>".

### Fuentes de scraping (`services/fuentes/`)
`retail_cl.py` (Sodimac, Easy, La Sierra, Construmart, Vitel, Dartel, Ferrelectrica, Gobantes, Rhona), `maderas_cl.py` (CLC, W Maderas, Ferramenta + directorio aserraderos con gate de keywords), `mouser/digikey/tme`. **Arquitectura hardcodeada** — pendiente convertir a registro data-driven. Vitel/Construmart (Magento GraphQL) usan `sku` como respaldo de URL cuando falta `url_key`, para que dos productos distintos nunca compartan `url=""` (ver Gotchas — esto rompía la selección del comparador).

### Supplier Capability Intelligence (Fases 1-7, todas completas — ver "Estado verificado" abajo)
Evolución hacia "qué proveedor abastece qué categoría", auditable y por usuario (sin aprendizaje compartido entre clientes todavía). Diseño original en `PROMPT_CLAUDE_CODE_SUPPLIER_INTELLIGENCE.md` (raíz del repo, no tocar). Las 7 fases quedaron implementadas y commiteadas (`6b7f92c` → `9b91094`); detalle de cada una en la sección "Estado verificado".
- `services/supplier_capability_intelligence.py` — `PESOS` por tipo de evento (ajustable), `registrar_evento()`/`registrar_evento_para_resultado()` (idempotentes), `recalcular_capacidad()` (determinístico: suma de pesos clamped a [0,1], **siempre recalculada desde los eventos, nunca incrementada in-place**), `rankear_proveedores()` (excluye bloqueados y categorías `rejected`, explica el porqué).
- `services/procurement_profile.py` — perfil de compra por usuario, generado al completar el onboarding, con señales de uso que descubren categorías nuevas.
- **Pendiente real:** probar Fase 1 con datos de producción de punta a punta (perfil/sesiones/feedback nunca se verificaron con un usuario real, solo con fake in-memory).

### Workflow Builder de compras/autorizaciones (fundación + conversacional + canvas + motor real conectado — completo)
Reemplaza gradualmente el "Proceso de compra" (texto libre) + "Email del autorizador" (un solo email fijo) de `/settings` por un motor de reglas real (roles, responsables, condiciones por monto, secuencial/paralelo). **No reemplaza `approval_workflows`/`approval_requests`** (siguen siendo la fuente real del magic link de autorización) — este workflow decide CUÁNDO y A QUIÉN corresponde disparar esa autorización. Diagnóstico completo (qué se reutiliza, deuda encontrada, modelo canónico) solo en el historial de la conversación que lo diseñó, no está en un archivo.
- **Migraciones `027_workflow_builder.sql`, `029_workflow_autorizacion_real.sql`, `030_organizaciones.sql`, `031_rls_organizacion.sql` — aplicadas y confirmadas.** `workflow_definitions` (versionado borrador→activo→archivado, `nodos`/`conexiones` en JSONB), `workflow_roles`, `responsables` (personas reales, con suplente opcional), `responsable_roles` (N:M), `workflow_instances`, `workflow_events` (log inmutable); 029 conecta `approval_requests` al workflow real (`workflow_instance_id`/`workflow_nodo_id`/`responsable_id`); 030/031 son la fundación de organizaciones multi-usuario (`organizaciones`, `membresias_organizacion`) de la que depende todo lo de acá.
- `services/workflow_engine.py` — motor puro, sin DB: `validar_grafo()`, `siguiente_nodo()` (determinista), `evaluar_condicion()` (**sin `eval`**), `resolver_autorizadores()` (secuencial/paralela), `procesar_evento()` (idempotente).
- `services/workflow_conversational.py` — `interpretar_descripcion()` (Gemini traduce texto libre a ETAPAS, nunca arma el grafo directamente) + `compilar_a_grafo()` (compilador puro y determinístico, reutiliza `validar_grafo`).
- `services/workflow_service.py` — persistencia de borradores/versiones/responsables. `services/workflow_execution.py` — **el puente real**: `iniciar_autorizacion_workflow()` (llamado desde `listas.py` en `solicitar_aprobacion`) resuelve autorizadores reales del ciclo activo y decide a quién notificar; si no hay ciclo activo, cae al flujo legado de un solo `aprobador_email`. **Esto ya está conectado en producción** — no es un pendiente.
- **`/settings/autorizaciones/canvas/[id]/page.tsx` — el canvas visual SÍ existe** (drag-and-drop de nodos, SVG para conexiones, panel de propiedades, asignación de responsables por rol con dropdown "elegir existente" que asigna al instante + toast de confirmación). No es un pendiente.
- Endpoints en `routers/workflows.py`: `POST /api/workflows/interpretar`, `POST/GET /api/workflows`, `GET/PUT /api/workflows/{id}`, `GET /api/workflows/{id}/validar`, `POST /api/workflows/{id}/activar`, `/api/workflows/responsables*`. Migrados a `Depends(get_auth_context)` (ya no confían en `user_id` del body/query).
- **Pendiente real:** ficha visual de responsables más rica, homologación de proveedores.

## Auth & Onboarding (frontend)
- Login/registro: **email/password + Google OAuth** (funcionan). Outlook **oculto** (`{false && ...}` en login/register) — Azure AD requiere cuenta Microsoft de trabajo.
- Callback OAuth: `frontend/app/auth/callback/page.tsx` es **client-side** (evita el host interno `localhost:8080` del proxy). Signout: `app/auth/signout/route.ts`.
- Onboarding: `frontend/components/OnboardingChat.tsx` (usado en `/onboarding` y flotando en `OnboardingFloating.tsx`) — chat conversacional NLP (ver sección dedicada abajo), ya no es una máquina de fases con regex.
- Dashboard saluda con logo+nombre; búsquedas usan `industria` como contexto.

## Onboarding conversacional (Fases 1-3 del proyecto de onboarding/workflow/mailing — completo)
Reemplazó la máquina de fases con regex (pedir_nombre → rut → nombre_usuario → logo → proceso) por
extracción tolerante a lenguaje natural, fuera de orden y con correcciones. **Migraciones `034_onboarding_organizacion_perfil.sql` y `035_organizacion_direccion.sql` — aplicadas y confirmadas.**
- Perfil organizacional real en `organizaciones` (`rut`, `rut_confianza`, `logo_url`, `logo_storage_path`,
  `logo_origen`, `sitio_web`, `industria`, `pais`, `direccion`) — ya no vive solo en `user_metadata`
  (se mantiene un backfill no destructivo hacia `user_metadata` para no romper el resto de la app que
  todavía lee de ahí). RUT único vía índice parcial; un RUT duplicado es conflicto manual, nunca fusión
  automática de organizaciones.
- `onboarding_sessions` — sesión persistida y reanudable (`draft` por campo con
  valor/confianza/origen/confirmado, `mensajes`, `propuesta_workflow`). Se puede recargar la página a
  mitad de la conversación sin perder el progreso.
- `services/onboarding_conversational.py` — Gemini SOLO propone valores para los campos mencionados en
  el turno; toda decisión (qué queda confirmado, validación de RUT módulo 11, montos coloquiales tipo
  "500 lucas") es código Python determinístico, nunca el modelo. Reusa
  `workflow_conversational.interpretar_descripcion()` tal cual sobre el texto acumulado del proceso de
  compra — no lo reimplementa.
- `services/rut.py` — validador chileno real (dígito verificador módulo 11), sin dependencias.
- `services/logo_upload.py` — protección SSRF real al descargar un logo candidato (sin redirects,
  resuelve DNS y rechaza IPs privadas/loopback antes de conectar, valida `content-type`/tamaño).
- El onboarding, una vez que interpreta el proceso de compra, **crea el workflow real** (no solo
  preview): reusa `PropuestaWorkflowCard`/`WorkflowGuardadoCard` (`frontend/components/workflow/`,
  compartidos con `/settings/autorizaciones`) para crear el borrador, invitar responsables (solo si el
  usuario deja el checkbox marcado) y activar — mismos endpoints de `workflows.py`, ningún endpoint
  nuevo hizo falta para esto.
- **Pendiente:** `onboarding_sessions` no guarda el `workflow_id` creado a mitad de camino (deuda
  menor); overrides de plantilla por nodo del canvas no expuestos en la UI de onboarding.

## Plantillas de correo (Fases 4-6 del mismo proyecto — completo, ver también sección de arriba)
Antes cada correo transaccional (RFQ, aprobación, OC, seguimientos) tenía asunto/cuerpo hardcodeado
con f-strings repartidos en 5 archivos — sin versionado, sin override por organización. **Migración
`036_mail_templates.sql` — aplicada y confirmada.**
- `mail_template_definitions`/`mail_template_versions`/`mail_delivery_events` guardan SOLO overrides
  — el contenido default de cada uno de los **16 eventos** (7 internos de autorización + 9 externos de
  proveedores) vive en Python (`services/mail_events.py`), así que una organización sin overrides sigue
  recibiendo el correo de siempre. Precedencia nodo > workflow > organización > default.
- `services/mail_template_service.py` — reemplazo de placeholders `{{variable}}` por regex con
  allowlist por evento, **deliberadamente sin Jinja2 ni `eval`** (no hace falta lógica condicional para
  asunto/cuerpo de correo). Variable no declarada no se puede guardar; variable faltante al renderizar
  lanza antes de "enviar"; `preview()` nunca escribe en DB; `restaurar_default()` crea una versión
  nueva, nunca borra historial; `registrar_envio()` es idempotente por `idempotency_key`.
- `routers/mail_templates.py` — CRUD con `Depends(get_auth_context)`; editar/restaurar exige
  `ctx.es_admin`.
- `/settings/comunicaciones` (frontend) — lista los 16 eventos por audiencia, editor con variables
  insertables por clic, preview con datos de ejemplo, guardar/restaurar. Sin generación de borradores
  por IA (fuera de alcance a propósito).
- **Emisores reales migrados (5 de 8 sitios candidatos):** `listas.py` (2 sitios, `approval_requested`),
  `oc.py` (`enviar_oc`, solo el correo al proveedor, `purchase_order_sent`),
  `recurrencia_service.py` (`rfq_requested`), `gmail_conversation_agent.py` (`rfq_received_thanks`/
  `rfq_missing_information`, con fallback al texto exacto de antes si el renderer falla, porque es un
  envío automático sin revisión humana). **3 sitios quedaron fuera a propósito** (no forzar mal
  mapeo): la copia interna de "OC enviada" y el aviso de "proveedor confirmó recepción" en `oc.py`, y
  la encuesta de satisfacción post-compra en `cron.py` — ninguno de los 16 eventos les queda bien.
- **Pendiente:** lógica de bloqueo/dedup pre-envío (hoy `registrar_envio()` es solo auditoría, un
  reintento todavía puede duplicar un correo); overrides de plantilla a nivel workflow/nodo sin UI
  (el modelo ya lo soporta); eventos de recordatorio (`approval_reminder`,
  `purchase_order_ack_reminder`, etc.) sin ningún cron/scheduler que los dispare todavía.

## Branding organizacional en documentos (OC e informes)
`OCPDFTemplate.tsx` y `ReporteTemplate.tsx` (ambos con `@react-pdf/renderer`, 100% frontend, no hay
generación de PDF en el backend) mostraban "Claria" hardcodeado. Ahora leen el perfil real de la
organización (`obtener_perfil_organizacion()` en `services/organizacion.py`, reusado por
`POST /api/oc/crear` y `POST /api/reportes/datos`): logo (imagen si existe, texto si no), nombre, RUT y
dirección, con fallback genérico "Baiyer" solo si la organización todavía no tiene perfil configurado.

## Gotchas importantes
- **Migraciones = manuales.** El service key de Supabase NO hace DDL, y no hay `DATABASE_URL` para conexión directa — Claude Code prepara el `.sql` y lo copia al portapapeles (`pbcopy`), pero el usuario lo pega y ejecuta en el SQL Editor de Supabase. Aplicadas y **confirmadas contra la DB real**: 019–021 agente Gmail, 022 notificaciones, 023 seguimiento de OC por correo, 024 Supplier Capability Intelligence, 025 ficha de proveedores, 026 `rfq_batches`, 027 Workflow Builder, 029 workflow↔aprobación real, 030 organizaciones, 031 RLS organizacional, **034 perfil organizacional + `onboarding_sessions`, 035 `direccion`, 036 plantillas de correo** (estas 3 confirmadas en esta sesión). Estado de 028 (capo control plane, de otra sesión), 032 (mcp oauth state) y 033 (supplier_ratings) no reverificado en esta sesión — no asumir sin chequear.
- **Bug real de `postgrest-py` 2.x encontrado en producción:** `.maybe_single().execute()` devuelve `None` directamente (no un objeto con `.data = None`) cuando la consulta no matchea ninguna fila — cualquier `.execute().data` sin chequear `None` antes crashea con `AttributeError`. Encontrado en `resolver_organizacion()` (rompía dashboard/listas/gmail/workflows enteros para cualquier usuario sin fila en `membresias_organizacion`) y corregido ahí y en `onboarding_session.obtener_sesion()`. **Quedan ~50 ocurrencias más del mismo patrón sin auditar** en `gmail.py`, `listas.py`, `cotizaciones.py`, `rfq.py`, `proveedores.py`, `workflow_service.py`, etc. — antes de escribir `.maybe_single().execute().data`, envolver en un chequeo de `None` (ver `_maybe_single()` en `mail_template_service.py` como ejemplo del patrón correcto).
- **`get_auth_context` ahora autocrea la organización si falta** (usuarios registrados después del backfill de la 030 no tenían fila en `membresias_organizacion` y quedaban bloqueados con 403 en TODO endpoint protegido) — usa la misma red de seguridad que ya tenía `obtener_organizacion()` para `/api/organizacion/mia`.
- **Tablas referenciadas en código que NO EXISTEN en producción (confirmado con `sb.table(x).select('*').limit(1)` contra la DB real, no contra los `.sql`):** `supplier_categories` y `procurement_ledger` (de `014_smart_procurement.sql`, migración numerada pero aplicada solo a medias — `approval_workflows`/`approval_requests`/`recurrencia_logs` de ese mismo archivo sí existen), `quote_items`/`quote_suppliers`/`purchase_events` (de `013_procurement_flow.sql`, usadas por `procurement.py` — **el botón "+ Lista" en `/cotizar/[id]/resultados` llama a `POST /api/procurement/eventos` y hoy tira 500**), `supplier_ratings`/`rating_pendiente` (usadas por `supplier_intelligence.py` y `POST /api/suppliers/rating` — fallan en silencio o 500). Ningún numero de migración garantiza que esté realmente en prod: **antes de asumir que una tabla existe, verificar con una query real**, no solo mirar `backend/migrations/`.
- **Orden de auto-aplicación Gmail:** hoy `item_field_updates` se inserta como `aplicado` antes de actualizar `resultados`. Si el segundo paso falla, la auditoría puede decir “Aplicada” sin que el dato exista. Esto ocurrió en datos antiguos y sigue siendo un riesgo del código actual; conviene hacer la escritura atómica o marcar `aplicado` sólo después del update exitoso.
- **Estado de conexión Gmail:** el dashboard debe consultar `/api/gmail/status`; no inferir la conexión desde `?gmail=conectado`, porque ese query param sólo existe inmediatamente después del callback OAuth. Al reconectar, conservar el `refresh_token` persistente si Google no devuelve uno nuevo.
- **credentials.json** (OAuth Gmail) está **gitignored** — en prod se usan env vars `GOOGLE_CLIENT_ID`/`GOOGLE_CLIENT_SECRET`.
- **SMTP:** Resend configurado en Supabase (dominio baiyer.cl verificado). Correos de auth (confirmación/recuperación) salen desde `no-reply@baiyer.cl`.
- **Serper.dev** integrado (2.500 búsquedas gratis; `SERPER_API_KEY`). Prioriza sobre SerpAPI.
- Secretos expuestos en capturas durante el desarrollo (Supabase service key, Gemini, SerpAPI, Serper) — **rotar** por higiene.

## Env vars
- **Backend (Railway `baiyers`):** SUPABASE_URL, SUPABASE_SERVICE_KEY, GEMINI_API_KEY, SERPER_API_KEY, SERP_API_KEY, ANTHROPIC_API_KEY (vacío), ENVIRONMENT=production, CORS_ORIGINS (incluye baiyer.cl + railway), FRONTEND_URL=https://www.baiyer.cl, GOOGLE_CLIENT_ID/SECRET, GOOGLE_REDIRECT_URI.
- **Frontend (Railway `sweet-trust`):** NEXT_PUBLIC_SUPABASE_URL, NEXT_PUBLIC_SUPABASE_ANON_KEY, NEXT_PUBLIC_API_URL=https://baiyers-production.up.railway.app.

## Costos infra
Railway ~$5-10/mes · Supabase free · Serper 2.500 gratis→$50/50k · Gemini free tier. WhatsApp y SII (futuros) sí cuestan.

## Estado verificado (10-ago-2026)
- `frontend/next-env.d.ts` sigue siendo el único cambio preexistente del worktree — se conserva sin commitear (es autogenerado por Next.js en dev).
- Sesión larga de fixes ya en `main`/deployados: campanita de notificaciones (migración 022 aplicada), correo de autorización con un solo link, envío de OC por Gmail con seguimiento de acuse de recibo/despacho por correo (**migración 023 aplicada y confirmada**), fix de selección de ofertas duplicadas en el comparador (bug real: elegir una oferta de Vitel con `url` vacía marcaba varias como seleccionadas — corregido con un id propio `_uid` por resultado en vez de usar `url`, más la causa raíz en el scraper), limpieza de markdown en el correo de cotización generado por Gemini, migración de `OCModal` al design system actual.
- **Supplier Capability Intelligence, Fase 1**: código completo, **migración 024 aplicada y confirmada**. Probado con fake in-memory; falta probar los endpoints reales end-to-end con datos de producción.
- **Supplier Capability Intelligence, Fase 3**: alta e investigación de proveedores, ficha editable y categorías manuales completa; **migración 025 aplicada y confirmada**. Commit `6b7f92c` en `main`.
- **Supplier Capability Intelligence, Fase 4**: matriz editable proveedor–ítem en `/listas/[id]/proveedores-confianza`, ranking por capacidad privada + preferencia + score, selección persistida dentro del JSON de la lista, cobertura accesible, warnings y explicaciones. No envía correos ni registra evidencia hasta confirmar la RFQ en Fase 5. No requiere migración. Commit `6e26b6c` en `main`.
- **Supplier Capability Intelligence, Fase 5**: migración 026 crea `rfq_batches`/`rfq_batch_items` (**aplicada y confirmada en producción**); preparación idempotente desde la matriz, revisión editable en `/listas/[id]/rfq`, un correo Gmail por proveedor con varios ítems, una conversación asociada a múltiples resultados y protección `delivery_uncertain` para no duplicar envíos ambiguos. El agente Gmail resuelve el batch a todos sus resultados y marca cada ítem respondido. Commit `6e26b6c` en `main`.
- **Supplier Capability Intelligence, Fase 6**: `/listas/[id]/busqueda-complementaria` separa ítems sin cobertura de los ya cubiertos, prioriza los primeros y exige acción explícita para buscar alternativas de los segundos. El buscador existente acepta `busqueda_expandida`, consulta todas las fuentes, crea una sesión `expanded` enlazada a la última dirigida y registra feedback idempotente `missing_suppliers`. No requiere migración. Commit `983c79d` en `main`.
- **Supplier Capability Intelligence, Fase 7**: continuidad completa sobre el flujo existente. Las respuestas Gmail (autoaplicadas o aprobadas manualmente), selección definitiva, aprobación limpia y compra completada generan evidencia idempotente; RFQs agrupadas resuelven resultado→proveedor; la aprobación inicia una sola conversación de compra por proveedor con sólo los ítems definitivos seleccionados; comparador, autorización, OC y lista de compra siguen siendo los existentes. No requiere migración. Commit `9b91094` en `main`.
- **Workflow Builder**: completo — fundación, conversacional, canvas visual y motor conectado de verdad al flujo real de aprobación (`listas.py` ya usa `iniciar_autorizacion_workflow()`). Ver sección dedicada arriba.
- **Onboarding conversacional + Workflow desde onboarding + Plantillas de correo (Fases 1-6 de ese proyecto)**: completas. Migraciones 034, 035, 036 aplicadas y confirmadas. Ver las tres secciones dedicadas arriba ("Onboarding conversacional", "Plantillas de correo", "Branding organizacional en documentos"). Commits `4bf2a79` → `d2b159a` en `main` (2026-08-09/10).
- **Trabajo en paralelo detectado, no documentado acá porque no es mío y sigue en curso**: "cubicación conversacional" (`identificar.py`, `cotizar/page.tsx`, `CUBICACION.md` — ver su propia sección abajo) y algo llamado "control plane" (`admin_control_plane.py`, `control_plane_telemetry.py`, migración `028_capo_control_plane.sql` — estado no reverificado esta sesión). Antes de tocar cualquiera de esos archivos, confirmar con el usuario en qué quedó esa sesión.
- `PROJECT_STATUS.md` y `handoff.md` son handoffs **viejos** — según instrucción explícita del usuario, **la continuidad vive solo en este archivo**, no confiar en esos dos para el estado actual.

## Próximos pasos
1. **`CLAUDE.md` se actualizó recién** (2026-08-10) — la próxima sesión debería partir de acá, no de `PROJECT_STATUS.md`.
2. Auditar las ~50 ocurrencias restantes del bug de `.maybe_single().execute()` sin chequear `None` (ver Gotchas) — hay un chip de tarea en background pendiente de que el usuario lo inicie.
3. Probar el onboarding conversacional de punta a punta con una segunda cuenta invitada real: aceptar la invitación, confirmar que queda como responsable y que puede iniciar sesión.
4. Migrar los 3 sitios de correo que quedaron fuera de la Fase 6 (copia interna de OC, aviso de proveedor confirmó recepción, encuesta de satisfacción) si se decide agregar eventos nuevos al catálogo para ellos.
5. Probar en producción el seguimiento de OC por correo (023): responder "recibido, gracias" desde otra cuenta y verificar que `ordenes_compra.estado` pasa a `recibido_conforme` solo, vía el cron de 1 min.
6. Probar Supplier Capability Intelligence (024) con datos reales: completar un onboarding y confirmar que aparece la fila en `procurement_profiles`; hacer una búsqueda y confirmar que se crea `search_sessions`; usar "Rebuscar con contexto" y confirmar que cae en `search_feedback`.
7. Verificar visualmente Fases 4–6 de Supplier Capability Intelligence con proveedores categorizados, enviar una RFQ agrupada de prueba desde Gmail y recorrer una búsqueda complementaria hasta el comparador.
8. Considerar si vale la pena arreglar o eliminar `procurement.py` (endpoint roto usado por el botón "+ Lista") y el sistema de Gantt sin uso (`proyectos.py`) — no tocado, solo detectado.

## Cubicación conversacional (primer corte)
- Motor puro en `backend/app/services/cubicacion.py`: unidades/dimensiones, conversiones, merma,
  formatos comerciales y recetas versionadas `completos@1`/`pintura@1`, más evaluación solar
  cotizable como servicio profesional con advertencias; sin `eval` ni aritmética LLM.
- `/api/identificar` activa el contrato sólo con `modo_cubicacion_conversacional`; usa
  `respuestas_cubicacion` estructuradas y conserva intactos a los clientes antiguos.
- `/cotizar` pregunta máximo tres datos por turno, no reenvía la imagen y muestra trazabilidad
  neto/compra antes de publicar mediante el flujo real de cotizaciones y listas.
