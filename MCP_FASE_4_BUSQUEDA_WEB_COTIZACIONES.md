# Baiyer MCP — Fase 4: búsqueda web y cotizaciones

Estado: **implementada en código y pruebas locales**
Fecha: 2026-08-14

## Alcance

Esta fase conecta el MCP al motor real de búsqueda de Baiyer: MercadoLibre,
Google Shopping (Serper/SerpAPI), fuentes técnicas y comercios chilenos según
categoría, además de proveedores privados de la organización. No realiza
llamadas HTTP internas al backend.

## Tools

- `start_web_quote(idempotency_key, list_id?, cotizacion_id?)`: inicia una
  búsqueda normal para exactamente una lista o un ítem.
- `search_alternatives(...)`: repite el flujo con búsqueda ampliada en todas
  las fuentes habilitadas.
- `get_web_quote(job_id)`: entrega estado, progreso, resultados por ítem o
  error persistido.
- `get_item_quotes(cotizacion_id, limit)`: devuelve ofertas persistidas,
  precio, moneda, fuente, plazo, stock, rating, URL y relevancia.
- `get_list_coverage(list_id)`: indica por ítem cuántas ofertas existen,
  cuántas son relevantes, cuántas tienen precio y si el ítem está cubierto.
- `list_jobs(status?, job_type?, limit?)` y `get_job(job_id)`.
- `cancel_job(job_id, confirmed)`: cancelación cooperativa con confirmación.

## Flujo recomendado

```text
start_web_quote(list_id=..., idempotency_key=...)
  -> status=queued + job.id
get_web_quote(job.id)
  -> queued/running + progress + output parcial
get_web_quote(job.id)
  -> completed
get_list_coverage(list_id)
get_item_quotes(cotizacion_id)
```

Las búsquedas largas no mantienen abierta la llamada MCP. Cada ítem actualiza
el porcentaje y un resumen parcial en `integration_jobs`. Si Railway reinicia,
los jobs `queued` o `running` de tipo `web_quote` se recuperan al iniciar el
worker productivo.

## Seguridad y consistencia

- Scopes: `quotes:read`, `quotes:write`, `jobs:read`, `jobs:write`.
- Cada cotización y lista se valida contra los miembros de la organización.
- Una clave de idempotencia evita crear dos jobs equivalentes por reintentos.
- Resultados web se guardan en `resultados`, preservando RFQ ya contactadas.
- La cancelación se comprueba antes y después de cada búsqueda externa.
- No se expone correo privado completo ni SQL.

## Implementación

- `services/web_quote_service.py`: objetivos autorizados, ejecución,
  persistencia de progreso, recuperación, ofertas y cobertura.
- `services/mcp_jobs.py`: listado y cancelación de jobs.
- `mcp/streamable.py`: tools públicas y scopes.
- `main.py`: recuperación de jobs en el worker productivo.

## Verificación

- 44 pruebas específicas de MCP aprobadas.
- 221 pruebas generales aprobadas, excluyendo únicamente el test preexistente
  que llama Gemini en vivo y puede bloquear por reintentos externos.
- 23 tools publicadas en el catálogo MCP total.
- `git diff --check` sin errores.
- No requiere migración SQL adicional; reutiliza la 038.

## Pendiente operativo

Configurar las variables MCP de Railway, desplegar el bloque completo y hacer
una búsqueda controlada contra una cotización real. La búsqueda consume APIs y
scrapers externos, por lo que no se ejecutó automáticamente sobre producción.
