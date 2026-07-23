# HANDOFF — Baiyer (Cotizador Inteligente B2B)

Documento autocontenido para retomar el proyecto en un agente/sesión nueva (Codex, Claude, etc.).
Fecha de corte: sesión de desarrollo en curso.

---

## 1. Qué es Baiyer
Plataforma SaaS de **procurement/cotización B2B para Chile**. Flujo: el usuario describe qué
comprar en lenguaje natural → IA (Gemini) identifica y categoriza los ítems → se buscan
proveedores en paralelo (scrapers de tiendas chilenas + MercadoLibre + Google Shopping vía
Serper.dev) → se comparan precios y se filtra relevancia → se cotiza (correo/WhatsApp) → OC.
Onboarding inteligente estilo "Ploy" que detecta la empresa desde el correo.

## 2. Infraestructura (todo desplegado y funcionando)
| Pieza | Detalle |
|---|---|
| **Repo** | github.com/jgonzalezplc-lgtm/baiyers (público). Push a `main` → auto-deploy Railway. |
| **Backend** | FastAPI (Python 3.11), `backend/`, Dockerfile (usa `$PORT`). Railway servicio `baiyers`. URL: `https://baiyers-production.up.railway.app`. |
| **Frontend** | Next.js 16 App Router (TS), `frontend/`. Railway servicio `sweet-trust`. |
| **Dominio** | `https://www.baiyer.cl` → Cloudflare (DNS: nameservers a Cloudflare) → Railway. SSL OK. |
| **DB + Auth** | Supabase (ref `zsssebwpnmsiklzwbrxh`, us-west-2). |
| **Hosting** | Railway plan Hobby (~$5-10/mes). Proyecto `genuine-connection` (2 servicios). ⚠️ Borrar proyecto huérfano `bountiful-presence`. |
| **Correo** | Resend (SMTP en Supabase, dominio baiyer.cl verificado). Auth emails desde `no-reply@baiyer.cl`. |
| **Búsqueda web** | Serper.dev (Google Shopping, `SERPER_API_KEY`, 2.500 gratis). Fallback SerpAPI. |
| **IA** | Gemini (`gemini-2.5-flash`) para identificación, onboarding, análisis. Anthropic key vacía. |

## 3. Cómo correr / desplegar
```bash
# Local
cd backend && .venv/bin/uvicorn app.main:app --port 8000
cd frontend && npm run dev   # :3000
# Deploy: git push origin main  (Railway redeploya solo ambos servicios)
```
**Migraciones:** correr manualmente los `.sql` de `backend/migrations/` en el SQL Editor de
Supabase (el service key NO hace DDL). Aplicadas: 015, 016, 017.

## 4. Estado por módulo (visión de 9 puntos)

### ✅ Construido y funcionando
1. **Auth & Onboarding:** email/password + Google OAuth. Onboarding **conversacional (chat)** que
   investiga la empresa desde dominio o nombre (Gemini + scraping): empresa, industria, país, logo,
   RUT; pregunta RUT/nombre/logo/proceso de compra; guarda en `user_metadata`. SMTP Resend andando.
   "Darse de baja" en Configuración. Outlook **oculto** (Azure requiere cuenta MS de trabajo).
2. **Búsqueda inteligente:** identificación semántica (Gemini), ruteo por categoría, conectores
   (ML + Serper + scrapers CL + electrónica), matching de relevancia anti-basura, MCP + API pública.
3. **Selección & aprobación:** comparador, análisis IA, informes PDF (incl. "mejor precio"),
   aprobaciones con magic link, contacto por WhatsApp/email (scraping del proveedor).
4. **Listas multi-ítem**, **Proyectos + Gantt**, descomposición proyecto→materiales.
5. **Correo entrante:** `factura_parser.py` con `scan_inbox`/`procesar_email_entrante` (parcial).

### 🔴 Faltante / deuda
- **Outlook OAuth** (Azure AD backend) — pausado.
- **SII (verificación de riesgo tributario)** — inexistente.
- **Panel de tracking** con ciclo completo de estados (Pendiente→Esperando→Cotizado→Aprobado→
  Comprado→Tránsito→Recibido) — hoy estados básicos.
- **WhatsApp bidireccional** (Twilio/Meta) — solo links `wa.me`.
- **OCR de facturas/PDF históricos** — no hay (usar Gemini Vision).
- **Modelo dual de proveedores** (datos de negocio/banco vs. historial) — básico.
- **Registro de conectores escalable** — scrapers hoy hardcodeados.
- **Cubicación de proyectos desde planos PDF** — no existe.
- Bucket de categoría **electrónica/eléctrico** mezcla componentes (arduino) con materiales
  eléctricos (cables) — falta afinar el ruteo (los demás buckets ya se limpiaron).

## 5. Roadmap en 4 fases (prioridad · dificultad)
- **Fase 1 — Auth/Onboarding/Correo:** ✅ casi completa. Falta Outlook (media). SMTP ✅.
- **Fase 2 — Motor de compra & proveedores:** registro de conectores (alta·media), agente de correo
  bidireccional robusto (alta·compleja), BD proveedores dual + ingesta OCR con Gemini Vision
  (alta·compleja), homologación de precios + MCP (media), OC masiva al aprobar (alta·media).
- **Fase 3 — Tracking, SII & cierre:** panel tracking + estados (alta·compleja), SII + scoring
  (alta·compleja, requiere servicio SII o scraping), WhatsApp (media, Twilio/Meta), alertas/retrasos
  vía LLM (media), recepción & cierre (media).
- **Fase 4 — Proyectos & ingeniería:** carga PDF planos + chat (alta·compleja, Gemini), **motor de
  cubicación** (alta·muy compleja), Gantt avanzado (media), informe final real vs. estimado (media).

## 6. Costos de infra extra (Claude Pro/Codex cubren el dev)
Railway ~$5-10/mes · Supabase free · Serper 2.500 gratis→$50/50k · Gemini free. **Solo si se activan:**
WhatsApp (Twilio ~$0.005/msg o Meta Cloud API 1.000 conv/mes gratis), SII (servicio ~$0.01-0.05/consulta
o scraping gratis frágil), OCR (evitable con Gemini Vision = $0).

## 7. Gotchas críticos (leer antes de tocar código)
1. **Migraciones manuales** en Supabase SQL Editor (service key no hace DDL).
2. **Next ignora errores TS/lint** en build (`next.config.js`). Verificar con `tsc --noEmit`.
3. **OAuth callback client-side** (`app/auth/callback/page.tsx`) — no server route, porque el proxy
   de Railway expone host interno `localhost:8080`. Usar `x-forwarded-host` en cualquier redirect server.
4. **credentials.json gitignored**; prod usa env vars GOOGLE_CLIENT_ID/SECRET.
5. **Secretos expuestos en capturas** durante dev (Supabase service key, Gemini, SerpAPI, Serper) →
   **rotar** por seguridad.
6. Estilo Swiss (IBM Plex Mono, `#c0392b`, radius 0, variables CSS). UI en español.
7. Listas de cotización se guardan como JSON en `proyectos.descripcion` (no hay tabla dedicada aún).

## 8. Env vars
**Backend:** SUPABASE_URL, SUPABASE_SERVICE_KEY, GEMINI_API_KEY, SERPER_API_KEY, SERP_API_KEY,
ANTHROPIC_API_KEY(vacío), ENVIRONMENT=production, CORS_ORIGINS, FRONTEND_URL, GOOGLE_CLIENT_ID,
GOOGLE_CLIENT_SECRET, GOOGLE_REDIRECT_URI.
**Frontend:** NEXT_PUBLIC_SUPABASE_URL, NEXT_PUBLIC_SUPABASE_ANON_KEY, NEXT_PUBLIC_API_URL.

## 9. Próximo paso sugerido
**Fase 2 — Agente de cotización por correo** (el core del producto): que Baiyer envíe las
solicitudes de cotización a los proveedores (desde `@baiyer.cl` con reply-to al usuario, vía Resend)
y **escuche/parsee las respuestas** con LLM para llenar precios/plazos/facturación automáticamente,
alimentando el comparador. Alternativa de arranque más simple: **registro de conectores** (convertir
los scrapers hardcodeados en `services/fuentes/` a un registro data-driven con tags/keywords, que
también afina el ruteo del caso arduino/eléctrico).

## 10. Mapa de archivos clave
- Backend routers: `backend/app/routers/` (identificar, buscar, onboarding, contacto, cuenta,
  listas, cotizaciones, oc, aprobaciones, proyectos, analisis, gmail, facturas, ...).
- Servicios: `backend/app/services/` (categoria_mapper, relevancia, contacto_scraper, email_finder,
  gmail_service, factura_parser, precio_historico, supplier_intelligence, fuentes/).
- Frontend páginas: `frontend/app/` (onboarding, cotizar, cotizar/[id]/resultados, listas,
  listas/[id], dashboard, settings, (auth)/login, (auth)/register, auth/callback, auth/signout).
- Componentes: `frontend/app/cotizar/components/` (CardProveedor, ResultadoIdentificacion,
  ResultadoIdentificacionMulti, FormularioCotizar), `frontend/components/` (AppShell, InformeLista,
  InformeCotizacion, EmailPreviewModal).
