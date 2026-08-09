-- 035: Dirección de la organización — para personalizar Órdenes de Compra e
-- informes con la dirección real de la empresa, igual que ya se hace con
-- nombre/RUT/logo (migración 034). `investigar-empresa` ya la scrapea
-- (`_scrape_rut_direccion` en onboarding.py); solo faltaba dónde guardarla.
--
-- IDEMPOTENTE — se puede correr varias veces sin efectos duplicados.

ALTER TABLE public.organizaciones
    ADD COLUMN IF NOT EXISTS direccion TEXT;

-- ─── Rollback lógico ────────────────────────────────────────────────────────
-- ALTER TABLE public.organizaciones DROP COLUMN IF EXISTS direccion;
