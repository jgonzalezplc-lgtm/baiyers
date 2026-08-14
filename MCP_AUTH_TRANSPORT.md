# Baiyer MCP — Transporte y autenticación

Estado: Fase 2 implementada en código; migración 039 aplicada y confirmada;
variables Railway configuradas; despliegue pendiente.

## Endpoint canónico

```text
https://baiyers-production.up.railway.app/api/mcp
```

Es Streamable HTTP estándar, stateless y JSON-RPC. El transporte legado
`/api/mcp/sse` + `/api/mcp/rpc` queda temporalmente disponible para desarrollo,
pero no se publica como endpoint de conexión.

## Discovery

```text
/.well-known/oauth-authorization-server
/.well-known/oauth-protected-resource
/.well-known/oauth-protected-resource/api/mcp
```

Una petición sin credenciales a `/api/mcp` responde HTTP 401 y
`WWW-Authenticate` apunta al Protected Resource Metadata con path.

## OAuth

- OAuth 2.1 Authorization Code.
- PKCE S256 obligatorio.
- `state` obligatorio.
- Dynamic Client Registration para clientes públicos.
- Redirect URI debe coincidir exactamente con una registrada.
- HTTPS obligatorio, salvo loopback HTTP para CLI/clientes locales.
- RFC 8707 `resource` obligatorio en autorización y token inicial.
- Access token opaco de 60 minutos.
- Refresh token opaco de 30 días, rotativo y de un solo uso.
- Access/refresh tokens se guardan solo mediante SHA-256.
- Revocar un token revoca toda su familia inmediatamente.
- El resource server valida resource/audience y organización actual.
- Los scopes de cada tool se verifican nuevamente dentro del handler.

## Migración

`backend/migrations/039_mcp_oauth_secure.sql` fue aplicada y confirmada en
Supabase producción el 2026-08-14. `mcp_oauth_tokens` y
`mcp_auth_codes.consumed_at` responden correctamente.

## Railway

Configurar en el servicio backend:

```text
MCP_ISSUER_URL=https://baiyers-production.up.railway.app
MCP_RESOURCE_URL=https://baiyers-production.up.railway.app/api/mcp
MCP_ACCESS_TOKEN_MINUTES=60
MCP_REFRESH_TOKEN_DAYS=30
MCP_ALLOWED_HOSTS=baiyers-production.up.railway.app
MCP_ALLOWED_ORIGINS=https://claude.ai,https://claude.com,https://chatgpt.com
```

Los clientes nativos normalmente no envían `Origin`; los hosts/orígenes se
mantienen explícitos para conservar protección contra DNS rebinding.

## Tools disponibles al terminar Fase 2

La superficie inicial verifica transporte y reutiliza la fundación de Fase 1:

```text
baiyer_status
list_lists
get_job
describe_query_schema
query_baiyer_data
```

Las herramientas operativas restantes se incorporan en las fases de dominio.

## Verificación antes de conectar clientes

1. Migración 039 aplicada y verificada.
2. Configurar variables Railway.
3. Desplegar backend.
4. Verificar los tres endpoints discovery.
5. Confirmar que `/api/mcp` sin token entrega 401 + `WWW-Authenticate`.
6. Probar DCR, autorización, intercambio PKCE, refresh y revocación.
7. Probar `initialize`, `tools/list` y `tools/call` con MCP Inspector.
8. Recién entonces agregar la URL a Codex y Claude.
