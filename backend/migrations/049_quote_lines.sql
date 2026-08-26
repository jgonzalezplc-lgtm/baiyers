-- 049 — Líneas de cotización: una oferta = una fila inmutable
--
-- NO APLICAR sin leer esto. Es aditiva: no borra ni modifica `resultados`.
--
-- Problema que resuelve, con el caso real que lo motivó (2026-08-26):
-- Joaquín cotizó DOS productos en un mismo correo contra UN ítem de la lista —
-- E27 estándar $19.990 y E27/E40 alta potencia $25.000. El modelo de datos tiene
-- una fila de `resultados` por (cotizacion_id, proveedor), así que la segunda
-- oferta no tenía dónde vivir: se aplicaba encima de la primera y ganaba la
-- última del texto. El borrador de OC quedó en $25.000 cuando lo elegido era
-- $19.990, y sólo lo frenó que una persona lo notara.
--
-- El commit 546c6c4 detecta el conflicto y frena, que es contención. Esto es la
-- corrección: cada oferta es una fila propia, identificable y seleccionable.
--
-- Por qué una tabla nueva y no columnas en `resultados`:
--   * `resultados` es una fila por proveedor y la usan búsqueda web, RFQ,
--     comparador, homologación y OC. Cambiar su cardinalidad rompería los cinco.
--   * Las líneas son inmutables por diseño: una oferta no se edita, se descarta
--     y se reemplaza. Eso permite auditar qué se ofreció y qué se eligió.

CREATE TABLE IF NOT EXISTS public.quote_lines (
    id                       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id                  UUID NOT NULL,
    cotizacion_id            UUID NOT NULL REFERENCES public.cotizaciones(id) ON DELETE CASCADE,

    -- Oferta de origen. Nullable a propósito: una línea puede nacer de un correo
    -- que ofrece un producto alternativo sin fila previa en `resultados`.
    resultado_id             UUID REFERENCES public.resultados(id) ON DELETE SET NULL,
    proveedor_id             UUID,
    proveedor_nombre         TEXT,
    proveedor_email          TEXT,

    -- Lo que el proveedor ofreció DE VERDAD, que puede no ser lo que se pidió.
    -- Es la columna que distingue "E27 estándar" de "E27/E40 alta potencia".
    descripcion_normalizada  TEXT,

    precio                   NUMERIC,
    moneda                   TEXT NOT NULL DEFAULT 'CLP',
    cantidad                 NUMERIC,
    unidad                   TEXT,
    plazo_entrega            TEXT,
    condiciones_pago         TEXT,
    disponibilidad           TEXT,

    origen                   TEXT NOT NULL DEFAULT 'correo',   -- correo | web | manual
    source_message_id        UUID REFERENCES public.gmail_messages(id) ON DELETE SET NULL,
    confianza                NUMERIC,

    -- propuesta   : extraída, esperando revisión humana
    -- vigente     : confirmada como oferta real
    -- seleccionada: elegida como definitiva para su ítem
    -- descartada  : el usuario la sacó de consideración
    estado                   TEXT NOT NULL DEFAULT 'propuesta',

    created_at               TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at               TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS quote_lines_cotizacion_idx ON public.quote_lines(cotizacion_id);
CREATE INDEX IF NOT EXISTS quote_lines_user_idx       ON public.quote_lines(user_id);
CREATE INDEX IF NOT EXISTS quote_lines_mensaje_idx    ON public.quote_lines(source_message_id);

-- Idempotencia de la extracción: un mismo correo re-sincronizado no puede
-- duplicar las líneas que ya creó. La clave es el mensaje + el producto ofrecido,
-- no el proveedor: dos productos del mismo correo son dos líneas legítimas.
CREATE UNIQUE INDEX IF NOT EXISTS quote_lines_origen_uniq
    ON public.quote_lines(source_message_id, cotizacion_id, descripcion_normalizada)
    WHERE source_message_id IS NOT NULL;

-- Una sola línea seleccionada por ítem. Es el invariante que hoy vive en el JSON
-- de la lista (`definitivos`) y que nada garantiza a nivel de datos.
CREATE UNIQUE INDEX IF NOT EXISTS quote_lines_seleccionada_uniq
    ON public.quote_lines(cotizacion_id)
    WHERE estado = 'seleccionada';

-- ── RLS ─────────────────────────────────────────────────────────────────────
-- Mismo criterio que el resto: el backend usa service key y bypassea RLS, así
-- que esto es la segunda capa para accesos directos vía PostgREST.
ALTER TABLE public.quote_lines ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS quote_lines_por_organizacion ON public.quote_lines;
CREATE POLICY quote_lines_por_organizacion ON public.quote_lines
    USING (user_id IN (
        SELECT m.user_id FROM public.membresias_organizacion m
        WHERE m.organizacion_id IN (
            SELECT organizacion_id FROM public.membresias_organizacion WHERE user_id = auth.uid()
        )
    ));

-- ── Verificación ────────────────────────────────────────────────────────────
--   SELECT count(*) FROM public.quote_lines;                        -- 0 esperado
--   SELECT indexname FROM pg_indexes WHERE tablename = 'quote_lines';
--
-- NO se hace backfill desde `resultados`. Una fila de `resultados` no sabe si
-- representa una oferta o varias colapsadas; inventar líneas a partir de ella
-- fabricaría un historial que nunca existió.

-- ─── Rollback lógico ────────────────────────────────────────────────────────
-- DROP TABLE IF EXISTS public.quote_lines;
