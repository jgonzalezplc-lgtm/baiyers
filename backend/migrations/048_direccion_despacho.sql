-- 048 — Dirección de despacho: un dato propio, nunca inferido
--
-- Caso real (2026-08-26): un proveedor preguntó "¿a qué dirección?" y Baiyer no
-- tenía ninguna dirección de entrega que ofrecer. El único campo disponible era
-- `organizaciones.direccion`, que estuvo a punto de enviarse: decía
-- "Av. Pedro Dreyer 4627, Monte Grande, Buenos Aires, Argentina" para una compra
-- a un proveedor chileno.
--
-- Ese campo NO es una dirección de entrega y no debe usarse como tal:
--   * lo scrapea `_scrape_rut_direccion()` del sitio web durante el onboarding,
--     así que es una suposición sin verificar, no un dato confirmado;
--   * aunque fuera correcto, la dirección administrativa/tributaria de una
--     empresa rara vez es donde quiere recibir la mercadería (bodega, obra,
--     sucursal).
--
-- Por eso se agrega un campo separado, en vez de "mejorar" el existente.

-- ── Dirección de entrega de la organización ─────────────────────────────────
ALTER TABLE public.organizaciones
    ADD COLUMN IF NOT EXISTS direccion_despacho     TEXT,
    ADD COLUMN IF NOT EXISTS despacho_contacto      TEXT,  -- quién recibe
    ADD COLUMN IF NOT EXISTS despacho_telefono      TEXT,
    ADD COLUMN IF NOT EXISTS despacho_notas         TEXT;  -- horarios, portería, etc.

COMMENT ON COLUMN public.organizaciones.direccion_despacho IS
    'Dónde recibe mercadería la empresa. Distinta de `direccion` (administrativa, '
    'scrapeada del sitio y sin verificar). Nunca derivar una de la otra.';

-- ── Copia en la OC ──────────────────────────────────────────────────────────
-- La dirección se congela en la orden al emitirla: si la empresa después cambia
-- de bodega, la OC ya enviada al proveedor debe seguir diciendo a dónde se
-- despachaba cuando se emitió. Mismo criterio que el número de OC.
ALTER TABLE public.ordenes_compra
    ADD COLUMN IF NOT EXISTS direccion_despacho TEXT;

-- ── Verificación ────────────────────────────────────────────────────────────
--   SELECT nombre, direccion, direccion_despacho FROM public.organizaciones;
--
-- Es esperable que `direccion_despacho` esté en NULL para todas: es un dato que
-- el usuario tiene que confirmar. NO se hace backfill desde `direccion` — copiar
-- una dirección sin verificar a un campo que el sistema tratará como verificada
-- es exactamente el error que esta migración existe para impedir.

-- ─── Rollback lógico ────────────────────────────────────────────────────────
-- ALTER TABLE public.organizaciones
--     DROP COLUMN IF EXISTS direccion_despacho, DROP COLUMN IF EXISTS despacho_contacto,
--     DROP COLUMN IF EXISTS despacho_telefono,  DROP COLUMN IF EXISTS despacho_notas;
-- ALTER TABLE public.ordenes_compra DROP COLUMN IF EXISTS direccion_despacho;
