# PROJECT_STATUS.md — Baiyer (Cotizador Inteligente B2B)

> Snapshot técnico. Actualizado: 28-jul-2026 (America/Santiago). Para contexto de negocio y convenciones ver [CLAUDE.md](CLAUDE.md); para roadmap por fases ver `handoff.md`.
>
> **Nota:** este resumen fusiona dos hilos de trabajo que avanzaron en paralelo sobre el mismo repo — uno en esta sesión (Claude Code, onboarding/RUT/estabilidad del dashboard) y otro previo en Codex (autorización por ítem, dashboard de listas). Ambos ya están en `main`.

## 1. Estado de Git y despliegue

- Repositorio: `/Users/macbook/Desktop/Cotizador` (rama `main`).
- Remoto: `https://github.com/jgonzalezplc-lgtm/baiyers.git` (público).
- `HEAD` local, `origin/main` y Railway están alineados en `e51f4fd Mejora contraste de motivo de rechazo`.
- Railway despliega automáticamente al hacer push a `main` (servicios `baiyers` = backend, `sweet-trust` = frontend, proyecto `genuine-connection`).

```bash
git status
git log --oneline -10
git push origin main   # dispara el deploy en Railway
```

## 2. Arquitectura

- **Backend:** FastAPI (Python 3.11) en `backend/`, Dockerfile con `$PORT`.
- **Frontend:** Next.js 16 App Router (TypeScript) en `frontend/`, puerto interno 8080.
- **DB + Auth:** Supabase (`zsssebwpnmsiklzwbrxh`, us-west-2). Migraciones **manuales** (correr `.sql` de `backend/migrations/` en el SQL Editor — el service key no hace DDL). Última aplicada: `018_approval_comentario.sql`.
- **Persistencia de listas de cotización:** JSON dentro de `proyectos.descripcion` (no relacional); no requirió migración para los cambios recientes de autorización por ítem.
- **Autorizaciones:** tabla `approval_requests`; el detalle y las decisiones por ítem se guardan en `resumen` y en el JSON de la lista, no en columnas nuevas.
- **Design system:** `frontend/components/ui/index.tsx`, `frontend/components/ui/tokens.ts`, variables CSS en `frontend/app/globals.css`. Estilo Swiss (IBM Plex Mono, acento `#c0392b` en marca / `var(--brand)` en componentes, `border-radius: 0` en botones).
- **Dominio:** `www.baiyer.cl` → Cloudflare (DNS) → Railway.

### Routers backend clave (`backend/app/routers/`)
`identificar` (IA/Gemini, categorización), `buscar` (orquesta scrapers + MercadoLibre + Serper/SerpAPI, `/buscar/stream` SSE), `onboarding` (investigación de empresa + RUT), `contacto` (scraping de contacto + WhatsApp), `cuenta` (baja de cuenta), `listas` (cotizaciones multi-ítem, autorización), `aprobaciones` (decisión del autorizador por token), `cotizaciones`, `oc`, `proyectos`, `analisis`, `gmail`, `facturas`, `procurement`, `ledger`, `recurrencias`, `estadisticas`, `chat`, `historico`, `suppliers`, `proveedores_import`.

### Frontend — piezas nuevas de este ciclo
- `components/OnboardingChat.tsx` (chat de onboarding extraído a componente reusable) + `components/OnboardingFloating.tsx` (widget flotante sobre el dashboard) + `lib/onboarding.ts` (campos requeridos compartidos).
- `app/listas/[id]/autorizacion/page.tsx` (preparación de la solicitud: autorizador + motivo por ítem).
- `app/authorize/[token]/page.tsx` (página pública del autorizador, aceptar/rechazar por ítem con motivo).

## 3. Módulos terminados (commits recientes, más nuevo primero)

| Commit | Qué |
|---|---|
| `e51f4fd` | Contraste del campo de motivo de rechazo en dark mode (`authorize/[token]`) |
| `162cc0a` | Dashboard muestra **listas** (no cotizaciones sueltas) con su estado de autorización |
| `574dafb` | Iteración de aprobaciones observadas por ítem |
| `818f428` | Correo de autorización simplificado (nombre, total, expiración, un solo link) |
| `3d4d07d` | Autorización alineada al design system |
| `4f829d8` | "Escoger lo más barato" + selección/autorización por ítem |
| `f52a775` | RUT vía boletaofactura.com como fuente adicional (Gemini → boletaofactura → scrape sitio) |
| `1e3d09d` | Onboarding flotante: retoma sólo campos faltantes, "Omitir por ahora" con sessionStorage |
| `536d30f` | Toggle mostrar/ocultar contraseña (login + registro) |
| `2dbaf7d` | Fix crash SSR del dashboard (`EmptyState icon={FileText}` — función no serializable Server→Client) |
| `e25272f` / `d589992` / `6310740` | Blindaje SSR: try/catch en `AppShellServer`/dashboard, error boundaries globales, timeout duro 5s en fetches |
| `f6d6bd4` | Compras por ítem post-autorización: envío de OC, checklist online, OCR de boleta |
| `caed3ab` | Unificación de Cotizaciones y Listas en un solo flujo |

### Semántica de "Aprobada con observaciones" (`aprobaciones.py` + `listas.py`)
1. El autorizador rechaza uno o más ítems y escribe motivo por ítem.
2. **Aprobar todo** se deshabilita si hay rechazos por ítem → se habilita **Aprobar con observaciones**.
3. La solicitud queda `aprobado` en `approval_requests`, pero la lista se marca `aprobado_con_observaciones` (los motivos van en `aprobacion.observaciones_items` dentro del JSON de la lista).
4. El solicitante ve los ítems a corregir; **Modificar y volver a solicitar** limpia el estado de autorización.
5. No se puede comprar una lista `aprobado_con_observaciones` — las acciones de compra exigen `estado === "aprobado"`.
6. `POST /api/listas/{id}/reenviar-aprobacion` acepta listas `rechazado` y `aprobado_con_observaciones`.

### Registro → onboarding → dashboard
Flujo verificado end-to-end: registro (email+password) → correo de confirmación → `/auth/callback` (client-side, evita host interno de Railway) → `/onboarding` (o el widget flotante si se omitió) → `/dashboard`. El crash de pantalla en blanco al llegar sin cotizaciones está resuelto.

## 4. Qué se estaba implementando en este preciso momento

Dos entregas se acaban de completar y ya están en `main`, en este orden:

1. **Onboarding flotante** (`1e3d09d`): el chat aparece sobre el dashboard mientras falten `empresa`/`nombre_usuario`/`rut`/`industria` en `user_metadata`. Sólo pregunta lo que falta (no repite toda la conversación si ya hay empresa conocida), y "Omitir por ahora" lo oculta vía `sessionStorage` hasta la próxima sesión/pestaña.
2. **Búsqueda de RUT en boletaofactura.com** (`f52a775`), inmediatamente después: nueva función `_buscar_rut_boletaofactura()` en `backend/app/routers/onboarding.py` — `POST /buscar` (campo `term`) al sitio, parsea la tabla de resultados, matchea razón social normalizada (sin S.A./SpA/Ltda) contra el nombre de empresa que detectó Gemini. Prioridad de RUT: **Gemini (si confía) → boletaofactura.com → scraping del sitio de la empresa**. Probada en vivo (Falabella, Codelco, Universidad de Chile → match correcto; empresa inexistente → `None` sin excepción) y contra el endpoint completo.

En paralelo (hilo Codex, ya mergeado), el último cambio fue un ajuste de contraste del campo de motivo de rechazo en `authorize/[token]` (`e51f4fd`) para que el input no quedara ilegible en dark mode.

## 5. Errores / deuda pendiente

1. **Onboarding flotante + RUT de boletaofactura sin verificar juntos end-to-end en producción.** El RUT se probó aislado por `curl`; falta confirmar que una cuenta real, en el flujo completo (flotante o página completa), efectivamente recibe y guarda ese RUT en `user_metadata`.
2. **Ciclo completo de autorización con observaciones sin probar en producción:** `rechazar ítems → aprobar con observaciones → modificar lista → reenviar → aprobar`.
3. **"Editar ciclo de autorizaciones"** (botón en dashboard, bajo "Agente de correo") sólo enlaza a `/settings?section=autorizaciones` — la edición real del ciclo todavía no está implementada.
4. **Errores de TypeScript preexistentes** (no introducidos por estos cambios; el build de Next los ignora vía `ignoreBuildErrors`, pero no los atrapa el CI):
   - `Type 'unknown' is not assignable to type 'ReactNode'` en `app/calendario/page.tsx`, `app/cotizar/[id]/resultados/page.tsx`, `components/ReporteTemplate.tsx`.
   - Incompatibilidad de tipos en `Formatter` de Recharts en `app/estadisticas/page.tsx`, `app/proyectos/[id]/page.tsx`, `components/HistorialPrecioModal.tsx`.
   - Iteración de `Set<string>` requiere `--downlevelIteration`/target ES2015+ en `app/cotizar/[id]/resultados/page.tsx`.
5. **SMTP propio pendiente en Supabase:** el SMTP gratuito no es apto para usuarios externos en producción (deuda histórica, mencionada también en `CLAUDE.md`).
6. **Bucket electrónica/eléctrico mezclado** (`services/categoria_mapper.py`): arduino/componentes junto con materiales eléctricos — pendiente afinar keywords.
7. **Fuentes de scraping hardcodeadas** (`services/fuentes/`) — pendiente migrar a registro data-driven.
8. **Secretos expuestos en capturas durante desarrollo** (Supabase service key, Gemini, SerpAPI, Serper) — pendiente rotación.
9. **Datos huérfanos:** borrar un usuario directamente desde el dashboard de Supabase (en vez de `/api/cuenta/eliminar`) deja filas huérfanas en `resultados`/`cotizaciones`/`proyectos`/`proveedores`/`ordenes_compra`. No rompe nada, pero no hay script de limpieza.

## 6. Próximos 3 pasos exactos

1. **Probar en producción el ciclo completo integrado:** crear/usar una cuenta nueva → confirmar que el onboarding flotante pide sólo los campos faltantes y guarda el RUT de boletaofactura correctamente → crear una lista → `rechazar ítems → aprobar con observaciones → modificar → reenviar → aprobar`, confirmando que cada estado se refleja bien en el dashboard de listas.
2. **Implementar la edición real del ciclo de autorizaciones** detrás del botón "Editar ciclo de autorizaciones" en el dashboard (hoy sólo enlaza a Settings sin funcionalidad).
3. **Corregir los errores de TypeScript preexistentes**, empezando por los de `Formatter` de Recharts (`estadisticas`, `proyectos/[id]`, `HistorialPrecioModal`) por ser el patrón que más se repite.
