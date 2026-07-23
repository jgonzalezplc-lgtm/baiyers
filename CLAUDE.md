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
- `onboarding.py` — `investigar-empresa`: desde dominio o nombre, con Gemini + scraping, devuelve empresa/industria/país/logo/RUT/categorías.
- `contacto.py` + `services/contacto_scraper.py` — al cotizar, scrapea email + WhatsApp del proveedor y arma mensaje pre-hecho (`wa.me`).
- `cuenta.py` — `/api/cuenta/eliminar` (darse de baja; verifica token, borra usuario auth).
- `listas.py` — listas de cotización multi-ítem (guardadas como JSON en `proyectos.descripcion`; lock por lista).
- Otros: `cotizaciones`, `oc`, `aprobaciones`, `proyectos` (Gantt), `analisis` (IA), `gmail`, `facturas` (parser de correos entrantes), `procurement`, `ledger`, `recurrencias`, `estadisticas`, `chat`, `historico`, `suppliers`, `proveedores_import`, MCP + API pública.

### Ruteo por categoría (`services/categoria_mapper.py`)
Cada categoría → set de fuentes. **carpinteria** = maderas + retail construcción (SIN eléctrico). **construccion/mecanico/consumible** sin eléctrico. **electrico/electronica** = electrónica + eléctrico CL. Fuentes de madera tienen gate de keywords (se auto-filtran). **Pendiente:** el bucket electrónica/eléctrico aún mezcla componentes (arduino) con materiales eléctricos (cables) — falta afinar.

### Matching de relevancia (`services/relevancia.py`)
Descarta derivados/accesorios (ej: "barniz de madera" al buscar tablones) con negativas por categoría + patrón "X para <ítem>".

### Fuentes de scraping (`services/fuentes/`)
`retail_cl.py` (Sodimac, Easy, La Sierra, Construmart, Vitel, Dartel, Ferrelectrica, Gobantes, Rhona), `maderas_cl.py` (CLC, W Maderas, Ferramenta + directorio aserraderos con gate de keywords), `mouser/digikey/tme`. **Arquitectura hardcodeada** — pendiente convertir a registro data-driven.

## Auth & Onboarding (frontend)
- Login/registro: **email/password + Google OAuth** (funcionan). Outlook **oculto** (`{false && ...}` en login/register) — Azure AD requiere cuenta Microsoft de trabajo.
- Callback OAuth: `frontend/app/auth/callback/page.tsx` es **client-side** (evita el host interno `localhost:8080` del proxy). Signout: `app/auth/signout/route.ts`.
- Onboarding: `frontend/app/onboarding/page.tsx` — **chat conversacional** que revela empresa/logo/rubro, pregunta RUT, nombre del usuario, logo y proceso de compra. Guarda perfil en **`user_metadata`** (empresa, industria, rut, logo_url, pais, categorias_default, nombre_usuario, proceso_compra, onboarding_completo).
- Dashboard saluda con logo+nombre; búsquedas usan `industria` como contexto.

## Gotchas importantes
- **Migraciones = manuales.** El service key de Supabase NO hace DDL. Correr los `.sql` de `backend/migrations/` en el SQL Editor de Supabase. Aplicadas: 015 (columna `metadata` en resultados + constraint fuente), 016 (fuentes madera), 017 (plan 'free' permitido). El código tiene degradación si `metadata` falta, pero se pierde título/descr.
- **credentials.json** (OAuth Gmail) está **gitignored** — en prod se usan env vars `GOOGLE_CLIENT_ID`/`GOOGLE_CLIENT_SECRET`.
- **SMTP:** Resend configurado en Supabase (dominio baiyer.cl verificado). Correos de auth (confirmación/recuperación) salen desde `no-reply@baiyer.cl`.
- **Serper.dev** integrado (2.500 búsquedas gratis; `SERPER_API_KEY`). Prioriza sobre SerpAPI.
- Secretos expuestos en capturas durante el desarrollo (Supabase service key, Gemini, SerpAPI, Serper) — **rotar** por higiene.

## Env vars
- **Backend (Railway `baiyers`):** SUPABASE_URL, SUPABASE_SERVICE_KEY, GEMINI_API_KEY, SERPER_API_KEY, SERP_API_KEY, ANTHROPIC_API_KEY (vacío), ENVIRONMENT=production, CORS_ORIGINS (incluye baiyer.cl + railway), FRONTEND_URL=https://www.baiyer.cl, GOOGLE_CLIENT_ID/SECRET, GOOGLE_REDIRECT_URI.
- **Frontend (Railway `sweet-trust`):** NEXT_PUBLIC_SUPABASE_URL, NEXT_PUBLIC_SUPABASE_ANON_KEY, NEXT_PUBLIC_API_URL=https://baiyers-production.up.railway.app.

## Costos infra
Railway ~$5-10/mes · Supabase free · Serper 2.500 gratis→$50/50k · Gemini free tier. WhatsApp y SII (futuros) sí cuestan.

## Estado y roadmap
Ver `handoff.md` para el estado detallado y las 4 fases del roadmap.
