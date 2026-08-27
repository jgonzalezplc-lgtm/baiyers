-- 050 — El emisor queda congelado en la OC
--
-- El membrete del PDF salía de `obtener_perfil_organizacion()`, leído en vivo en
-- cada generación, y `ordenes_compra` no guardaba nada del emisor. Si la empresa
-- se renombra, regenerar el PDF de una OC vieja la muestra con el nombre de hoy:
-- el documento deja de decir quién la emitió cuando la emitió.
--
-- Mismo criterio que `direccion_despacho` (048) y que el número de OC: un
-- documento comercial es un registro histórico.
--
-- IDEMPOTENTE — se puede correr varias veces.

ALTER TABLE public.ordenes_compra
    ADD COLUMN IF NOT EXISTS emisor_nombre    TEXT,
    ADD COLUMN IF NOT EXISTS emisor_rut       TEXT,
    ADD COLUMN IF NOT EXISTS emisor_direccion TEXT;

COMMENT ON COLUMN public.ordenes_compra.emisor_nombre IS
    'Nombre de la empresa AL MOMENTO DE EMITIR. No se actualiza si la '
    'organización se renombra: el documento ya emitido no cambia.';

-- Sin backfill: las OC previas no registran quién era el emisor entonces, y
-- copiarles el nombre actual afirmaría algo que no consta. El generador de PDF
-- cae al perfil vigente cuando la columna está vacía, que es el comportamiento
-- que ya tenían.

-- ─── Rollback lógico ────────────────────────────────────────────────────────
-- ALTER TABLE public.ordenes_compra
--     DROP COLUMN IF EXISTS emisor_nombre,
--     DROP COLUMN IF EXISTS emisor_rut,
--     DROP COLUMN IF EXISTS emisor_direccion;
