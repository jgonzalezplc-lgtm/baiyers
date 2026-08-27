-- 051: Las OCs pueden comprar fracciones (kg, metros, litros, etc.).
-- `cantidad` se creó originalmente como INTEGER, por lo que Postgres rechazaba
-- incluso el valor serializado "5.0" con 22P02.

ALTER TABLE public.ordenes_compra
    ALTER COLUMN cantidad TYPE NUMERIC(12,3)
    USING cantidad::NUMERIC(12,3),
    ALTER COLUMN cantidad SET DEFAULT 1;

-- La unidad es parte de la línea de compra, no un dato sólo de la lista.
ALTER TABLE public.ordenes_compra
    ADD COLUMN IF NOT EXISTS unidad TEXT NOT NULL DEFAULT 'und';

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'ordenes_compra_cantidad_positiva'
          AND conrelid = 'public.ordenes_compra'::regclass
    ) THEN
        ALTER TABLE public.ordenes_compra
            ADD CONSTRAINT ordenes_compra_cantidad_positiva
            CHECK (cantidad IS NULL OR cantidad > 0);
    END IF;
END $$;

COMMENT ON COLUMN public.ordenes_compra.cantidad IS
    'Cantidad solicitada, con hasta tres decimales.';
COMMENT ON COLUMN public.ordenes_compra.unidad IS
    'Unidad de medida de la cantidad (und, kg, m, L, etc.).';
