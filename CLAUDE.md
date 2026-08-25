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
- **Design system "soft professional"** (definido en `frontend/app/globals.css` — leerlo antes de
  escribir UI). Marca **azul petróleo** (`--brand`, base `#136b76`), neutros cálidos, **radios
  moderados** (`--r-sm/md/lg`), sombras suaves y **sentence case** — nada de mayúsculas con
  `letter-spacing`. Fuente base **Inter** (`--font-sans`); **IBM Plex Mono sólo para montos, códigos
  e identificadores** (`.mono`, `.tabular`), no para texto corriente. Tamaños de 13–15px, no de 9–11.
  - **Usar los componentes de `components/ui`** en vez de estilos inline propios: `PageHeader`,
    `Card`, `BtnPrimary`/`BtnSecondary`/`BtnGhost`, `Badge`, `Input`, `Modal`, `EmptyState`,
    `SkeletonBox`, `Table`. Iconos: `lucide-react`.
  - **Ojo con los alias.** Los nombres viejos (`--accent`, `--bg-surface`, `--text-primary`,
    `.btn-swiss-*`, `.label`, `.section-rule`) **siguen existiendo pero apuntan a los valores
    nuevos**. Por eso una pantalla escrita con el lenguaje anterior compila y *casi* se ve bien:
    toma los colores nuevos pero conserva mono en todo, mayúsculas y esquinas rectas. Pasó de
    verdad en `/integraciones` (2026-08-24). Preferir los tokens nuevos (`--brand`, `--surface`,
    `--n-600`, `--r-md`).
  - **Hasta el 2026-08-24 este archivo decía "Estilo Swiss: IBM Plex Mono, acento `#c0392b`,
    `border-radius: 0`"** — describía el sistema anterior y llevó a escribir una pantalla entera
    con el estilo equivocado. Si la UI real no coincide con lo que dice acá, la fuente de verdad es
    `globals.css`.
  - Gotcha de Tailwind: su preflight pone `list-style: none`, así que un `<ol>` **no numera** salvo
    que lo declares explícitamente.
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
- `listas.py` — listas de cotización multi-ítem (guardadas como JSON en `proyectos.descripcion`; lock por lista). **Es el sistema real y en uso** para proyectos multi-ítem — no confundir con `proyectos.py` (Gantt, tablas `items_proyecto`/`cotizaciones_proyecto`, existen pero con 0 filas reales); `procurement.py`, el otro modelo paralelo, fue eliminado el 2026-08-24. Cada ítem de una lista ya tiene identidad estable real: `it.cotizacion_id` es una fila propia de `cotizaciones`, no depende de su posición en el JSON.
- `procurement_profile.py` / `search_feedback.py` — Fase 1 de Supplier Capability Intelligence (ver sección dedicada más abajo).
- Otros: `cotizaciones`, `oc`, `aprobaciones`, `proyectos` (Gantt, sin uso real), `analisis` (IA), `gmail`, `facturas` (parser de correos entrantes), `recurrencias`, `estadisticas`, `chat`, `historico`, `suppliers`, `proveedores_import`, `notificaciones`, MCP + API pública.

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
- **`/settings/autorizaciones/canvas/[id]/page.tsx` — el canvas visual SÍ existe** (drag-and-drop de
  nodos, panel de propiedades, asignación de responsables por rol con dropdown "elegir existente" que
  asigna al instante + toast de confirmación). Cada tarjeta tiene un punto de **entrada** (izquierda,
  solo responde si ya hay una conexión armada desde otro nodo) y uno de **salida** (derecha, arma el
  origen) — antes un solo ícono servía para ambos y una conexión nueva podía pisar una existente. Las
  líneas se dibujan desde el borde real de cada tarjeta (no siempre izquierda/derecha fijo) y, si dos
  conexiones comparten el mismo par de tarjetas en sentidos opuestos, se separan con un offset
  perpendicular estable — si no, quedaban exactamente superpuestas y parecían una sola flecha
  apuntando mal. Las ramas "aprobado"/"rechazado" se pintan verde/rojo. Botón "Ordenar
  automáticamente" reacomoda las tarjetas en columnas según su distancia real desde "Inicio" (BFS
  simple — un nodo recibe su nivel la primera vez que se alcanza y nunca se re-encola, para tolerar
  ciclos reales del proceso como "rechazado → volver a cotizar" sin colgar el navegador).
- **Chat de correcciones dentro del canvas** (`interpretar_correccion()` en `workflow_conversational.py`,
  `POST /api/workflows/{id}/interpretar-correccion`) — el LLM propone una lista de operaciones sobre el
  grafo YA EXISTENTE (nunca lo rediseña completo), aplicadas con las mismas funciones que la edición
  manual. Incluye `asignar_responsable` (nombre + email + rol_clave) — a diferencia de las operaciones
  de grafo, esta se persiste al instante (igual que "+ Agregar responsable" del panel), no queda
  pendiente de "Guardar". El set de tipos de nodo agregables por chat (`TIPOS_NODO_AGREGABLES`) incluye
  "decision" — deliberadamente distinto del set que usa la creación inicial por ETAPAS, donde
  "decision" nunca es algo que el usuario describa (lo arma el compilador solo). Si TODAS las
  operaciones propuestas se descartan por validación, se lo dice honesto al usuario en vez de mostrar
  el resumen optimista del modelo con el grafo intacto.
- Endpoints en `routers/workflows.py`: `POST /api/workflows/interpretar`, `POST/GET /api/workflows`,
  `GET/PUT /api/workflows/{id}`, `DELETE /api/workflows/{id}` (rechaza borrar el ciclo activo),
  `GET /api/workflows/{id}/validar`, `POST /api/workflows/{id}/activar`,
  `POST /api/workflows/{id}/interpretar-correccion`, `/api/workflows/responsables*`. Migrados a
  `Depends(get_auth_context)` (ya no confían en `user_id` del body/query).
- **`/settings/autorizaciones` — roster de un solo ciclo, no lista de duplicados (2026-08-12).** Antes
  cada confirmación del chat creaba una fila nueva en `workflow_definitions` sin forma de verlas ni
  limpiarlas — el usuario terminó con 8+ ciclos sueltos. Ahora, si existe algún ciclo, la página muestra
  directo el principal (el `activo`, o si no el `borrador` más reciente) con quién está a cargo de cada
  rol y su estado real (`estado_onboarding_de_usuarios()` en `organizacion.py`: "activo" si
  `last_sign_in_at` no es null, "invitacion_pendiente" si nunca inició sesión, "sin_vincular" si nunca
  se invitó) — agregar/quitar personas ahí mismo, sin pasar por el canvas. Los demás ciclos quedan
  colapsados bajo "Otros ciclos (N)" con opción de eliminar (bloqueado para el activo). El refresco tras
  asignar/quitar una persona fija el ciclo por id (`cargarDetalle`) en vez de recalcular "cuál es el
  principal" en cada acción (`elegirPrincipal`, solo al montar o tras eliminar), y nunca borra la vista
  si el refetch falla por algo transitorio — solo un 404 real limpia el principal.
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
  preview): reusa `PropuestaWorkflowCard` (`frontend/components/workflow/`, compartido con
  `/settings/autorizaciones`) para crear el borrador, invitar responsables (solo si el usuario deja el
  checkbox marcado) y pasa directo al canvas para activar — mismos endpoints de `workflows.py`.
- **Chats unificados (2026-08-12):** `OnboardingChat.tsx` ya no tiene sus propias burbujas/input —
  usa los mismos componentes compartidos que `/settings/autorizaciones` y el chat de correcciones del
  canvas (`ChatBubbles` con slot `extra` para la tarjeta de empresa, `TypingBubble`, `textarea` +
  `BtnPrimary`). Al terminar el perfil, la MISMA conversación pregunta explícitamente "¿Pasamos a
  configurar el proceso de compras?" (máquina de fases `perfil → transicion → proceso` local al
  componente) en vez de mezclar la extracción de perfil y de proceso — la fase "proceso" llama
  `POST /api/workflows/interpretar` igual que `/settings/autorizaciones`, con contexto que arranca
  limpio desde ese punto. Si el usuario ya tiene un ciclo de compras, la pregunta ni se ofrece (chequea
  `GET /api/workflows` antes de preguntar) — evita la causa real de los ciclos duplicados que motivó el
  rediseño de `/settings/autorizaciones` en "roster de un solo ciclo" (ver sección Workflow Builder).
  `WorkflowGuardadoCard.tsx` ya no existe (se borró cuando se sacó la pantalla intermedia "Aceptar" /
  "Ajustar visualmente" — confirmar un workflow pasa directo al canvas en los dos chats).
- **Entrevista por slots en la fase "proceso" (2026-08-19).** Reemplazó el cuestionario de 5
  preguntas fijas. Antes el frontend decidía con regex si un tema "ya estaba cubierto"
  (`/(cotiz|presupuesto|comparacion)/` etc.) y, si no matcheaba, repetía la pregunta y hacía
  `return` **sin llamar nunca al backend** — una respuesta válida como "Valeria Tapia,
  admin@reveniu.com" no contiene la palabra "cotizar", así que el chat quedaba en loop infinito
  (bug real reportado en producción). Ahora las tres responsabilidades están separadas en
  `services/workflow_proceso_slots.py`: **avance determinístico** (`siguiente_slot()` = primer slot
  pendiente, con `MAX_INTENTOS_POR_SLOT=2` → la entrevista termina sí o sí en ≤12 turnos aunque el
  modelo nunca entienda nada), **comprensión por LLM** (`extraer_de_respuesta()`, único punto con
  Gemini) y **compilación determinística** (`compilar_slots_a_etapas()` → `compilar_a_grafo()`, el
  grafo nunca lo arma el modelo). Los 6 slots son cotizador/revisor/autorizador/reglas_monto/
  homologador/comprador. Una sola respuesta puede llenar varios slots y los ya cubiertos no se
  vuelven a preguntar (verificado real: una respuesta llenó 5 de 6 y sólo preguntó el que faltaba).
  Endpoint `POST /api/workflows/proceso/turno` (sin auth, igual que `/interpretar`); la ficha
  (`slots`) viaja en cada request, el backend no persiste la entrevista.
- **Primer uso de structured output real en el repo:** `ESQUEMA_EXTRACCION` se pasa como
  `response_schema` (+ `response_mime_type`) en `generation_config`, en vez del patrón de pedir
  JSON por prompt y limpiar los fences ```` ```json ```` a mano que usa el resto del backend
  (`identificar.py`, `purchase_invoice_service.py`, `workflow_conversational.py`). Schema plano y
  sin `null` a propósito (Gemini responde peor con nullables): centinelas `""`/`0` y validación en
  Python. Verificado en vivo que el SDK 0.8.6 acepta el schema como dict.
- El caso borde "Coti Zamorano autoriza, cotiz@abc.cl" se verificó contra Gemini real: la clasifica
  como `autorizador` pese a que se le preguntaba por el cotizador y a que nombre y correo contienen
  "coti"/"cotiz" — la asignación de rol es 100% semántica, ningún substring la toca.
- Escape hatch en el chat ("Prefiero describirlo con mis palabras"): sale del cuestionario y cae al
  flujo LLM completo de `/api/workflows/interpretar`. Descarta la ficha a medio llenar a propósito
  (mezclarla con una descripción libre produce workflows contradictorios).
- **Pendiente:** `onboarding_sessions` no guarda el `workflow_id` creado a mitad de camino ni la fase
  `perfil/transicion/proceso` — si el usuario recarga a mitad de la fase "proceso" antes de confirmar,
  vuelve a ver el botón "Confirmar y continuar" del perfil (ya guardado, así que reintentar es inocuo)
  y se le vuelve a preguntar si quiere configurar el proceso; overrides de plantilla por nodo del
  canvas no expuestos en la UI de onboarding.

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

## Workflow + comunicaciones unificado — Fase A (2026-08-17)
- PRD fuente: `PRD_WORKFLOW_COMUNICACIONES_UNIFICADO.md`. La Fase A está implementada en código,
  y la migración **`041_workflow_communications_foundation.sql` está aplicada y confirmada en
  Supabase producción (2026-08-17)**. Se verificaron por consultas reales las cuatro tablas nuevas
  (vacías, estado esperado), las columnas `workflow_version`/`execution_owner` en instancias y las
  columnas de reserva/auditoría en `mail_delivery_events`; no se crearon datos productivos de prueba.
- La 041 crea `workflow_node_assignments` (responsables por tarjeta),
  `workflow_node_communication_rules` (plantilla + disparador + loop + término),
  `workflow_node_executions` (una fila por visita) y `workflow_scheduled_actions` (cola durable con
  lease). Amplía instancias con `execution_owner = legacy|unified`: todas las existentes y las nuevas
  creadas por el código actual quedan en `legacy`, candado explícito contra doble envío durante la
  transición.
- RPCs atómicas preparadas: `claim_workflow_scheduled_action()` adquiere una acción vencida y permite
  recuperar leases expirados; `reserve_mail_delivery_event()` inserta la entrega antes de Gmail y
  sólo devuelve fila al worker que ganó la clave. `mail_template_service.reservar_envio()` expone
  este contrato, pero ningún emisor real lo usa todavía (se migran uno por uno en fases posteriores).
- `services/workflow_automation.py` es puro: valida asignaciones/reglas por nodo, audiencia y
  destinatario, loops con salida, resultados conectados y responsables internos resolubles; también
  genera claves idempotentes opacas por instancia+nodo+visita+regla+destinatario+intento.
  `workflow_automation_service.py` contiene persistencia base, sin ejecutar comunicaciones.
- Tests nuevos y regresión: pruebas focalizadas de workflow/mail: 72 passing; el resto de tests
  posteriores al punto de corte: 58 passing. La suite global llega a 83% y sale durante el test
  preexistente `test_descripcion_normal_no_lanza_por_scope_de_re`, que llama Gemini real sin mock;
  al excluir sólo ese caso, todo lo restante pasa. No se modificó frontend en esta fase.

## Workflow + comunicaciones unificado — Fase B (2026-08-17)
- Configurador unificado conectado a las tablas de la 041. No requiere una migración adicional y
  **todavía no ejecuta ni programa correos**: el cron/scheduler corresponde a Fase C.
- Endpoints autenticados/admin en `routers/workflows.py`: listar toda la configuración por tarjetas;
  crear/quitar `workflow_node_assignments`; crear/editar/quitar
  `workflow_node_communication_rules`. Identidad siempre desde `get_auth_context`, nunca desde
  `user_id` del body. Los servicios verifican pertenencia organizacional y sólo permiten editar
  workflows en `borrador`.
- `validar_workflow()` ahora combina `validar_grafo()` con `validar_automatizacion()`: una tarjeta
  humana necesita responsables explícitos por rol; loops necesitan evento de término y política de
  agotamiento; resultados usados por reglas deben existir y tener conexión. Activar un borrador con
  errores queda bloqueado. Las asignaciones globales `responsable_roles` se conservan como roster/
  fallback legado, pero no se reinterpretan silenciosamente como asignaciones por tarjeta.
- Canvas `/settings/autorizaciones/canvas/[id]`: panel ampliado con responsable por acción y modos
  individual/paralelo/secuencial; comunicaciones internas/externas; destinatario, disparador,
  demora, repetición, máximo, evento de término, alcance y política de agotamiento; resumen narrado y
  errores por tarjeta. Las tarjetas muestran conteos de responsables/correos y chip de loop.
- Editor de plantillas compartido en `components/workflow/MailTemplateEditor.tsx`: desde una regla
  crea override específico de nodo (precedencia existente nodo > workflow > organización > default),
  preview y restauración de herencia. Restaurar herencia archiva el override sin borrar versiones.
- `/settings/comunicaciones` se presenta como **Biblioteca de correos**, sólo para defaults de la
  organización, y muestra cantidad de usos en tarjetas. La tarjeta de `/settings` explica que
  destinatarios/cadencias/loops viven en el canvas.
- Chat de correcciones acepta `configurar_comunicacion` y asignación con `nodo_id`; sólo permite
  eventos reales del catálogo y rechaza loops incompletos. Se agregó `homologador` como rol base.
- Verificación: 110 pruebas focalizadas passing (1 test preexistente de Gemini real excluido);
  `next build` completo y exitoso. `tsc --noEmit` sigue reportando deuda preexistente en calendario,
  resultados, estadísticas, proyectos y reportes, pero cero errores en archivos de Fase B.

## Branding organizacional en documentos (OC e informes)
`OCPDFTemplate.tsx` y `ReporteTemplate.tsx` (ambos con `@react-pdf/renderer`, 100% frontend, no hay
generación de PDF en el backend) mostraban "Claria" hardcodeado. Ahora leen el perfil real de la
organización (`obtener_perfil_organizacion()` en `services/organizacion.py`, reusado por
`POST /api/oc/crear` y `POST /api/reportes/datos`): logo (imagen si existe, texto si no), nombre, RUT y
dirección, con fallback genérico "Baiyer" solo si la organización todavía no tiene perfil configurado.

## Aislamiento entre organizaciones — deny-by-default en el borde HTTP (2026-08-24)
Contexto: arrancan pilotos con clientes empresa reales, y una filtración entre organizaciones es
inaceptable. **El backend usa la service key, así que bypassea RLS** — las políticas de la 031 NO son
una segunda capa para el camino del backend. No requirió migración.
- **Agujero crítico encontrado y cerrado:** `POST /api/organizacion/invitar` recibía el `user_id` del
  invitador **en el body y sin autenticar**. Con el UUID de un admin de otra empresa, cualquiera se
  invitaba a sí mismo como `rol: "admin"` a esa organización. Ese campo ya no existe en el modelo.
- **`services/tenant_guard.py` — dependencia global `exigir_sesion`** (declarada en
  `FastAPI(dependencies=[...])`, ver `main.py`): toda ruta `/api` exige token de Supabase verificado
  salvo que esté en una de tres listas explícitas: `RUTAS_PUBLICAS` (magic links, callbacks OAuth,
  health, catálogos estáticos — cada una con el motivo escrito), `PREFIJOS_CON_GUARDIA_PROPIO`
  (`/api/admin-control-plane`, `/api/mcp`, `/api/v1`, que tienen otro mecanismo verificado) y
  `DEUDA_SIN_AUTENTICAR`. **Un endpoint nuevo nace cerrado.**
  Es dependencia global y **no** middleware ASGI a propósito: las dependencias corren después del
  ruteo, así que se lee `request.scope["route"].path` (la plantilla real, `/api/proyectos/{id}`) y el
  match es exacto, sin prefijos ni regex a mano.
- **`tests/test_tenant_guard.py` es el mecanismo real, más que el guardia**: un endpoint nuevo sin
  `Depends(get_auth_context)` y sin declarar hace fallar el test; también falla si quedan entradas
  muertas en las listas, y hay un tope numérico para que la deuda sólo pueda achicarse.
- El guardia deja el actor verificado en `request.state.actor_user_id` y `get_auth_context` lo reusa:
  **una sola verificación contra Supabase por request**, no dos.
- **56 endpoints migrados a `Depends(get_auth_context)`** (`proyectos` 15, `workflows` 11,
  `procurement-profile` 5, `notificaciones`/`buscar/sesiones` 7, LLM 6, correo 3, resto 9). Los 18
  de `procurement.py`/`ledger.py` no se migraron: se borraron.
  En el frontend, ~20 archivos pasaron de `fetch` a `authFetch` y **`user_id` salió de las query
  strings y de los bodies** (viajaba a logs de Railway/Cloudflare, historial y `Referer`).
- **Cinco endpoints no tenían NINGÚN filtro de propietario** (no es que confiaran en un `user_id`
  adivinable: no preguntaban nada): `chat/conversaciones/{id}/mensajes`, `calendario/llegada-efectiva`
  (escribía fecha de entrega y alteraba el score del proveedor en la OC de otra empresa),
  `reportes/datos` y dos de `proyectos`. Ahora verifican pertenencia y devuelven **404, no 403** — un
  403 confirmaría que el id existe en otra organización. En `proyectos.py` eso está centralizado en
  `_proyecto_de_la_org()`.
- **`DEUDA_SIN_AUTENTICAR` está en CERO** (arrancó en 72). Las últimas dos, `POST /api/buscar` y
  `POST /api/identificar`, se cerraron el 2026-08-24 con `services/cotizacion_pipeline.py` — ver la
  sección siguiente.
- **Pendiente real:** el test de aislamiento con dos organizaciones reales (recorrer todas las rutas
  con el token de A y afirmar que ninguna devuelve datos de B) y la Fase 1 de
  `PLAN_DATA_FOUNDATION.md` — el borde HTTP está cerrado, pero **con service key un `.eq()` olvidado
  dentro de un servicio todavía cruza organizaciones**.

## Auditoría externa y cierre de escalada de privilegios (2026-08-25)
Un pentest black-box con cuenta propia (informe en `~/Downloads/informe_baiyer_mcp.md`, no versionado)
confirmó que **no se pueden leer datos de otra organización** — el borde HTTP y RLS aguantan. Lo que
encontró es escalada de privilegios y toma de control de recursos propios de otra cuenta. Ojo con el
ranking del informe: su hallazgo "CRÍTICO" (auto-upgrade de `public.users.plan` por RLS floja) es
**real pero casi inocuo**, porque `public.users` no lo lee NINGÚN gate del backend (`grep table("users")`
en `app/` da cero); el escalado de plan que buscaba estaba en `api_keys.plan`. Y descartó como "no
confirmado" el peor de todos, el de `state` de OAuth.
- **`state` OAuth forjable → toma del buzón (lo más grave, cerrado).** `_encode_state` era
  `base64(json)` sin firma y `GET /api/gmail/auth?user_id=...` estaba en `RUTAS_PUBLICAS` con el motivo
  equivocado ("lo llama Google" — a `/auth` lo llama el navegador; sólo `/callback` viene del
  proveedor). Cualquiera abría ese link con el UUID de la víctima, completaba el consentimiento con
  **su propia** cuenta de Google, y el callback hacía `upsert` de sus tokens en la fila
  `user_integrations` de la víctima. No es leer correo ajeno: las RFQ y OC de la víctima salen desde el
  buzón del atacante y el agente Gmail ingiere correo que él controla como cotizaciones de proveedores
  (con auto-aplicación a confianza ≥ 0.85). Cierre en dos partes, las dos necesarias:
  `POST /api/{gmail,outlook}/conectar` (autenticado, devuelve la URL de consentimiento en JSON porque
  un endpoint con sesión no puede ser destino de una navegación) y `services/oauth_state.py`
  (`state` firmado con HMAC-SHA256 sobre `SUPABASE_SERVICE_KEY`, vigencia 10 min) para que `/callback`,
  que sigue siendo público de verdad, pueda confiar en el `user_id` que lee. Sin la firma, el punto 1
  se saltaría llamando a `/callback` directo. Cobertura: `tests/test_oauth_state.py`.
- **`/api/v1/keys` — identidad y plan del cliente (cerrado).** Los tres endpoints deducían el usuario de
  `X-Claria-User-Id` (header plano, sin token) y el plan de `X-Claria-User-Plan`, que se grababa tal
  cual en `api_keys.plan` — el único plan que el backend sí aplica (`rate_limiter.get_plan_config()`).
  Ahora usan `Depends(get_auth_context)` y `plan_de_organizacion()` lo resuelve contra
  `organizations.plan` (lo escribe sólo el control plane). **No sirve derivarlo de `user_metadata`**:
  el propio usuario lo edita con `supabase.auth.updateUser()` desde `/settings`.
- **La exención por prefijo de `tenant_guard` era la causa raíz del punto anterior**: `/api/v1` entero
  estaba eximido asumiendo "todo esto va por api_key", pero los endpoints que EMITEN la api_key no
  pueden autenticarse con ella. Ahora existe `RUTAS_CON_SESION_DENTRO_DE_PREFIJO` y el test lo fija.
- **`invitar_a_organizacion` linkeaba responsables sin filtro de organización** (`_linkear_responsable()`
  ahora filtra por `ctx.user_ids_miembros`). No permitía aprobar nada ajeno — `_authorized_request` y
  `decidir_caso` chequean organización aguas abajo — pero sí desconectar al responsable legítimo de otra
  empresa de sus aprobaciones y avisos.
- **`POST /api/organizacion/invitar` — respuesta uniforme (cerrado).** Devolvía el `user_id` recién
  creado y distinguía tres casos, así que cualquier usuario autenticado mapeaba qué correos tienen
  cuenta en Baiyer y se quedaba con sus UUIDs. Ahora siempre `{"estado": "invitada"}` sin `user_id`,
  incluido el caso "pertenece a otra organización" y los fallos de `invite_user_by_email` (cuyos
  mensajes también distinguen "email ya registrado"). Se conserva `ya_miembro` a propósito: el
  invitador es admin de esa organización y ya puede listar su propio roster.
  **Contrapartida real y aceptada:** si el correo pertenece a otra organización, el admin ve
  "Invitación enviada" y no pasa nada. El efecto sí es visible en el roster de
  `/settings/autorizaciones`, donde ese responsable queda "sin vincular".
- **Docs apagadas en prod (cerrado):** `main.py` pasa `docs_url/redoc_url/openapi_url = None` cuando
  `settings.is_production` (propiedad nueva en `config.py`). Cubierto por `tests/test_docs_produccion.py`.
- **`.single()` → `ejecutar_maybe_single()` en los dos magic links de OC (cerrado):**
  `GET /api/oc/info/{token}` y `POST /api/oc/confirmar/{token}` devolvían 500 con un token inválido,
  porque `.single()` lanza con 0 filas y el `if not res.data` de la línea siguiente era inalcanzable.
  Son endpoints públicos que abre el proveedor desde el correo: el token equivocado es el caso
  esperado, no la excepción.
- **`migrations/046_users_plan_no_editable.sql` — aplicada el 2026-08-25** (confirmada por el usuario:
  "Success. No rows returned", que es lo esperado en DDL). Trigger `BEFORE UPDATE` que impide al
  cliente cambiarse `plan`/`trial_hasta`/`plan_activo_hasta`/`cotizaciones_mes_actual` en
  `public.users`; va como trigger y no como policy porque **RLS no puede restringir por columna**. Es
  higiene: hoy ningún gate del backend lee esa tabla.
  **Falta verificar el efecto**, no sólo que la migración corriera: repetir el PATCH del informe
  (`PATCH /rest/v1/users?id=eq.<mi_id>` con `{"plan":"enterprise"}` y el token de sesión propio) y
  confirmar que ahora devuelve error `42501` en vez de 200. Si igual pasa, el chequeo
  `current_setting('request.jwt.claim.role')` no es el correcto para esta versión de PostgREST y hay
  que cambiarlo por `auth.role()`.
- **Pendiente de esa auditoría:** limpiar los `user_id` de los schemas de las tools MCP
  (el servidor los ignora, pero sugieren una confianza que no existe); los hints de PostgREST que
  revelan nombres de tablas (sin fix directo, baja prioridad). **Rotar los secretos ya no está en la
  lista**: se revisó el 2026-08-25 y no hubo exposición real (ver "Gotchas importantes").

## Pipeline de cotización en proceso (`services/cotizacion_pipeline.py`, 2026-08-24)
`cotizar_descripcion()` hace identificar → crear la fila en `cotizaciones` → buscar, **todo en
proceso**, reusando `identificar_item()` y `BuscarRequest`/`_buscar_fuentes`/`_filtrar_gemini`/
`_guardar_supabase` (mismo patrón que ya usaba `web_quote_service._run()`).
- **Para qué:** el servidor MCP legado (`mcp/tools/cotizar.py`) y la API pública
  (`api_publica/endpoints/cotizar.py`) le pegaban por HTTP a `http://localhost:8000/api/identificar`
  y `/api/buscar`. Eso obligaba a dejar esos dos endpoints sin autenticación. Ya no: **ambos usan el
  pipeline y los dos endpoints exigen sesión**.
- **Los dos llamadores estaban rotos y nadie lo había notado** (verificado con llamadas reales, no
  leyendo el código): mandaban `{"item_id","cantidad","user_id"}` a `/api/buscar`, cuerpo que no
  corresponde a `BuscarRequest` → **422**; y leían `id`/`item_id` de la respuesta de `/api/identificar`,
  que **nunca devolvió ninguno de los dos** (identificar no crea la fila en `cotizaciones`, eso lo hace
  el cliente). O sea `cotizar_item` devolvía siempre "No se pudo identificar el item" y
  `POST /api/v1/cotizar` siempre `item_not_identified`. Ahora ambos devuelven precios reales
  (verificado: 40 resultados para "taladro percutor 800w", 20 proveedores para "casco de seguridad").
- **Identidad:** `identificar_item()` y `buscar_proveedores()` sobrescriben `req.user_id` con
  `ctx.actor_user_id` cuando hay request HTTP. El pipeline los llama con `ctx=None` y pasa el actor
  explícito, ya verificado aguas arriba (api_key de la API pública o token MCP). Importa porque
  `incluir_proveedores_custom` inyecta los proveedores privados de esa organización.
- Si falla el insert en `cotizaciones`, la búsqueda igual corre y devuelve precios sin persistir:
  cotizar es lo que el usuario pidió, perder la traza es peor que nada pero mucho menos que fallar.

## Gotchas importantes
- **Migraciones = manuales.** El service key de Supabase NO hace DDL, y no hay `DATABASE_URL` para conexión directa — Claude Code prepara el `.sql` y lo copia al portapapeles (`pbcopy`), pero el usuario lo pega y ejecuta en el SQL Editor de Supabase. Aplicadas y **confirmadas contra la DB real**: 019–021 agente Gmail, 022 notificaciones, 023 seguimiento de OC por correo, 024 Supplier Capability Intelligence, 025 ficha de proveedores, 026 `rfq_batches`, 027 Workflow Builder, 029 workflow↔aprobación real, 030 organizaciones, 031 RLS organizacional, **034 perfil organizacional + `onboarding_sessions`, 035 `direccion`, 036 plantillas de correo** (estas 3 confirmadas en esta sesión). Estado de 028 (capo control plane, de otra sesión), 032 (mcp oauth state) y 033 (supplier_ratings) no reverificado en esta sesión — no asumir sin chequear.
- **Bug real de `postgrest-py` 2.x encontrado en producción — ya corregido en todo el backend (commit `43fd9c4`).** `.maybe_single().execute()` devuelve `None` directamente (no un objeto con `.data = None`) cuando la consulta no matchea ninguna fila — cualquier `.execute().data` sin chequear `None` antes crashea con `AttributeError`. Se encontró primero en `resolver_organizacion()` (rompía dashboard/listas/gmail/workflows enteros para cualquier usuario sin fila en `membresias_organizacion`) y se terminó de auditar el resto del backend: **57 ocurrencias en 12 archivos** corregidas con `ejecutar_maybe_single()` (`services/supabase.py`) — envuelve el query y siempre devuelve un objeto con `.data` accesible, sin tener que reescribir la lógica de cada sitio. Para queries nuevas: usar `ejecutar_maybe_single(query.maybe_single())` en vez de `query.maybe_single().execute()`. **Ojo:** había un chip de tarea en background para esto mismo que el usuario alcanzó a iniciar por separado — si existe un worktree/sesión paralela tocando los mismos archivos, revisar por conflictos antes de mergear.
- **`get_auth_context` ahora autocrea la organización si falta** (usuarios registrados después del backfill de la 030 no tenían fila en `membresias_organizacion` y quedaban bloqueados con 403 en TODO endpoint protegido) — usa la misma red de seguridad que ya tenía `obtener_organizacion()` para `/api/organizacion/mia`.
- **Tablas referenciadas en código que NO EXISTEN en producción (confirmado con `sb.table(x).select('*').limit(1)` contra la DB real, no contra los `.sql`):** `supplier_categories` y `procurement_ledger` (de `014_smart_procurement.sql`, migración numerada pero aplicada solo a medias — `approval_workflows`/`approval_requests`/`recurrencia_logs` de ese mismo archivo sí existen), `quote_items`/`quote_suppliers`/`purchase_events` (de `013_procurement_flow.sql`; el código que las usaba se borró el 2026-08-24), `supplier_ratings`/`rating_pendiente` (usadas por `supplier_intelligence.py` y `POST /api/suppliers/rating` — fallan en silencio o 500). Ningún numero de migración garantiza que esté realmente en prod: **antes de asumir que una tabla existe, verificar con una query real**, no solo mirar `backend/migrations/`.
- **Modelos de Gemini: verificar contra `list_models()`, no de memoria (2026-08-25).** `escanear_boleta`
  (`listas.py`, `POST /api/listas/{id}/boleta-scan`) pedía **`gemini-1.5-flash`, que está retirado** y
  no aparece en la lista de la cuenta. La llamada lanzaba siempre, el `except Exception` de ese bloque
  la convertía en `502 "No se pudo leer la boleta"` y parecía un fallo transitorio del OCR — la función
  llevaba quién sabe cuánto muerta. Corregido a `gemini-2.5-flash` (verificado en vivo que acepta
  imagen + prompt). El resto del backend ya usaba `gemini-2.5-flash` (22 sitios) y
  `gemini-3.5-flash-lite` (2 sitios en `_modelos_identificacion`, con fallback explícito por
  `_es_error_modelo_no_disponible`); **ambos existen**, comprobado contra la API real. Para chequear:
  `genai.list_models()` filtrando por `generateContent` — no consume tokens.
- **`procurement.py` y `ledger.py` ya no existen (borrados 2026-08-24).** Eran código muerto de punta
  a punta sobre tablas que nunca existieron en producción (`quote_items`/`quote_suppliers`/
  `purchase_events`/`procurement_ledger`): ningún link navegaba a `/procurement`, nada los importaba y
  sus 18 endpoints respondían 500. Se fueron con ellos `frontend/app/procurement/` y la rama
  `quote_supplier:` de `aprobaciones.py`, que era inalcanzable. La decisión quedó registrada en la
  Fase 3 de `PLAN_DATA_FOUNDATION.md`. Ojo: `procurement_profile.py` y `/api/procurement-profile/*`
  son **otra cosa** (Supplier Capability Intelligence, en uso real) — no confundir por el nombre.
- **Orden de auto-aplicación Gmail:** hoy `item_field_updates` se inserta como `aplicado` antes de actualizar `resultados`. Si el segundo paso falla, la auditoría puede decir “Aplicada” sin que el dato exista. Esto ocurrió en datos antiguos y sigue siendo un riesgo del código actual; conviene hacer la escritura atómica o marcar `aplicado` sólo después del update exitoso.
- **Estado de conexión Gmail:** el dashboard debe consultar `/api/gmail/status`; no inferir la conexión desde `?gmail=conectado`, porque ese query param sólo existe inmediatamente después del callback OAuth. Al reconectar, conservar el `refresh_token` persistente si Google no devuelve uno nuevo.
- **credentials.json** (OAuth Gmail) está **gitignored** — en prod se usan env vars `GOOGLE_CLIENT_ID`/`GOOGLE_CLIENT_SECRET`.
- **SMTP:** Resend configurado en Supabase (dominio baiyer.cl verificado). Correos de auth (confirmación/recuperación) salen desde `no-reply@baiyer.cl`.
- **Serper.dev** integrado (2.500 búsquedas gratis; `SERPER_API_KEY`). Prioriza sobre SerpAPI.
- **Rotación de secretos: CERRADA, no era un bloqueante (2026-08-25).** Hasta hoy este archivo pedía
  "rotar los secretos expuestos en capturas" y eso figuraba como bloqueante de seguridad #5. Al
  revisarlo con el usuario, **no hubo exposición**: las capturas nunca salieron de su máquina (no se
  compartieron por chat, ni se subieron a un asistente de IA, ni quedaron en un issue, video o carpeta
  sincronizada). Un secreto que sólo vio su dueño no dejó de ser secreto. **No hay nada que rotar.**
  - El repo también está limpio — verificado sobre el historial completo (`git log --all
    --diff-filter=A` + búsqueda de `eyJhbGciOi…`/`AIza…`/`GOCSPX-`/`sk-ant-`/`sb_secret_` en todos los
    diffs): cero coincidencias, y los únicos `.env` trackeados son los dos `.env.example` con
    placeholders. **No hace falta reescribir el historial.**
  - La protección que sí conviene para Gemini no es rotar, es un **límite de gasto en Google Cloud**:
    la cuenta es pagada, así que un abuso factura sin techo, y un tope cubre cualquier fuga futura
    mucho mejor que cambiar la clave una vez.
  - **Si alguna vez SÍ hay que rotar, dos trampas:** (1) `SUPABASE_SERVICE_KEY` también firma el
    `state` de OAuth de correo (`services/oauth_state.py` la usa como clave HMAC), así que rotarla
    invalida los consentimientos en vuelo — ventana de 10 min, se resuelve reintentando, pero hay que
    saberlo para no perseguir un bug fantasma; (2) el proyecto usa el sistema **nuevo** de API keys de
    Supabase (hay un `sb_publishable_...`), o sea que se pueden tener dos secret keys vivas y borrar la
    vieja después — **nunca tocar el JWT Secret legacy**, que cierra la sesión de todos los usuarios.
    Orden siempre: crear la nueva → cargarla en Railway → verificar → recién ahí borrar la vieja.
  - Criterio para la próxima vez: una clave sólo se rota si se puede nombrar **dónde** se filtró. Rotar
    "por las dudas" tiene costo (ventana de corte, riesgo de error humano) y beneficio cero.
- **`mcp_jwt_secret` ya no existe** (borrado el 2026-08-25). Era un default hardcodeado en
  `config.py` (`"claria-mcp-secret-change-me-in-production"`) que **no usaba nadie**: los tokens MCP
  son opacos y se validan contra la DB desde la Fase 8 (`verify_mcp_token` → `token_service.load_token`),
  no por firma. No era un riesgo vivo; se borró para que nadie lo "reactive" dentro de seis meses.

## Env vars
- **Backend (Railway `baiyers`):** SUPABASE_URL, SUPABASE_SERVICE_KEY, GEMINI_API_KEY, SERPER_API_KEY, SERP_API_KEY, ANTHROPIC_API_KEY (vacío), ENVIRONMENT=production, CORS_ORIGINS (incluye baiyer.cl + railway), FRONTEND_URL=https://www.baiyer.cl, GOOGLE_CLIENT_ID/SECRET, GOOGLE_REDIRECT_URI.
- **Frontend (Railway `sweet-trust`):** NEXT_PUBLIC_SUPABASE_URL, NEXT_PUBLIC_SUPABASE_ANON_KEY, NEXT_PUBLIC_API_URL=https://baiyers-production.up.railway.app.

## Costos infra
Railway ~$5-10/mes · Supabase free · Serper 2.500 gratis→$50/50k · **Gemini: cuenta PAGADA**
(confirmado por el usuario 2026-08-19 — antes este archivo decía "free tier", dato que ya no aplica).
WhatsApp y SII (futuros) sí cuestan.

**Consecuencia de seguridad de estar en tier pagado:** en free tier la cuota actuaba como techo
accidental (un abuso se cortaba solo y el daño era caída, no factura). Pagando ese techo no existe:
cualquier endpoint que llame a Gemini sin autenticación factura sin freno. Ver "Defensas de costo LLM".

### Prepago vs pospago de Google (verificado 2026-08-25)
La cuenta tiene **dos carriles separados** y hoy sólo se usa el barato:
- **Prepago (AI Studio)** — lo que paga Gemini. Se cargaron CLP 10.000 el 20-jun-2026 y al 25-ago
  quedaban ~6.854 (≈1.500/mes de consumo real). **Recarga automática DESACTIVADA**, y ése es el techo
  real: los créditos se descuentan antes de ejecutar cada llamada. No activarla sin pensarlo.
- **Pospago (Google Cloud)** — saldo CLP 0, sin transacciones. Ojo: el "límite de pago CLP 30.000"
  que muestra la consola **no es un tope de gasto**, es el umbral que Google deja acumular antes de
  pasar la tarjeta. Y los *presupuestos* de Google Cloud sólo mandan alertas, no cortan nada; el único
  freno duro es bajar la cuota de la API (APIs y servicios → la API → Cuotas).
- **Nada del código toca hoy el carril pospago** (auditado el 2026-08-25 sobre todo `backend/app/`):
  Gemini entra por AI Studio (`genai.configure` + `GenerativeModel`, cero rastros de
  `vertex`/`aiplatform`), el único servicio Google que se construye es `build("gmail")` — que es
  gratis, de ahí las ~14.000 solicitudes diarias del cron sin costo—, los logos van a Supabase
  Storage y las búsquedas a Serper/SerpAPI. Sin Pub/Sub, GCS, Maps, Vision ni Document AI.
- **Las dos únicas vías que activarían el pospago, si alguien las toca:**
  1. **Activar el webhook Pub/Sub de Gmail.** `POST /api/gmail/webhook` (`gmail.py:410`) hoy es un
     stub que loguea y devuelve `{"status": "received"}`, y **nadie llama a `users.watch()`**, que es
     lo que haría que Gmail publique en un topic. Producción usa polling por cron. Pub/Sub **es un
     servicio pago de GCP**.
  2. **Migrar Gemini a Vertex AI.** Es el riesgo sutil: mismo modelo, misma respuesta, pero el cobro
     salta de los créditos prepagos a la cuenta pospaga sin que nada en la app lo indique.

## Defensas de costo LLM (2026-08-19)
- `services/llm_rate_limit.py` — rate limiting **por IP** en memoria (distinto del de
  `api_publica/rate_limiter.py`, que va por `api_key_id` y plan). Usa `CF-Connecting-IP` (la
  sobrescribe Cloudflare, es la confiable) y cae a `X-Forwarded-For`/`request.client`. Los intentos
  rechazados **no** se contabilizan, si no un loop dejaría a esa IP bloqueada para siempre. Limpia
  ventanas viejas cada 5 min para no ser él mismo un vector de memoria.
- Aplicado a los dos endpoints de workflows que llaman a Gemini sin auth:
  `/api/workflows/interpretar` (10/min, 60/h) y `/api/workflows/proceso/turno` (20/min, 120/h).
  Un onboarding real gasta ~6-12 llamadas en total.
- Topes de tamaño del body en `routers/workflows.py` (`MAX_DESCRIPCION=8000`, `MAX_CONTEXTO=20000`,
  `MAX_RESPUESTA=4000`, `MAX_SLOTS=50`) — antes NO había ninguno: un solo request con cientos de KB
  costaba lo que miles de usos legítimos. Excederlos devuelve 422 antes de tocar Gemini.
- **Limitaciones honestas:** el contador es en memoria y por proceso (con varias réplicas el límite
  efectivo se multiplica); el rate limiting por IP es un freno, no una garantía — un atacante
  distribuido rota IPs. La mitigación de fondo sigue siendo exigir autenticación.

### Extensión a identificar/buscar/analisis (2026-08-20, commit `9edbad9`)
Los 7 endpoints POST de `identificar.py`, `buscar.py` y `analisis.py` ya tienen límite por IP + topes
de tamaño en Pydantic (rechazan 422 antes de tocar ninguna API paga). Siguen **sin
`get_auth_context`** — eso no cambió y sigue siendo la mitigación de fondo pendiente.
- Límites: `/identificar` y `/refinar-busqueda` 15/min·100/h; `/buscar` y `/buscar/stream`
  20/min·200/h (compartido, calibrado contra el uso real del frontend: una llamada por ítem al abrir
  su vista de resultados); `/buscar/prefetch` 5/min·30/h; `/analizar-cotizaciones` 10/min·60/h.
- **`es_llamada_interna()` en `llm_rate_limit.py` es obligatorio entender antes de tocar esto:**
  `/api/buscar` lo consumen server-to-server el servidor MCP (`mcp/tools/cotizar.py`) y la API
  pública (`api_publica/endpoints/cotizar.py`) contra `http://localhost:8000`. Sin la exención,
  ambos comparten la IP de loopback y **se estrangulan entre sí** — el límite pensado para abuso
  externo rompería el flujo legítimo. La exención sólo aplica si NO hay `cf-connecting-ip` ni
  `x-forwarded-for` (un request desde internet siempre trae alguna), así nadie se declara interno
  falsificando `X-Forwarded-For: 127.0.0.1`. Esos dos caminos ya tienen control propio aguas arriba.
- **El endpoint más caro NO es `buscar`, es `/analizar-cotizaciones`**: usa Anthropic Opus con
  `max_tokens=16000` y thinking adaptive. Hoy corta con 503 porque `ANTHROPIC_API_KEY` está vacía en
  prod; el límite existe para que configurarla algún día no abra una vía de facturación sin freno.
- `/buscar/prefetch` era un **amplificador**: encolaba una búsqueda completa en background por cada
  `cotizacion_id`, sin tope (`MAX_PREFETCH_IDS=50` ahora). Ojo: **no lo llama nadie** — ni el
  frontend ni el backend. Candidato a eliminar.
- **SSRF cerrado en `/identificar`**: `imagen_url` se descargaba con un `client.get()` directo sobre
  cualquier URL del cliente, sin auth — apuntaba sin problema a `169.254.169.254` y a la red interna
  de Railway. Ahora reusa `descargar_y_validar_url()` de `services/logo_upload.py` (valida esquema,
  resuelve DNS y rechaza IPs privadas en cada redirección, más content-type y tamaño). **Para
  cualquier descarga nueva de una URL provista por el usuario, reusar esa función, no reimplementarla.**
- Cobertura: `tests/test_llm_rate_limit.py` (incluye el bypass de `X-Forwarded-For`) y
  `tests/test_endpoints_llm_topes.py`.

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
2. ~~Auditar las ~50 ocurrencias restantes del bug de `.maybe_single().execute()`~~ — hecho (commit `43fd9c4`). Si hay una sesión en background que también lo estaba haciendo por separado, revisar y descartar ese trabajo duplicado.
3. Probar el onboarding conversacional de punta a punta con una segunda cuenta invitada real: aceptar la invitación, confirmar que queda como responsable y que puede iniciar sesión.
4. Migrar los 3 sitios de correo que quedaron fuera de la Fase 6 (copia interna de OC, aviso de proveedor confirmó recepción, encuesta de satisfacción) si se decide agregar eventos nuevos al catálogo para ellos.
5. Probar en producción el seguimiento de OC por correo (023): responder "recibido, gracias" desde otra cuenta y verificar que `ordenes_compra.estado` pasa a `recibido_conforme` solo, vía el cron de 1 min.

### Estado de ramas (verificado 2026-08-24)
**`main` está al día con `origin/main` y `testing` ya está mergeada** (`git rev-list main..testing`
= 0). Hasta el 2026-08-24 este archivo decía que había "8 commits sin mergear ni pushear" en
`testing`; era información vieja. Recordar que **`main` es la rama de deploy**: Railway auto-deploya
ambos servicios al pushear ahí.

### Bloqueantes conocidos y no resueltos (actualizado 2026-08-24)
1. **Checkpoint productivo de Fase G** — correr un ciclo real `unified` antes de retirar legacy.
2. **Aislamiento en profundidad** — el borde HTTP está cerrado, pero el backend usa service key: un
   `.eq()` olvidado dentro de un servicio todavía cruza organizaciones. Falta el test de aislamiento
   con dos organizaciones reales y la Fase 1 de `PLAN_DATA_FOUNDATION.md`.
3. **Auto-aplicación Gmail no atómica** — `item_field_updates` se marca `aplicado` antes de escribir
   en `resultados`; si el segundo paso falla, la auditoría dice "Aplicada" sin que el dato exista.
4. **`registrar_envio()` es sólo auditoría** — no bloquea ni deduplica, un reintento todavía puede
   duplicar un correo real.
5. ~~Rotar los secretos expuestos en capturas~~ — **no era un bloqueante**: las capturas nunca
   salieron de la máquina del usuario y el historial de git está limpio (verificado el 2026-08-25,
   ver "Gotchas importantes"). No agregar de nuevo este punto sin poder nombrar dónde se filtró algo.

## MCP Baiyer — Fases 0 y 1 (2026-08-13)
- El contrato operativo completo está en `MCP_FASE_0_CONTRATO.md` (tools,
  resources, prompts, scopes, confirmaciones, jobs y brechas). Es la fuente de
  verdad del proyecto MCP.
- Fase 1 implementada en código: `services/mcp_context.py`,
  `services/lista_service.py`, `services/mcp_jobs.py` y
  `services/semantic_query.py`. Crear/listar listas ya delega en el servicio
  compartido manteniendo el API web actual.
- `backend/migrations/038_mcp_data_foundation.sql` crea jobs/drafts y la RPC
  transaccional proyecto/documento → cotizaciones + lista. **Aplicada y
  confirmada en Supabase producción el 2026-08-14** mediante consultas reales
  a `integration_jobs` e `integration_drafts` (ambas vacías, estado esperado).
  La RPC no se invocó para no crear datos productivos de prueba.
- El transporte y OAuth MCP siguen siendo legado/no estándar y corresponden a
  Fase 2. No conectar todavía clientes externos a `/api/mcp/sse` o `/rpc`.

## MCP Baiyer — Fase 2 (2026-08-14)
- Streamable HTTP estándar implementado en `/api/mcp` con tools iniciales de
  Fase 1. Diseño y operación en `MCP_AUTH_TRANSPORT.md`.

## MCP Baiyer — Fase 3 (2026-08-14)
- Proyectos, carga de documentos y CRUD de listas implementados como tools
  MCP. Flujo seguro de draft/preview → confirmación → commit transaccional.
- Documento operativo: `MCP_FASE_3_PROYECTOS_DOCUMENTOS_LISTAS.md`.
- Reutiliza migraciones 038/039; no requiere SQL adicional.
- Migración 039 aplicada y confirmada. Pendiente configurar Railway, desplegar
  y validar OAuth/tools reales con Codex y Claude.

## MCP Baiyer — Fase 4 (2026-08-14)
- Búsqueda web normal/ampliada por ítem o lista mediante jobs persistidos.
- Progreso parcial, cancelación cooperativa y recuperación tras restart.
- Lectura de ofertas y cobertura de lista disponibles como tools MCP.
- Documento operativo: `MCP_FASE_4_BUSQUEDA_WEB_COTIZACIONES.md`.
- 23 tools MCP totales; no requiere migración adicional.

## MCP Baiyer — Fase 5 (2026-08-14)
- Matriz de proveedores, preparación/edición/envío Gmail de RFQ, estados,
  sincronización de respuestas y revisión de propuestas expuestos como tools.
- Confirmación explícita para enviar, sincronizar y aplicar/rechazar datos.
- Documento operativo: `MCP_FASE_5_PROVEEDORES_RFQ_CORREO.md`.
- `suggest_suppliers` combina ahora el directorio privado con el banco global
  categorizado que ya usa la web; `select_supplier_for_item` materializa sólo
  el sugerido elegido y registra su capacidad para listas futuras.
- 37 tools MCP acumuladas al cierre de esta fase; no requiere migración adicional.
- Pendientes honestos: follow-up manual y envío RFQ agrupado vía Outlook.

## MCP Baiyer — Fase 6 (2026-08-14)
- Comparativos por ítem/lista, recomendación explicable, selección definitiva,
  ruta/estado/eventos y decisiones de aprobación expuestos como tools MCP.
- Aprobar/rechazar exige `responsable.usuario_baiyer_id == actor_user_id`; el
  flujo legacy por email sólo se decide por magic link.
- Corregido el snapshot de aprobación: ahora incluye alternativas reales.
- Documento operativo: `MCP_FASE_6_COMPARACION_APROBACIONES.md`.
- 47 tools MCP totales; no requiere migración adicional.

## MCP Baiyer — Fase 7 (2026-08-14)
- OC: preview, crear, listar, leer, editar, enviar PDF y tracking.
- Facturas: preview/commit documental, listar/leer, conciliar/vincular OC,
  marcar pagada y escanear inbox.
- Endurecido `/api/oc/enviar` contra acceso cruzado y estados falsos.
- Documento operativo: `MCP_FASE_7_OC_FACTURAS.md`.
- 62 tools MCP totales; no requiere migración adicional.

## MCP Baiyer — Fase 8 (2026-08-14)
- Proveedores/importación, informes, métricas, 9 resources y 9 prompts.
- Auditoría transversal sin argumentos ni respuestas sensibles.
- 77 tools MCP totales; 272 pruebas generales aprobadas y una deseleccionada
  porque llama Gemini en vivo.
- Documento: `MCP_FASE_8_PROVEEDORES_REPORTES_RESOURCES_AUDITORIA.md`.
- Migración `040_mcp_audit_log.sql` aplicada y verificada en producción.
- OAuth endurecido: DCR, PKCE S256, state/redirect/resource obligatorios,
  tokens opacos hashados, refresh rotativo y revocación de familia.
- `backend/migrations/039_mcp_oauth_secure.sql` fue aplicada y confirmada en
  Supabase. Variables MCP configuradas en Railway; falta el despliegue de Fase 9.
- `/api/mcp/sse` y `/rpc` son solo legado temporal; los clientes nuevos deben
  usar Streamable HTTP en `/api/mcp`.

## MCP Baiyer — conexión global y login unificado (2026-08-24)
- `/integraciones` muestra instalación global real para los dos clientes
  principales: Claude Code usa `claude mcp add --scope user --transport http`
  (antes omitía `--scope user` y quedaba local pese a que el texto decía otra
  cosa); Codex usa `codex mcp add baiyer --url ...` + `codex mcp login baiyer`
  (ya no obliga a editar `~/.codex/config.toml` a mano). La documentación
  pública `/docs/mcp` fue reemplazada porque todavía mostraba el paquete npx
  inexistente `@claria/mcp-server` y un token manual que el producto no usa.
- El authorization endpoint MCP mantiene la validación OAuth 2.1/DCR/PKCE y
  luego redirige a `/mcp/autorizar` en el frontend con un `request_id` interno
  opaco. Ya no usa el `state` elegido por el cliente como clave de persistencia
  (dos clientes podían pisarse si lo repetían) ni renderiza un formulario HTML
  del backend que sólo aceptaba contraseña.
- La pantalla de consentimiento reutiliza Supabase Auth: sesión Baiyer ya
  abierta (un botón), Google, Microsoft o correo+contraseña. Google/Microsoft
  regresan por `/auth/callback` y completan la autorización automáticamente;
  ese callback ahora acepta sólo destinos internos para cerrar el open redirect
  que existía en su parámetro `next`. Este login social sólo autentica Baiyer:
  no vuelve a pedir scopes de Gmail/Outlook ni toca la conexión del buzón.
- `POST /api/mcp/oauth/consent/session` verifica el access token Supabase contra
  Auth antes de consumir atómicamente el request pendiente y emitir el código
  MCP de un solo uso. La contraseña se procesa en Supabase desde el navegador y
  nunca llega al servidor MCP. Cancelar también consume el request. `GET
  /api/mcp/oauth/request/{request_id}` entrega al frontend sólo nombre del
  cliente y scopes; no expone redirect URI ni PKCE.
- `/api/mcp/connections` enriquece el `client_id` aleatorio de DCR con el
  `client_name` registrado para que la pantalla muestre "Codex"/"Claude Code"
  en vez de un identificador opaco. Verificación: 416 pruebas backend passing +
  1 test Gemini real deseleccionado; `next build` completo y QA visual desktop/
  móvil correctos. `tsc --noEmit` conserva sólo la deuda preexistente ya
  documentada en calendario/resultados/estadísticas/proyectos/reportes.

## Navegación — Chat IA y API ocultos (2026-08-24)
- `frontend/components/AppShell.tsx` ya no incluye `Chat IA` (`/chat`) ni `API`
  (`/developers`) en la sección «Sistema» del menú lateral. El cambio aplica al
  riel de escritorio y al drawer móvil porque ambos renderizan el mismo `NAV`.
- Las páginas y rutas se conservan: siguen accesibles por URL directa para no
  romper enlaces ni integraciones existentes; sólo se ocultaron de la
  navegación principal. `MCP` y `Configuración` permanecen visibles.
- **2026-08-25:** mismo criterio para `Estadísticas`, `Calendario`, `Recurrencias`
  y `Reportes` (sección «Gestión»), más el botón "Generar reporte PDF" de
  `/proyectos/[id]`, que era el último enlace de navegación a una de esas
  secciones. Las entradas siguen en `BREADCRUMB` para que la cabecera funcione
  al entrar por URL directa. El botón "Exportar Excel" de proyectos se conserva:
  descarga desde el backend sin navegar a `/reportes`.
- Cambio desplegado desde `main` en el commit `d827263`; `next build` verificado.

6. Probar Supplier Capability Intelligence (024) con datos reales: completar un onboarding y confirmar que aparece la fila en `procurement_profiles`; hacer una búsqueda y confirmar que se crea `search_sessions`; usar "Rebuscar con contexto" y confirmar que cae en `search_feedback`.
7. Verificar visualmente Fases 4–6 de Supplier Capability Intelligence con proveedores categorizados, enviar una RFQ agrupada de prueba desde Gmail y recorrer una búsqueda complementaria hasta el comparador.
8. ~~Eliminar `procurement.py` + `frontend/app/procurement/`~~ — hecho el 2026-08-24 (ver Gotchas). Queda pendiente decidir qué hacer con el Gantt sin uso (`proyectos.py`), dentro de `PLAN_DATA_FOUNDATION.md`.

## Workflow de compras + comunicaciones unificado (PRD, Fases A-G — 17-08-2026)
Proyecto nuevo, grande, **no confundir con el "Workflow Builder" ya descrito arriba** (ese sigue
siendo la fuente real de autorización/magic link). El contrato completo está en
`PRD_WORKFLOW_COMUNICACIONES_UNIFICADO.md` (raíz, sin trackear en git todavía) — 7 fases (A-G) para
convertir cada tarjeta del canvas en una unidad ejecutable con responsables por acción, loops de
correo declarativos y un motor que recorre el ciclo completo (RFQ → autorización → homologación →
OC → despacho), reemplazando gradualmente el flujo legado. Es deliberadamente incremental: el propio
PRD exige "una fase por vez" y checkpoints, no un big-bang.
- **Fase A completa. Migración 041 aplicada y verificada en Supabase producción el 17-08-2026.**
  `backend/migrations/041_workflow_communications_foundation.sql`
  (crea `workflow_node_assignments`, `workflow_node_communication_rules`, `workflow_node_executions`,
  `workflow_scheduled_actions`, más las RPCs atómicas `claim_workflow_scheduled_action` y
  `reserve_mail_delivery_event`, con RLS por organización — no toca comportamiento productivo, sólo
  agrega), `backend/app/services/workflow_automation.py` (validación pura `validar_automatizacion()`
  del modelo tarjeta/asignación/regla, sin tocar Supabase, con `clave_idempotencia()` determinística),
  `backend/app/services/workflow_automation_service.py` (persistencia mínima: `crear_ejecucion_nodo`,
  `programar_accion` idempotente, `reservar_accion` vía RPC atómica). `backend/app/services/mail_template_service.py`
  agrega `reservar_envio()` (reserva atómica antes de enviar, vía la RPC de la 041). Desde Fase C,
  `listas.py` usa la reserva previa para autorizaciones unificadas; el camino legacy y los demás
  emisores (`oc.py`, `recurrencia_service.py`, `gmail_conversation_agent.py`) conservan
  `registrar_envio()` hasta sus fases de migración.
- **Fase B completa:** CRUD autenticado/admin de asignaciones y reglas por tarjeta; canvas con
  responsables individual/paralelo/secuencial, biblioteca/edición de correos internos y externos,
  configuración de loops y validación conjunta grafo+automatización. El chat puede proponer
  `configurar_comunicacion`. `/settings/comunicaciones` queda como biblioteca global; la asignación
  operacional se hace dentro de cada tarjeta.
- **Fase C completa:** `workflow_scheduler.py` consume cada minuto acciones vencidas con lease
  atómico; el flujo real de autorización opta por el motor nuevo sólo cuando la instancia declara
  `execution_owner=unified`. El correo inicial y los recordatorios reservan su idempotency key antes
  de Gmail, los fallos ambiguos quedan `delivery_uncertain` y nunca se reenvían automáticamente.
  Una decisión cancela sus recordatorios, el cierre del tramo completa la ejecución, y el agotamiento
  pausa la instancia (nunca autoaprueba). Hay endpoints admin para pausar/reanudar y una vista de
  automatización/trazabilidad por instancia. No requirió migración adicional a la 041.
- **Fase D completa y habilitada:** RFQ batch queda enlazada a instancia/ejecución/proveedor mediante
  `backend/migrations/042_workflow_rfq_execution.sql` (**aplicada manualmente en Supabase y confirmada
  por el usuario el 17-08-2026**). El envío inicial usa `rfq_requested` contextual y reserva previa; `rfq_followup` corre
  por proveedor en el mismo hilo Gmail. El agente Gmail y la carga manual normalizan
  `rfq_respuesta_recibida`/`rfq_completa`, cierran sólo el loop del proveedor y evalúan
  `todos_resueltos`, `minimo_respuestas` o `cierre_manual`. El agotamiento puede descartar proveedor;
  si todos se descartan sin cotización, la instancia se pausa. La instancia RFQ se reutiliza luego
  en autorización para no partir un segundo motor. Canvas permite configurar el criterio agregado.
- Verificación al cierre de Fase D: compilación Python correcta, 44 pruebas enfocadas, suite backend
  completa de 310 pruebas pasando y build Next.js correcto.
  La migración 042 fue aplicada manualmente y confirmada por el usuario.
- **Fase E completa y habilitada:** crea expedientes mínimos por proveedor
  (`supplier_homologation_cases`), asigna la tarea al homologador de la tarjeta, solicita antecedentes
  en el mismo hilo Gmail, ejecuta `supplier_intake_followup` y registra adjuntos recibidos sin
  autoaprobar. La pantalla `/listas/[id]/homologacion` permite al responsable/admin solicitar
  faltantes, homologar o rechazar. Sólo una decisión humana cierra cada caso; cuando todos terminan,
  la tarjeta avanza por `proveedor_homologado` o `proveedor_rechazado` hacia el nodo visible siguiente
  (incluida emisión de OC). No implementa scoring de riesgo ni validación bancaria/tributaria; eso
  pertenece al proyecto específico documentado en `DISENO_HOMOLOGACION_RIESGO_PROVEEDORES.md`.
- `backend/migrations/043_workflow_supplier_homologation.sql` también amplía el tipo de conversación
  Gmail con `homologacion`; **fue aplicada manualmente en Supabase y confirmada por el usuario el
  17-08-2026**.
- **Indicador en la lista (2026-08-20, commit `b24bcaf`):** `/listas/[id]` muestra el estado de
  homologación del proveedor definitivo junto a cada ítem, con "Ver más" que abre el expediente
  (antecedentes solicitados/recibidos, responsable, comentario). Consume
  `GET /api/workflows/homologacion/estado-items` y `/homologacion/casos`. `NIVEL_RIESGO_POR_ESTADO_FRONT`
  espeja a propósito el mapa de `workflow_homologation.py` — **si cambia uno hay que cambiar el otro**.
  El modal aclara explícitamente que el nivel es un proxy del estado documental y no un score
  verificado (no hay integración con SII/Mercado Público/buró); esa aclaración es deliberada, mostrar
  "riesgo bajo" a secas sugeriría una validación que no existe.
- Verificación al cierre de Fase E: 63 pruebas enfocadas, suite backend completa de 314 pruebas pasando,
  compilación Python, `git diff --check` y build Next.js correctos.
- **Fase F completa y habilitada:** las OCs creadas desde una lista
  en el nodo `emision_oc` quedan enlazadas a la instancia y ejecución unificadas. El correo inicial
  reserva su clave antes de Gmail, usa la plantilla de la tarjeta y deja `delivery_uncertain` ante
  cualquier resultado ambiguo. El acuse por magic link o respuesta Gmail cancela su loop y programa
  consultas de despacho; el aviso de despacho cancela los loops, ejecuta los avisos internos
  configurados y sólo cierra la tarjeta cuando **todas** las OCs de esa ejecución están despachadas.
  Copia de emisión, confirmación y despacho internas son opt-in por reglas de la tarjeta; el flujo
  legacy conserva sus correos anteriores. La vista operativa incluye eventos y métricas de ejecución,
  acciones, loops agotados y envíos inciertos.
- `backend/migrations/044_workflow_purchase_order_execution.sql` agrega a `ordenes_compra` los enlaces
  de lista/instancia/ejecución y el candado `execution_owner`; **fue aplicada manualmente en Supabase
  y confirmada por el usuario el 17-08-2026**.
- Verificación al cierre de Fase F: 20 pruebas enfocadas, 317 pruebas backend pasando y 1
  deseleccionada (el caso preexistente que llama Gemini real), compilación Python, `git diff --check`
  y build Next.js correctos. `tsc --noEmit` conserva errores preexistentes en calendario, resultados,
  estadísticas, proyectos y reportes; ninguno está en archivos tocados por F. Ese fue el checkpoint
  previo a implementar la Fase G descrita a continuación.
- **Fase G completa y habilitada, pendiente checkpoint productivo:**
  `workflow_rollout_settings` fija `legacy|unified` por organización. RFQ y autorización nuevas
  consultan esa bandera; cada instancia ya iniciada conserva para siempre su `execution_owner`, por
  lo que un rollback no reenvía correos ni abandona acciones en curso. La migración habilita sólo la
  cohorte que ya posee workflow activo con asignaciones y reglas explícitas por tarjeta; ausencia de fila
  equivale a `legacy`. Antes de aplicar 045 el código conserva temporalmente el opt-in A-F para evitar
  una ventana de corte durante el despliegue.
- `GET /api/workflows/rollout/estado` compara instancias, activas/completadas, eventos, loops agotados
  y entregas inciertas de ambos dueños. `PUT /api/workflows/rollout/estado` es sólo admin, valida el
  workflow antes de habilitar `unified` y permite volver a `legacy`; el cambio sólo gobierna compras
  nuevas. Operación y criterio de retiro físico documentados en `WORKFLOW_ROLLOUT_RUNBOOK.md`.
- `backend/migrations/045_workflow_rollout_control.sql` **fue aplicada manualmente en Supabase y
  confirmada por el usuario el 17-08-2026**.
  El código legacy se conserva deliberadamente hasta ejecutar y observar al menos un ciclo productivo
  controlado, tal como exige el PRD; retirar las bifurcaciones antes de ese checkpoint rompería el
  rollback y el criterio de compatibilidad.
- Verificación al cierre de código de Fase G: 28 pruebas focalizadas; suite backend de 325 pruebas
  pasando y 1 deseleccionada (Gemini real); compilación Python, `git diff --check` y build Next.js
  correctos.
- **TODO A-G está commiteado** (verificado 2026-08-20 con `git ls-files`: `workflow_automation.py`,
  `workflow_automation_service.py`, `workflow_execution.py`, `workflow_scheduler.py`,
  `workflow_homologation.py`, `workflow_rollout.py`, sus tests y las migraciones 041-045). Hasta el
  2026-08-20 este archivo afirmaba en cuatro lugares que A-D/E/F/G seguían sin commit; era información
  vieja. **Lo único realmente pendiente de la Fase G es el checkpoint productivo**: correr y observar
  al menos un ciclo real con `execution_owner=unified` antes de retirar las bifurcaciones legacy.

## Cubicación conversacional (primer corte)
- Motor puro en `backend/app/services/cubicacion.py`: unidades/dimensiones, conversiones, merma,
  formatos comerciales y recetas versionadas `completos@1`/`pintura@1`, más evaluación solar
  cotizable como servicio profesional con advertencias; sin `eval` ni aritmética LLM.
- `/api/identificar` activa el contrato sólo con `modo_cubicacion_conversacional`; usa
  `respuestas_cubicacion` estructuradas y conserva intactos a los clientes antiguos.
- `/cotizar` pregunta máximo tres datos por turno, no reenvía la imagen y muestra trazabilidad
  neto/compra antes de publicar mediante el flujo real de cotizaciones y listas.
