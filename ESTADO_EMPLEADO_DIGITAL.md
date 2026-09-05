# Estado del empleado digital — handoff

**Última actualización: 2026-09-05.** Este archivo es la **continuidad** del proyecto: qué
está hecho, qué está a medias y qué decisiones ya se tomaron para no re-litigarlas.

No duplica otras fuentes, las apunta:

| Documento | Qué es |
|---|---|
| `PRD_EMPLEADO_DIGITAL.md` | **El contrato.** Decisiones, reglas duras, ejes, arquitectura, fases F1–F6. Leerlo primero. |
| `CLAUDE.md` | Guía del proyecto entero (arquitectura, convenciones, gotchas, env vars). `AGENTS.md` apunta ahí a propósito: una sola fuente de verdad para Codex y Claude Code. |
| Este archivo | Sólo el estado del empleado digital. |

---

## 1. Dónde está parado el proyecto

**Ninguna fase (F1–F6) está empezada.** Lo hecho hasta ahora es fundación: el registro de
capacidades, el parseo de adjuntos que F1 va a necesitar sí o sí, y el checkpoint de aislamiento
entre organizaciones que habilita iniciar F1.

No existen todavía `backend/app/services/empleado/`, `canales/` ni `pagos/`.

### Hecho y commiteado

- **`79ed1d9`** — PRD inicial + referencia de la API de tarjetas.
- **`a4befba`** — borrado del sanitizador de SQL y su llamador muerto.
- **`0047d58`** — **registro único de capacidades por efecto** (§4.1 del PRD).
  - `backend/app/services/tool_registry.py`: las **85 tools MCP** declaran efecto, scope, si
    ingieren contenido de terceros y qué rol del workflow las respalda.
    Reparto actual: **40 lectura / 37 escritura_interna / 2 externo / 6 dinero**.
  - `exige_autorizacion_humana()` ya devuelve la respuesta correcta. **El ejecutor de F1
    tiene que consultarla, no inventar su propio criterio.**
  - Es **declarativo**: nadie lo consulta para autorizar todavía, así que MCP se comporta
    igual que antes.
  - El mecanismo real es `backend/tests/test_tool_registry.py`, que lee el **AST de
    `streamable.py`** (no una lista escrita a mano) y falla si una tool no está declarada,
    si sobra una entrada o si el scope del código no coincide con el del registro. Igual
    que `tenant_guard`: una capacidad nueva **nace clasificada**.

### Hecho y commiteado (2026-09-05)

**Parseo de adjuntos de cotizaciones.** Un proveedor que responde con el precio en un PDF
adjunto ya no entra al sistema como una respuesta sin datos.

Archivos nuevos:
- `backend/app/services/adjunto_parser.py` — allowlist (PDF/XLSX/XLSM/XLS/PNG/JPEG/WEBP),
  tope 15 MB, descarga, sha256. **Word queda fuera a propósito.**
- `backend/app/services/documentos.py` — `texto_office()`, movido desde
  `routers/identificar.py` sin cambiarle la lógica.
- `backend/tests/test_adjunto_parser.py` (31 tests)
- `backend/tests/test_gmail_fuentes_adjuntas.py` (12 tests)

Modificados:
- `backend/app/services/email_understanding.py` — parámetro `documento` en
  `extraer_actualizaciones()`; línea anti-inyección en `PROMPT_BASE` (aplica al cuerpo
  también, no sólo al adjunto).
- `backend/app/routers/gmail.py` — `_extraer_de_todas_las_fuentes()`, umbral por origen,
  procedencia, resolución adjunto→mensaje→conversación en los dos listados.
- `backend/app/routers/identificar.py` — importa `texto_office` en vez de definirlo.
- `frontend/app/conversaciones/[id]/page.tsx` — muestra "Leído de `archivo.pdf`".

**Sin migración y sin dependencias nuevas**: las columnas `texto_extraido`/`hash` de
`gmail_attachments` y el valor `'gmail_attachment'` de `source_type` existían desde la 019
y nunca se habían usado; `descargar_adjunto()` (`services/gmail_service.py:235`) llevaba
desde siempre sin un solo llamador.

Verificación al cierre: **904 passed, 3 skipped** (los skipped son el test de aislamiento,
opt-in). `tsc --noEmit` sólo con la deuda preexistente ya documentada. **Falta la prueba
end-to-end real** — ver §3.

---

## 2. Prerrequisito de la §6 del PRD — verificado

**Esto va antes de F1.** No es burocracia, está escrito en el PRD y hay una razón concreta.

`tenant_guard` cerró el borde HTTP, pero **el backend usa la service key, así que bypassea
RLS**. Adentro de un servicio, un `.eq("id", x)` al que se le olvidó el
`.in_("user_id", actor.organization_user_ids)` devuelve la fila de otra empresa y nada se
queja. El agente amplifica eso: encadena decenas de llamadas sin supervisión y entrega el
resultado **redactado en prosa**, donde una fila filtrada ya no parece una fila filtrada.

### Estado: test ejecutado en producción, 2026-09-05

`backend/tests/test_aislamiento_organizaciones.py` (sin commitear). Crea dos organizaciones
reales, siembra datos en B con un centinela, y ejecuta **22 capacidades con la identidad de
A pasándole los ids de B**. Incluye 4 escrituras (una fuga de escritura no la detecta
ninguna sonda de lectura) y un control negativo (B sí ve lo suyo).

Prueba en la capa de **servicios con `ApplicationActorContext`**, no por HTTP: `_actor()` de
`streamable.py` sólo traduce un token MCP a ese mismo contexto, así que probar ahí cubre al
agente y al MCP sin emitir tokens OAuth.

```bash
cd backend && PYTHONPATH=. BAIYER_TEST_AISLAMIENTO=1 \
  .venv/bin/pytest tests/test_aislamiento_organizaciones.py -v
```

**Es opt-in porque el proyecto no tiene entorno de test**: hay una sola Supabase y es la de
producción. Crea 2 usuarios de Auth y ~6 filas, y las borra al terminar. Si el proceso muere
entre el seed y el cleanup quedan huérfanas, todas con el prefijo `AISLAMIENTO-`.

Resultado: **3 passed**. Las 22 sondas cruzadas no devolvieron ni modificaron datos de B desde
la identidad de A; los listados de A quedaron limpios y el control negativo confirmó que B ve sus
propios datos. Durante la verificación se creó `052_facturas.sql` (la tabla faltaba en producción)
y se corrigió `historial_supplier()` para convertir un proveedor inexistente en 404, no en un error
técnico de PostgREST.

---

## 3. Lo primero que hay que hacer

1. **Probar el parseo de adjuntos end-to-end.** Es lo que decide si sirve; el resto son
   tests con fakes. Mandar una RFQ desde Baiyer, responder **desde otra cuenta de correo**
   con un PDF de cotización real y el cuerpo sin datos, esperar el cron de 1 minuto, y
   verificar que (a) `gmail_attachments.texto_extraido` quedó lleno, (b) aparece la
   propuesta con el nombre del archivo en `/conversaciones/[id]`, (c) el precio llega al
   comparador.
   **Responderse a uno mismo no sirve**: Gmail marca el mensaje como `SENT` y el agente lo
   trata como saliente (`gmail.py:858-864`).
2. Recién ahí, **F1**: cerebro (`services/empleado/`) + canal correo.

---

## 4. Decisiones ya tomadas — no re-litigar

- **La barrera vive en el código, no en el modelo.** El argumento `confirmed: bool` que
  llevan 28 de las 85 tools **no es una confirmación humana**: lo elige el propio modelo.
  Bajo MCP se tolera porque hay una persona leyendo; bajo el empleado digital no hay nadie
  en ese loop. Por eso `audit.py` ahora escribe `"asserted_by_model"` y no `"explicit"`.
- **Reemplazar `confirmed` por una barrera real** es lo que queda pendiente de §1. El SDK
  MCP 1.28.1 soporta `Context.elicit`, que alcanza para efecto `externo`; **`dinero`
  necesita la fila de aprobación persistida** que pide la regla dura 1 — una confirmación de
  sesión no es trazable a un responsable con rol. El registro ya distingue los dos casos.
- **`ESCRITURAS_SIN_CONFIRMED`** fija las escrituras que hoy NO piden `confirmed` siendo
  equivalentes a otras que sí (`create_list`, `rename_list`, `add_list_items`). No se
  cambió ninguna —sería tocar comportamiento— y el test **sólo deja achicar** ese conjunto.
- **Auto-aplicación desde adjuntos: umbral 0.95**, contra 0.85 del cuerpo
  (`UMBRAL_AUTO_APLICAR_ADJUNTO` en `gmail.py`). Decisión del dueño del producto. Motivo: el
  PDF lo controla por completo el proveedor (mejor vector de inyección que un cuerpo de
  correo) y el parseo de tablas falla distinto que el de prosa — se equivoca de columna, o
  toma el total de la línea por el unitario.
- **Pagos (F5): el límite es el saldo.** Yativo no ofrece merchant lock, MCC ni límite por
  transacción. Se fondea con el monto exacto de la OC autorizada, así que **el daño máximo
  es ese monto**. Hay 4 preguntas abiertas con el proveedor en el PRD §4.5, y la #1 (cómo se
  autentica la API) es **bloqueante total**.
- **El PAN y el CVV nunca se persisten, nunca se loguean y nunca entran a un prompt.**

---

## 5. Trampas concretas para quien siga

- **Verificar los modelos de Gemini contra `list_models()`, no de memoria.** Ya pasó:
  `escanear_boleta` pedía `gemini-1.5-flash`, retirado, y la función estaba muerta hacía
  quién sabe cuánto disfrazada de fallo transitorio del OCR.
- **`.maybe_single().execute()` devuelve `None`**, no un objeto con `.data = None`. Usar
  `ejecutar_maybe_single()` de `services/supabase.py`.
- **Ninguna migración numerada garantiza estar en producción.** Antes de asumir que una
  tabla existe, hacer una query real. `supplier_ratings` y `supplier_categories` están en
  `.sql` y **no existen** en prod.
- **El cron de correo corre cada 1 minuto sobre todos los usuarios.** Cualquier llamada a
  Gemini que se agregue en ese camino y no sea idempotente es un problema de **factura**
  antes que de correctitud. Por eso el parseo de adjuntos se saltea los que ya tienen
  `texto_extraido`, y hay un test que lo verifica por mutación.
- **Gemini está en cuenta pagada con recarga automática DESACTIVADA** (~6.854 CLP de saldo
  prepago al 2026-08-25). El techo real es ese saldo. `services/gemini_budget.py` **avisa,
  nunca corta** — decisión explícita.
- **`SERP_API_KEY` (SerpAPI) y `SERPER_API_KEY` (Serper.dev) son empresas distintas.** Hoy
  `SERP_API_KEY` tiene cargada una key de Serper, así que **el failover no tiene respaldo
  real detrás**.
- **Rotación de secretos pendiente y con el "dónde" identificado:** el 2026-08-27 se
  compartió por chat una captura de `backend/.env` legible con `SUPABASE_SERVICE_KEY`,
  `GEMINI_API_KEY` y `SERP_API_KEY`. **Ninguna se rotó.** La service key es la prioritaria:
  bypassea RLS y además firma el `state` de OAuth de correo (`services/oauth_state.py`), así
  que rotarla invalida los consentimientos en vuelo — ventana de 10 min.

---

## 6. Contexto de producto (sondeo LinkedIn, 2026-09-02)

Se comparó Baiyer contra una spec de puesto de procurement estratégico. Resultado: **~40-50%
de cobertura, mal distribuida.**

- **Por delante de lo pedido:** el flujo transaccional P2P completo y la gobernanza de
  autorizaciones (workflow builder con roles, umbrales por monto, motor unificado A–G).
- **Parcial:** spend analytics (hay reporting de gasto, no TCO ni benchmarking), vendor
  management (hay capacidades y homologación; **claims/NCR es cero**).
- **Cero, y es producto nuevo, no una feature faltante:** contratos (EPC/O&M/LTSA, ciclo de
  vida, análisis de cláusulas) e inventario (ver `DISENO_INVENTARIO.md`).

**Los tres huecos priorizados, en orden:**

1. ~~Parseo de adjuntos~~ — **hecho**, falta la prueba real (§3.2).
2. **Ponderación en el comparador.** `explain_quote_recommendation` ordena por
   `(campos_faltantes, precio, -rating)`: es menor precio con desempate, **no un modelo
   ponderado**. No hay pesos configurables ni criterio técnico vs. económico.
3. **Maestro de productos.** El estructural. Los ítems nacen ad-hoc en `cotizaciones` (texto
   identificado por Gemini); no existe una entidad SKU estable. Sin eso **no hay
   inventario, no hay benchmarking y no hay spend analytics por categoría de verdad**.
   Bloquea dos módulos a la vez.

Contratos se dejó fuera a propósito: es otro producto.
