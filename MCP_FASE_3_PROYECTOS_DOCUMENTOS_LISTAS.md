# Baiyer MCP — Fase 3: proyectos, documentos y listas

Estado: **implementada en código y pruebas locales**
Fecha: 2026-08-14

## Alcance

Esta fase permite que un cliente MCP convierta una conversación o documento
en una lista operativa de Baiyer y la mantenga después. Toda operación usa el
actor y la organización del token; ningún argumento `user_id` concede acceso.

## Tools

### Intake por conversación

- `start_project_intake(description, industry?)`: interpreta una necesidad o
  proyecto y crea un draft. Puede devolver preguntas de cubicación.
- `continue_project_intake(draft_id, answers)`: responde esas preguntas sin
  perder el contexto del draft.
- `commit_project_intake(draft_id, idempotency_key, confirmed, list_name?)`:
  crea cotizaciones y lista en una transacción. Exige `confirmed=true`.

### Documentos

- `preview_document_import(file_base64, file_name, file_mime, ...)`: admite
  PDF, DOCX, XLS y XLSX, máximo 15 MB. Detecta todas las filas, cantidades,
  unidades, partidas, supuestos y problemas; sólo guarda un draft temporal.
- `commit_document_import(draft_id, idempotency_key, confirmed, list_name?)`:
  consume un draft listo una sola vez y crea la lista atómicamente. No acepta
  drafts con cantidades/unidades pendientes ni sin confirmación explícita.

El contenido del archivo se trata como datos no confiables. El archivo
completo no se guarda en `integration_drafts`: se conserva el resultado
estructurado, nombre, MIME y hash SHA-256.

### Listas

- `list_lists(limit)` y `get_list(list_id)`
- `create_list(name, items)` para cotizaciones que ya existen
- `rename_list(list_id, name)`
- `add_list_items(list_id, items)`
- `update_list_item(list_id, cotizacion_id, ...)`
- `remove_list_item(list_id, cotizacion_id, confirmed)`

Los ítems mantienen su `cotizacion_id` estable. Eliminar un ítem también quita
su selección definitiva, pero nunca permite dejar una lista vacía.

## Flujo recomendado desde Codex o Claude

```text
Usuario: Cotiza la construcción de una bodega de 20 m².
Cliente: start_project_intake(...)
Baiyer: requiere datos de dimensiones/especificación
Usuario: responde las preguntas
Cliente: continue_project_intake(...)
Baiyer: devuelve preview y ready_to_commit=true
Cliente: muestra resumen y solicita confirmación
Usuario: confirma
Cliente: commit_project_intake(..., confirmed=true, idempotency_key=...)
Baiyer: crea cotizaciones + lista y devuelve list_id
```

Para documentos el flujo equivalente es
`preview_document_import → revisión/corrección → confirmación → commit_document_import`.

## Seguridad y consistencia

- Scopes: `projects:write`, `documents:write`, `lists:read`, `lists:write`.
- Drafts aislados por organización y con expiración de 24 horas.
- Commit documental/proyecto con clave de idempotencia.
- Confirmación conversacional obligatoria para commit y eliminación.
- Conversión cotizaciones + lista mediante la RPC transaccional de la 038.
- Sin llamadas internas a `localhost`.

## Verificación

- 38 pruebas específicas de las fases MCP aprobadas.
- La migración 039 fue confirmada en Supabase producción.
- No hay una migración de base de datos adicional para esta fase.

## Pendiente operativo

El código todavía debe desplegarse junto con las variables Railway descritas
en `MCP_AUTH_TRANSPORT.md`. Después se prueba el OAuth real y estas tools con
MCP Inspector, Codex y Claude. No se debe conectar un cliente al código viejo
de producción antes del despliegue coordinado.
