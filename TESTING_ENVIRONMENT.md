# Entorno de testing de Baiyer

## Objetivo

Todo cambio entra primero a `testing`, se valida en una copia aislada de la aplicación y sólo
después de QA se promueve a `main`. `main` sigue siendo la única rama que despliega producción.

```text
rama de trabajo -> PR a testing -> CI -> deploy testing -> QA
                                                    |
                                                    v
                                      PR testing a main -> producción
```

## Infraestructura que debe existir

Crear un ambiente **staging/testing** en Railway con dos servicios clonados:

- Backend: root `backend`, rama `testing`.
- Frontend: root `frontend`, rama `testing`.
- Dominio sugerido: `testing.baiyer.cl` para frontend y el dominio Railway del backend.
- Health check del backend: `/api/health`; debe responder `environment: testing`.

Crear además un proyecto Supabase independiente. No reutilizar el proyecto productivo
`zsssebwpnmsiklzwbrxh` y no copiar usuarios, tokens OAuth, conversaciones, cotizaciones ni datos
personales. Aplicar en testing las migraciones en el mismo orden antes de promoverlas a producción.

## Variables de testing

Backend Railway:

```dotenv
ENVIRONMENT=testing
CRON_ENABLED=false
SUPABASE_URL=https://<proyecto-testing>.supabase.co
SUPABASE_SERVICE_KEY=<service-key-testing>
FRONTEND_URL=https://testing.baiyer.cl
CORS_ORIGINS=https://testing.baiyer.cl
GOOGLE_REDIRECT_URI=https://<backend-testing>/api/gmail/callback
```

Las API keys externas pueden ser cuentas/cuotas de testing. No configurar Gmail OAuth hasta tener
usuarios QA dedicados. Mantener `CRON_ENABLED=false`; así el clon no sincroniza buzones ni envía
ratings o recurrencias automáticas.

Frontend Railway:

```dotenv
NEXT_PUBLIC_ENVIRONMENT=testing
NEXT_PUBLIC_API_URL=https://<backend-testing>
NEXT_PUBLIC_SUPABASE_URL=https://<proyecto-testing>.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=<anon-key-testing>
```

En Supabase testing, registrar `https://testing.baiyer.cl/auth/callback` en Auth URL Configuration.
En Cloudflare, crear el CNAME de `testing.baiyer.cl` hacia el dominio indicado por Railway.

## Protección de ramas en GitHub

Configurar rulesets:

1. `testing`: exigir pull request y los checks `Backend` y `Frontend`.
2. `main`: exigir pull request, los mismos checks y al menos una aprobación de QA.
3. Bloquear pushes directos y force-pushes en ambas ramas.
4. Railway testing observa `testing`; Railway producción observa exclusivamente `main`.

## Promoción y rollback

1. Crear una rama `codex/...` o `feat/...` desde `testing`.
2. Abrir PR hacia `testing`; CI debe quedar verde.
3. Probar login, cotización, listas, RFQ/correos con cuentas QA, aprobación y OC.
4. Registrar evidencia en el PR y aprobar QA.
5. Abrir PR de `testing` hacia `main`; no hacer cherry-picks sueltos.
6. Aplicar primero cualquier migración compatible hacia atrás y luego desplegar el código.
7. Si falla, revertir el PR de promoción en `main`. Las migraciones destructivas requieren un plan
   propio de rollback y respaldo previo.

## Regla de datos

Testing parte con datos sintéticos. Si un caso exige datos realistas, deben anonimizarse fuera de
producción antes de importarlos. Nunca copiar `auth.users`, `user_integrations`, access/refresh tokens,
emails, adjuntos ni secretos.
