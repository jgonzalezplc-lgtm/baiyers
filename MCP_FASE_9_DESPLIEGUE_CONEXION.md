# Baiyer MCP — Fase 9: despliegue y conexión

Estado: **desplegada; Codex validado y Claude MCP autenticado**
Fecha: 2026-08-14

## Resultado esperado

Un único servidor MCP remoto para Codex y Claude:

```text
https://baiyers-production.up.railway.app/api/mcp
```

El repositorio incluye configuración de proyecto para ambos clientes:

- Codex: `.codex/config.toml`
- Claude Code: `.mcp.json`

Ambos usan Streamable HTTP y OAuth 2.1 con PKCE. No se guardan contraseñas,
access tokens ni refresh tokens en el repositorio.

## 1. Variables del backend en Railway

Configurar en el servicio `baiyers` del proyecto `genuine-connection`:

```text
MCP_ISSUER_URL=https://baiyers-production.up.railway.app
MCP_RESOURCE_URL=https://baiyers-production.up.railway.app/api/mcp
MCP_ACCESS_TOKEN_MINUTES=60
MCP_REFRESH_TOKEN_DAYS=30
MCP_ALLOWED_HOSTS=baiyers-production.up.railway.app
MCP_ALLOWED_ORIGINS=https://claude.ai,https://claude.com,https://chatgpt.com
```

No reemplazar las demás variables del servicio. El cliente CLI normalmente no
envía `Origin`; la allowlist protege principalmente las conexiones web.

## 2. Despliegue

El push a `main` dispara el deploy automático del backend y frontend Railway.
Antes del push deben pasar las pruebas MCP y la regresión general. Después del
deploy, validar:

```bash
curl -i https://baiyers-production.up.railway.app/.well-known/oauth-authorization-server
curl -i https://baiyers-production.up.railway.app/.well-known/oauth-protected-resource/api/mcp
curl -i https://baiyers-production.up.railway.app/api/mcp
```

Los dos primeros deben responder `200`. El tercero, sin token, debe responder
`401` con `WWW-Authenticate` apuntando al Protected Resource Metadata.

## 3. Codex

La configuración de proyecto se activa al abrir este repositorio como proyecto
confiable. Alternativa global por CLI:

```bash
codex mcp add baiyer --url https://baiyers-production.up.railway.app/api/mcp \
  --oauth-resource https://baiyers-production.up.railway.app/api/mcp
codex mcp login baiyer
```

En el navegador, iniciar sesión con la cuenta Baiyer y autorizar. Reiniciar el
cliente si estaba abierto, ejecutar `codex mcp list` y usar `/mcp` para revisar
la conexión. La app de Codex, la CLI y la extensión comparten la configuración
del mismo host.

## 4. Claude Code

Claude detecta `.mcp.json` al abrir el proyecto. Si no lo hace, agregarlo al
scope del proyecto:

```bash
claude mcp add --transport http --scope project baiyer \
  https://baiyers-production.up.railway.app/api/mcp
claude mcp list
```

Abrir Claude Code, ejecutar `/mcp`, seleccionar `baiyer` y completar el login
OAuth en el navegador.

## 5. Prueba funcional mínima

Después de autenticar cada cliente:

1. Pedir: “Llama `baiyer_status` y dime la organización activa”.
2. Pedir: “Lista mis listas Baiyer sin modificar nada”.
3. Abrir una lista real y consultar cobertura o comparación.
4. Crear una lista de prueba sólo si se quiere validar escritura.
5. No probar envíos de correo, OC, pagos ni importaciones masivas sin una
   confirmación humana explícita y datos controlados.

## 6. Criterio de cierre

- Discovery y `401` estándar verificados en producción.
- OAuth completado desde Codex y Claude.
- `initialize`, `tools/list`, `baiyer_status` y `list_lists` funcionan.
- La llamada aparece en `mcp_tool_audit_log` sin argumentos ni respuestas.
- Los refresh tokens rotan y una conexión revocada deja de funcionar.

## Estado de cierre

- Las seis variables MCP fueron cargadas manualmente en el backend Railway el
  2026-08-14.
- Backend desplegado en Railway y discovery/401 validados en producción.
- Codex autenticado y `baiyer_status` ejecutado correctamente para la
  organización `Claria Soluciones de Software`.
- Claude Code autenticó correctamente el MCP y confirmó `Connected to baiyer`.
  La prueba de tool quedó pendiente únicamente porque expiró la sesión general
  de Claude Pro del CLI; renovar con `claude auth login` y repetir
  `baiyer_status`.
- Últimos arreglos productivos: pin del SDK MCP, metadata scoped, render del
  consentimiento y consumo del estado OAuth posterior a la autenticación.
