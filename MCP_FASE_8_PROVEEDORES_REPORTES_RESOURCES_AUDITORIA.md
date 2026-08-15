# Baiyer MCP — Fase 8: proveedores, informes, resources y auditoría

Estado: **completada; migración 040 aplicada y verificada**
Fecha: 2026-08-14

## Proveedores e importación

Tools para buscar, leer, crear, editar, investigar, bloquear/desbloquear,
categorizar e importar proveedores. La importación CSV/XLS/XLSX usa
`preview_supplier_import → commit_supplier_import`, máximo 200 filas y 15 MB.
El commit reutiliza el dedupe real de Baiyer.

## Informes y métricas

- `generate_list_report`
- `get_spend_metrics`
- `get_supplier_metrics`
- `describe_query_schema` y `query_baiyer_data`

Los informes usan el modelo real de listas y la consulta semántica allowlisted;
no se expone SQL libre.

## Resources

Nueve templates read-only y autenticados: listas, comparación, RFQ,
respuestas, proveedores, aprobaciones, OC, facturas y jobs. Todos resuelven la
organización desde el token.

## Prompts

Los nueve prompts del contrato quedaron publicados: proyecto, documento,
cobertura, seguimiento, comparación, aprobación, OC, conciliación y análisis
de gasto. Son guías; no conceden permisos ni ejecutan acciones.

## Auditoría

`040_mcp_audit_log.sql` crea `mcp_tool_audit_log`. El middleware registra tool,
actor, organización, cliente, scopes, entidad, resultado, HTTP/JSON-RPC error,
duración y nivel de confirmación. La clave de idempotencia se guarda sólo como
SHA-256.

Nunca registra argumentos completos, tokens, documentos, PDFs, cuerpos de
correo, mensajes ni respuestas de proveedores.

## Verificación

- 64 pruebas específicas MCP aprobadas.
- 272 pruebas generales aprobadas salvo el test preexistente con Gemini vivo.
- 77 tools, 9 resource templates y 9 prompts.
- No se realizaron importaciones ni escrituras productivas.

## Migración

`backend/migrations/040_mcp_audit_log.sql` fue aplicada y verificada en
Supabase producción el 2026-08-14. La tabla `mcp_tool_audit_log` responde
correctamente y no se crearon datos productivos de prueba.
