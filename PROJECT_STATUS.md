# PROJECT_STATUS.md — Baiyer (Cotizador Inteligente B2B)

> Handoff para continuar en Codex. Escrito por Claude Code al quedarse sin tokens
> a mitad de la Fase 3 de "Supplier Capability Intelligence". Fecha: 30-jul-2026.

## 0. Antes de tocar nada

1. Lee `CLAUDE.md` completo — tiene todo el contexto arquitectónico y los gotchas.
2. Lee `PROMPT_CLAUDE_CODE_SUPPLIER_INTELLIGENCE.md` (raíz del repo) — es el spec
   completo de las 7 fases de Supplier Capability Intelligence, dado por el usuario.
3. **`frontend/next-env.d.ts` está modificado — es autogenerado por Next.js en dev,
   consérvalo tal cual, no lo commitees, no lo reviertas.**
4. **Hay trabajo de OTRA sesión en paralelo en el mismo repo** — no tocar:
   - `backend/app/routers/identificar.py` (modificado, no por mí)
   - `frontend/app/cotizar/page.tsx` (modificado, no por mí)
   - `CUBICACION.md` (nuevo, no por mí)
   Es un motor de "cubicación" (cálculo de cantidades de materiales para proyectos de
   construcción) — no tiene relación con Supplier Capability Intelligence. No lo toques,
   no lo mezcles, no lo comitees como si fuera tuyo. Pregúntale al usuario si hace falta
   coordinar con esa sesión.
5. Antes de asumir que una tabla/columna existe, verifica contra la DB real:
   ```python
   from app.services.supabase import get_supabase
   sb = get_supabase()
   sb.table("nombre_tabla").select("*").limit(1).execute()
   ```
   Varias tablas referenciadas en código **no existen en producción** pese a estar en
   migraciones numeradas — ver sección 4.

## 1. Qué se hizo esta sesión (todo en `main`, deployado, confirmado)

Sesión larga, en orden:
1. Campanita de notificaciones (aprobación de cotización + respuesta de proveedor por
   correo). Migración 022 aplicada.
2. Correo de autorización por Gmail en vez de mailto, con un solo link (la página
   `/authorize/{token}` ya deja elegir aprobar/rechazar/observaciones desde ahí).
3. Fix de selección de ofertas duplicadas en el comparador: elegir una oferta con `url`
   vacía (bug real del scraper Vitel/Construmart sin `url_key`) marcaba varias como
   seleccionadas. Se agregó `_uid` propio por resultado en vez de usar `url` como llave,
   más el fix de raíz (usar `sku` como respaldo en el scraper).
4. Limpieza de markdown en el correo de cotización generado por Gemini.
5. `OCModal.tsx` migrado al design system actual + precarga de plazo/email del
   proveedor + fix del bug "010" en el campo Cantidad.
6. Seguimiento de OC por respuesta de correo (acuse de recibo / despacho), alternativa
   al link de confirmación manual. Migración 023 aplicada y confirmada.
7. **Supplier Capability Intelligence — Fase 1 (fundaciones): COMPLETA, commiteada,
   pusheada, migración 024 aplicada y confirmada.**
8. **Fase 2 (indicadores de estado arriba del dashboard): COMPLETA, commiteada,
   pusheada.** La parte de "consistencia de tema" quedó **sin resolver** — investigué
   a fondo (ver sección 5) y no pude reproducir el bug reportado.
9. **Fase 3 (gestión de proveedores): A MEDIO CAMINO, sin commitear — ver sección 3.**

## 2. Fase 1 y 2 — qué hay que saber

- Migración 024 (`backend/migrations/024_supplier_capability_intelligence.sql`)
  aplicada: `procurement_profiles`, `procurement_profile_categories`,
  `search_sessions`, `search_feedback`, `supplier_capability_events`,
  `supplier_capabilities`. Todas nuevas, RLS, FKs a tablas reales.
- `backend/app/services/supplier_capability_intelligence.py` — `PESOS` por tipo de
  evento, `registrar_evento()` (idempotente por `clave_idempotencia`),
  `recalcular_capacidad()` (SIEMPRE recalcula desde el log completo de eventos, nunca
  incrementa in-place), `rankear_proveedores()`, y ahora (sin commitear, ver Fase 3)
  `listar_capacidades()`/`rechazar_capacidad()`.
- `backend/app/services/procurement_profile.py` — perfil de compra por usuario,
  generado al completar el onboarding (`OnboardingChat.tsx` llama a
  `POST /api/procurement-profile/generar` sin bloquear si falla).
- `frontend/app/cotizar/[id]/resultados/page.tsx` crea una `search_session` no
  bloqueante por búsqueda y registra `search_feedback` en el flujo YA EXISTENTE
  "¿No encontraste lo que buscabas?" → "Rebuscar con contexto" (no inventé UI nueva).
- **Nada de esto se probó contra la DB real con datos reales** — solo con un fake
  in-memory de supabase-py en Python. Sería bueno, cuando haya tiempo, completar un
  onboarding real y verificar que aparece la fila en `procurement_profiles`.
- **Bug de tema pendiente** (Fase 2): al pasar de dashboard a "Nueva cotización" el
  fondo cambiaría a claro, según el spec original. Investigué el theme provider
  (`layout.tsx`, `useIsDark`/`ThemeToggle` en `components/ui/index.tsx`), y TODOS los
  archivos que `CLAUDE.md` marcaba como "sin migrar" (`app/cotizar/page.tsx`,
  `FormularioCotizar.tsx`, `ResultadoIdentificacionMulti.tsx`, `CardProveedor.tsx`,
  `SkeletonResultados.tsx`) — ninguno tiene colores hardcodeados a claro. Verifiqué en
  vivo (browser real) que los alias de variables viejas (`--bg-surface`,
  `--text-primary`, etc.) SÍ reaccionan correctamente a `data-theme="dark"` — el
  mecanismo de CSS funciona. No pude reproducir el bug (no tengo credenciales de login
  para probar el flujo real). **Antes de "arreglar" esto, pídele al usuario que
  reproduzca y describa/capture exactamente qué ve** — no hay pistas de código.

## 3. Fase 3 (gestión de proveedores) — EN PROGRESO, sin commitear

### Lo que ya está escrito pero sin verificar ni commitear

- `backend/migrations/025_proveedores_ficha.sql` (**creada, NO aplicada**):
  - `ALTER TABLE proveedores ADD COLUMN` → `sitio_web`, `telefono`, `notas_privadas`,
    `preferido` (boolean default false). Aditivo, sin riesgo.
  - Amplía el CHECK de `supplier_capability_events.tipo_evento` agregando
    `'manual_category_assigned'` (peso 1.0, ya agregado a `PESOS` en el service).
- `backend/app/services/supplier_capability_intelligence.py` (modificado):
  - Nuevo peso `PESOS["manual_category_assigned"] = 1.00`.
  - Nueva función `listar_capacidades(user_id, proveedor_id)`.
  - Nueva función `rechazar_capacidad(user_id, proveedor_id, categoria, concepto="")`
    — anula una capacidad directamente (corrección manual explícita, no espera
    eventos negativos acumulados).
- `backend/app/routers/suppliers.py` (modificado): `GET /{id}/historial` ahora
  envuelve la consulta a `supplier_ratings` en try/except (esa tabla **no existe en
  producción**, tumbaba el endpoint entero — bug preexistente real, ver sección 4).
  También agrega `capacidades` a la respuesta.
- `backend/app/routers/proveedores.py` (**archivo nuevo, completo**):
  - `POST /api/proveedores/investigar` — investiga un PROVEEDOR (no la empresa del
    usuario — no confundir con `onboarding.py`) reutilizando los helpers de
    `onboarding.py` (`_dominio_de`, `_buscar_rut_boletaofactura`,
    `_scrape_rut_direccion`, `_logos_de`, `_TLD_PAIS`, `_GENERICOS`) con un prompt
    propio. Solo investiga, no guarda nada.
  - `POST /api/proveedores` — alta manual, reutiliza
    `resolver_o_crear_proveedor`/`resolver_o_crear_contacto` (mismo dedupe que Excel
    import y agente de Gmail — no crea directorio paralelo).
  - `GET /api/proveedores/{id}` — ficha completa (proveedor + contactos +
    capacidades + OCs).
  - `PATCH /api/proveedores/{id}` — editar campos sueltos.
  - `POST /api/proveedores/{id}/categorias` — confirma categorías (evento
    `manual_category_assigned` por cada una).
  - `DELETE /api/proveedores/{id}/categorias/{categoria}` — quita una capacidad.
  - Registrado en `backend/app/main.py` (import + `include_router`, ANTES de
    `proveedores_import.router` en el orden de rutas — verificar que no colisione
    `/plantilla`/`/importar` de `proveedores_import.py` con `/{proveedor_id}` de este
    archivo nuevo; los until ahora confirmé que el import de `app.main` no falla, pero
    **no alcancé a confirmar el orden real de matching de rutas con un request real**
    — probarlo con `curl` antes de dar por bueno).

### Lo que falta (no empezado)

1. **Verificar que `backend/app/main.py` importa sin error** con todos estos cambios
   juntos (la última verificación fue solo del import, no de un request real).
2. **Aplicar la migración 025** (solo cuando el usuario autorice — copiar con
   `cat backend/migrations/025_proveedores_ficha.sql | pbcopy` y pedirle que la pegue
   en el SQL Editor de Supabase, mismo flujo que 022/023/024).
3. **Probar los endpoints nuevos contra la DB real** una vez aplicada la 025 (crear un
   proveedor manual, investigar uno, confirmar categorías, ver la ficha).
4. **Frontend — nada hecho todavía:**
   - `frontend/app/proveedores/page.tsx`: agregar botón "Agregar proveedor
     manualmente" que abra un modal (usar el design system actual — `Card`, `Input`,
     `BtnPrimary`/`BtnSecondary` de `@/components/ui`, mismo patrón que se usó hoy
     para `OCModal.tsx` — NO el estilo Swiss viejo que tiene esta página hoy) con:
     nombre, RUT, sitio web, país, email, contacto, teléfono, selección múltiple de
     categorías, notas privadas, preferido/bloqueado. Incluir un botón "Investigar y
     recomendar categorías" que llame a `POST /api/proveedores/investigar` y muestre
     las categorías sugeridas para que el usuario las confirme/descarte ANTES de
     guardar (igual que el onboarding: investigar → revisar → confirmar).
   - `frontend/app/proveedores/[id]/page.tsx`: agregar sección "Categorías" mostrando
     `capacidades` (confianza, estado, origen) con botón para quitar una, y campos
     editables de sitio_web/telefono/notas_privadas/preferido (llamando al `PATCH`
     nuevo).
5. **Bug bonus encontrado, no arreglado:** `proveedores_import.py` (importación
   Excel/CSV) extrae `categoria`, `telefono` y `notas` con Gemini pero **nunca los
   guarda** — solo persiste nombre/email/rut. Sería una mejora natural aprovechar las
   columnas nuevas de la 025 para guardar `telefono`/`notas_privadas`, y generar un
   evento `manual_category_assigned` (o uno nuevo tipo `import_category_assigned` con
   menor peso, a definir) por la `categoria` detectada. No lo hice por falta de
   tiempo/tokens — está documentado acá para retomar.
6. **Type-check frontend** (`cd frontend && npx tsc --noEmit`) — no se corrió después
   de estos cambios de backend (no debería afectar frontend hasta que se toque la UI).

## 4. Gotchas críticos (ya estaban en CLAUDE.md, repetidos acá por importancia)

**Tablas referenciadas en código que NO EXISTEN en producción** (confirmado con
`sb.table(x).select('*').limit(1)` contra la DB real):
- `supplier_categories`, `procurement_ledger` (de `014_smart_procurement.sql`,
  migración numerada pero aplicada solo a medias).
- `quote_items`, `quote_suppliers`, `purchase_events` (de `013_procurement_flow.sql`,
  usadas por `procurement.py` — el botón "+ Lista" en `/cotizar/[id]/resultados`
  llama a `POST /api/procurement/eventos` y hoy tira 500).
- `supplier_ratings`, `rating_pendiente` (usadas por `supplier_intelligence.py` y
  `POST /api/suppliers/rating` — el primero ahora está protegido con try/except en
  `/historial`, pero `/rating` sigue roto).

**Ningún número de migración garantiza que esté realmente en prod.** Verificar
siempre contra la DB real antes de asumir.

## 5. Migraciones — estado real confirmado

Aplicadas y confirmadas contra la DB real: **hasta la 024** (019–021 agente Gmail,
022 notificaciones, 023 seguimiento OC por correo, 024 Supplier Capability
Intelligence Fase 1). **025 creada pero NO aplicada.**

## 6. Comandos útiles

```bash
cd /Users/macbook/Desktop/Cotizador/backend
.venv/bin/python -c "import app.main"                    # verificar que importa
cd ../frontend && npx tsc --noEmit                        # type-check

# Copiar una migración al portapapeles para pegarla en Supabase SQL Editor
cat backend/migrations/025_proveedores_ficha.sql | pbcopy

# Verificar si una tabla/columna existe en la DB real (NO confiar en los .sql)
cd backend && .venv/bin/python -c "
from app.services.supabase import get_supabase
sb = get_supabase()
sb.table('nombre_tabla').select('columna').limit(1).execute()
"
```

## 7. Reglas de trabajo que el usuario ya estableció esta sesión

- No commitear/pushear/aplicar migraciones sin autorización explícita.
- Las migraciones de Supabase se aplican copiando el `.sql` al portapapeles
  (`pbcopy`) y pidiéndole al usuario que lo pegue en el SQL Editor — Claude Code no
  tiene `DATABASE_URL` ni credenciales de conexión directa.
- Conservar `frontend/next-env.d.ts` tal cual (no commitear ese cambio).
- No tocar el trabajo paralelo de "cubicación" (sección 0.4).
- Usar `CLAUDE.md` como documento de continuidad principal; este archivo
  (`PROJECT_STATUS.md`) es el handoff puntual para el cambio de herramienta.
- Verificar backend (`import app.main`) y frontend (`tsc --noEmit`) después de cada
  cambio, antes de pedir autorización para commitear.
