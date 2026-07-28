# PROJECT_STATUS.md — Baiyer (Cotizador Inteligente B2B)

> Handoff para continuar en Codex. Actualizado: 28-jul-2026 (America/Santiago).
> Escrito al cierre de una sesión larga en Claude Code centrada en el **agente de Gmail**
> (de cero a funcional end-to-end) y varios fixes de estabilidad encontrados en el camino.

## 1. Estado de Git y despliegue

- Repositorio: `/Users/macbook/Desktop/Cotizador` (rama `main`).
- Remoto: `https://github.com/jgonzalezplc-lgtm/baiyers.git` (público).
- `HEAD` local, `origin/main` y Railway están alineados en `cca1954 Fix: resultados.estado usa 'respondido', no 'respondio'`.
- Railway despliega automáticamente al hacer push a `main` (proyecto `genuine-connection`: servicio `baiyers` = backend, `sweet-trust` = frontend).
- **Migraciones aplicadas hasta la 021** (ver sección 3) — corren manualmente en el SQL Editor de Supabase, el service key no hace DDL.

```bash
git status
git log --oneline -15
git push origin main   # dispara el deploy en Railway
```

## 2. Arquitectura

- **Backend:** FastAPI (Python 3.11) en `backend/`, Dockerfile con `$PORT`.
- **Frontend:** Next.js 16 App Router (TypeScript) en `frontend/`, puerto interno 8080.
- **DB + Auth:** Supabase (`zsssebwpnmsiklzwbrxh`, us-west-2).
- **Cron:** `backend/app/services/cron.py` — `apscheduler` `BackgroundScheduler`, arrancado en `main.py`. Jobs: ratings (1h), recurrencias (1h), **sync de Gmail (1 min, nuevo)**.
- **Design system:** `frontend/components/ui/index.tsx` + `tokens.ts` + `app/globals.css`. Paleta clara/oscura con tokens `var(--brand)`, `var(--n-*)`, `var(--st-*)` (estados), componentes `Card`/`Badge`/`Input`/`BtnPrimary`/`BtnSecondary`/`PageHeader`/`Table*`/`EmptyState`. **Ojo:** hay tokens viejos (`var(--accent)`, `var(--text-*)`, `.btn-swiss-*`) que siguen funcionando como alias CSS pero están deprecados — quedan `CardProveedor.tsx`, `app/cotizar/page.tsx`, `SkeletonResultados.tsx`, `ResultadoIdentificacionMulti.tsx` sin migrar al patrón nuevo (`ResultadoIdentificacion.tsx` ya se migró, ver sección 4).
- **Dominio:** `www.baiyer.cl` → Cloudflare (DNS) → Railway.

## 3. El agente de Gmail — construido esta sesión, de cero

Objetivo: que Baiyer converse con proveedores por correo, entienda sus respuestas (precio,
disponibilidad, plazo, condiciones de pago) y actualice la cotización solo, sin que el
usuario tenga que estar pendiente del inbox.

### Esquema (migraciones 019, 020, 021 — todas aplicadas en prod)
- **019**: `gmail_conversations`, `gmail_messages`, `gmail_attachments`, `item_field_updates` (audit log / cola de propuestas).
- **020**: `proveedores.rut` + tabla `proveedor_contactos` (multi-contacto por proveedor) + `gmail_conversations.proveedor_id`/`contacto_id` (link real al directorio, ya no texto libre).
- **021**: agrega el estado `compra_iniciada` al CHECK de `gmail_conversations.estado` + columna `tipo` (`cotizacion`|`compra`).

### Piezas backend (`backend/app/routers/gmail.py`, `backend/app/services/`)
- `gmail_service.py` — threading real (`send_email_threaded` con `In-Reply-To`/`References`), `listar_mensajes_thread`, `extraer_texto_plano`, `extraer_adjuntos_meta`, `descargar_adjunto`.
- `email_understanding.py` — Email Understanding Agent (Gemini): extrae campos con nivel de confianza desde el cuerpo del correo, soporta multi-ítem, no inventa asociaciones ambiguas (`entity_id: null` si no está seguro).
- `proveedores_matching.py` — dedupe compartido (RUT normalizado → email/dominio de contacto → nombre normalizado) usado tanto por el import de Excel (`proveedores_import.py`) como por el agente, para que ambos escriban sobre el mismo directorio.
- `gmail_conversation_agent.py` — redacción **determinística** (no LLM, a propósito) de los 3 correos que el agente manda solo: agradecimiento, pedir lo que falta, e inicio de la etapa de compra.
- `_sincronizar_usuario(user_id)` (antes era el endpoint directo) — recorre conversaciones activas, trae mensajes nuevos del hilo (idempotente por `gmail_message_id` **y** por `procesado`, así un mensaje que falló a medias se reintenta solo), corre el Understanding Agent, y:
  - Campos "core" (precio/disponibilidad/plazo/condiciones) con confianza ≥0.85 se **auto-aplican** a `resultados` (quedan en `item_field_updates` como `aplicado`, trazable). El resto queda como `propuesta` para revisión humana en `/conversaciones`.
  - Si con eso ya está todo lo pedido → agradece y cierra la conversación sola. Si falta algo → pide sólo lo que falta.
  - Todo el bloque de procesamiento por mensaje está en un `try/except`: un error puntual marca la conversación `human_review_required` en vez de dejarla colgada en silencio.
- `sincronizar_todos_los_usuarios()` — la llama el cron cada minuto; itera todos los `user_id` con conversaciones activas.
- **Etapa de compra**: en `aprobaciones.py`, cuando una lista queda **aprobada sin observaciones**, por cada ítem definitivo con conversación de Gmail asociada se dispara `iniciar_proceso_compra()` — correo preguntando proceso de compra/OC/homologación/condiciones de pago, conversación pasa a `compra_iniciada`. Idempotente.
- **Mapeo de campos a columnas reales de `resultados`** (`_FIELD_MAP_RESULTADOS`): `precio_unitario→precio_cotizado`, `moneda→moneda_cotizada`, `plazo_entrega→plazo_entrega`, `condiciones_pago→condiciones_pago`. Lo que no tiene columna dedicada (ej. `disponibilidad`) cae acumulado en `notas_respuesta`. **Importante:** estos nombres de columna fueron un problema real (ver sección 5) — antes de tocar este mapeo, verificar contra el esquema real con `select('*').limit(1)`, no confiar en los `.sql` legacy de `backend/migrations/` (algunos nunca se aplicaron tal cual, ver más abajo).

### Piezas frontend
- `app/conversaciones/page.tsx` — listado (proveedor, asunto, estado, propuestas pendientes, link a Gmail). Botón "Sincronizar respuestas" = forzar ahora (ya no es la única vía, el cron corre solo).
- `app/conversaciones/[id]/page.tsx` — detalle: timeline de mensajes + panel de propuestas con Aplicar/Rechazar.
- `app/cotizar/[id]/resultados/page.tsx` — botón **"+ Proveedor de mi directorio"**: permite cotizarle a un proveedor propio (Excel/manual) sin depender del buscador automático. Nuevo endpoint `POST /api/cotizaciones/{id}/proveedor-directorio`.
- El envío (`/api/gmail/enviar`) ahora manda `resultado_id` real (antes sólo mandaba `cotizacion_id` + nombre, ambiguo si hay >1 resultado del mismo proveedor bajo la misma cotización).
- El correo generado (`/api/gmail/generar-correo`) ahora recibe `specs` reales (descripción de la IA + marca/modelo del resultado elegido) — antes el frontend nunca mandaba ese campo y el modelo inventaba "las especificaciones se adjuntan por separado".

## 4. Qué se estaba haciendo en este preciso momento

Encadenando fixes sobre pruebas reales end-to-end con un proveedor de prueba ("Usach",
correo real distinto al conectado, usado para simular respuestas de proveedor). Se
encontraron y corrigieron, en orden, estos bugs — **todos ya en `main` y deployados**:

1. Detección de dirección del mensaje (`outbound`/`inbound`) por comparación de texto del
   header `From` fallaba en auto-tests → se cambió a usar las `labelIds` de Gmail (`SENT`).
2. `/enviar` no mandaba `resultado_id` → ambigüedad cuando había >1 resultado del mismo
   proveedor.
3. `_items_contexto` le pasaba a Gemini el nombre genérico "ítem cotizado" porque
   consultaba una columna (`cotizaciones.nombre_item`) que no existe.
4. Idempotencia por sólo `gmail_message_id` (no por `procesado`) dejaba mensajes colgados
   para siempre si algo fallaba a mitad de proceso.
5. **`_FIELD_MAP_RESULTADOS` apuntaba a columnas que nunca existieron en producción**
   (`precio_respuesta`, `moneda_respuesta`, `respuesta_at` — de un `.sql` legacy
   `add_resultado_respuesta_fields.sql` que aparentemente nunca se corrió tal cual). Las
   columnas reales son `precio_cotizado`, `moneda_cotizada`, `respuesta_recibida_at`.
6. **Typo en el valor de `resultados.estado`**: el código escribía `"respondio"`, el CHECK
   constraint real sólo acepta `"respondido"` (entre otros). Esto tumbaba el `UPDATE`
   completo — y como el `item_field_updates` ya se había marcado `aplicado` *antes* de
   intentar escribir en `resultados`, la UI mostraba "Aplicada" sin que el dato hubiera
   llegado realmente, y además cortaba el resto de las propuestas del mismo correo sin
   procesar (precio y plazo se perdían, sólo quedaba lo primero que alcanzó a procesarse).
7. El botón "Sincronizar respuestas" era manual — se agregó el cron de 1 minuto para que
   el usuario no tenga que acordarse de apretarlo.
8. Se migró `app/cotizar/components/ResultadoIdentificacion.tsx` al design system actual
   (quedó pillado con el estilo viejo, el usuario lo notó por comparación visual).

**Lección para la próxima sesión:** antes de asumir el nombre de una columna en
`resultados`, `cotizaciones` o `proveedores`, verificar contra el esquema real:
```python
sb.table("resultados").select("*").limit(1).execute().data[0].keys()
```
Los `.sql` sueltos en `backend/migrations/` que no tienen número de secuencia
(`add_resultado_respuesta_fields.sql`, `add_cotizaciones_fields.sql`) no reflejan
necesariamente lo que hay en producción.

## 5. Errores / deuda pendiente

1. **Verificar en producción, de punta a punta, que el fix del typo `respondido` quedó
   bien.** Se reseteó manualmente en la DB la conversación de prueba "Silla Gamer" (dos
   registros) para que el cron la reprocese — falta confirmar que precio_cotizado y
   plazo_entrega quedan escritos y que el comparador de la lista los muestra.
2. **4 componentes de `/cotizar` sin migrar al design system nuevo**: `CardProveedor.tsx`,
   `app/cotizar/page.tsx`, `SkeletonResultados.tsx`, `ResultadoIdentificacionMulti.tsx`
   (mismo patrón que se acaba de aplicar a `ResultadoIdentificacion.tsx`: reemplazar
   `var(--accent)`/`.btn-swiss-*`/`var(--font-mono)` en body por `Card`/`Badge`/
   `BtnPrimary`/`BtnSecondary`/`var(--brand)`/`var(--n-*)`).
3. **Parseo de contenido de adjuntos (PDF/Excel) no implementado** — hoy sólo se guarda
   metadata del adjunto (`gmail_attachments`), no su texto/tabla extraída. Es el "Caso 2"
   del spec original del agente (cotización adjunta).
4. **Webhook Pub/Sub de Gmail sigue siendo un stub** (`/api/gmail/webhook`) — la
   sincronización real es por polling del cron cada 1 minuto, no push notification.
5. **Multi-contacto sin UI**: `proveedor_contactos` existe en el modelo y se usa desde el
   backend, pero no hay pantalla para que el usuario vea/administre los contactos de un
   proveedor (sólo se crean automáticamente al enviar/recibir correos).
6. **Ciclo de autorización con observaciones** (`rechazar ítems → aprobar con
   observaciones → modificar → reenviar → aprobar`) sigue sin probarse en producción
   punta a punta (deuda de la sesión anterior en Codex, no tocada esta vez).
7. **"Editar ciclo de autorizaciones"** en el dashboard sólo enlaza a Settings, sin
   funcionalidad real detrás.
8. **Errores de TypeScript preexistentes** (el build de Next los ignora vía
   `ignoreBuildErrors`): `ReactNode`/`unknown` en `calendario`, `cotizar/[id]/resultados`,
   `ReporteTemplate`; `Formatter` de Recharts en `estadisticas`, `proyectos/[id]`,
   `HistorialPrecioModal`; iteración de `Set<string>` en `cotizar/[id]/resultados`.
9. **SMTP propio pendiente en Supabase** (el gratuito no es apto para usuarios externos
   en producción).
10. **Secretos expuestos en capturas durante desarrollo** (Supabase service key, Gemini,
    SerpAPI, Serper, y el `GOOGLE_CLIENT_SECRET` rotado esta sesión) — pendiente rotación
    periódica por higiene.
11. **Datos huérfanos** si se borra un usuario directo desde Supabase (no vía
    `/api/cuenta/eliminar`): quedan filas sin dueño en `resultados`/`cotizaciones`/
    `proyectos`/`proveedores`/`ordenes_compra`.

## 6. Próximos 3 pasos exactos

1. **Confirmar en producción que el ciclo completo del agente de Gmail funciona sin
   intervención manual**: mandar una cotización real a un proveedor de prueba, responder
   desde otra cuenta con precio/disponibilidad/plazo/condiciones, esperar el cron (≤1 min,
   sin tocar el botón), y verificar que (a) el comparador de la lista muestra los datos,
   (b) llega el correo de agradecimiento automático, (c) al aprobar la lista sin
   observaciones se dispara el correo de inicio de compra.
2. **Migrar los 4 archivos de `/cotizar` restantes al design system** (ver sección 5.2).
3. **Implementar el parseo de adjuntos** (PDF/Excel de una cotización formal) para que
   actualice los mismos campos estructurados que una respuesta en el cuerpo del correo —
   es el próximo salto de valor grande del agente, ya con la infraestructura de
   `gmail_attachments` lista para colgarle el contenido extraído.

## 7. Comandos útiles

```bash
cd /Users/macbook/Desktop/Cotizador/backend

# Verificar que el backend importa
.venv/bin/python -c "import app.main"

# Ver el esquema real de una tabla (no confiar en los .sql sueltos)
.venv/bin/python -c "
from app.services.supabase import get_supabase
sb = get_supabase()
print(sb.table('resultados').select('*').limit(1).execute().data[0].keys())
"

# Frontend: type-check
cd ../frontend && npx tsc --noEmit

# Publicar
git push origin main
```
