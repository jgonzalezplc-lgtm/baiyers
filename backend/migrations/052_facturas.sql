-- 052 — Facturas: tabla canónica para recepción, conciliación y pago
--
-- El módulo de facturas existe en rutas, servicios y MCP desde antes de que el
-- repositorio empezara a versionar todas las migraciones. Producción no tenía
-- la tabla, por lo que cualquier uso del módulo (y el checkpoint de
-- aislamiento del empleado digital) fallaba antes de poder aplicar sus filtros
-- de organización.
--
-- Esta migración es sólo aditiva. El backend sigue siendo responsable de
-- filtrar siempre por los miembros de la organización: usa service key y no
-- puede depender de RLS para ese límite.

CREATE TABLE IF NOT EXISTS public.facturas (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    proveedor_id        UUID REFERENCES public.proveedores(id) ON DELETE SET NULL,
    proveedor_nombre    TEXT NOT NULL,
    numero_factura      TEXT,
    fecha_factura       DATE,
    fecha_vencimiento   DATE,
    monto_neto          NUMERIC,
    iva                 NUMERIC,
    monto_total         NUMERIC NOT NULL DEFAULT 0 CHECK (monto_total >= 0),
    moneda              TEXT NOT NULL DEFAULT 'CLP',
    estado              TEXT NOT NULL DEFAULT 'pendiente'
                        CHECK (estado IN ('pendiente', 'vencida', 'pagada')),
    oc_id               UUID REFERENCES public.ordenes_compra(id) ON DELETE SET NULL,
    fecha_pago          DATE,
    email_message_id    TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS facturas_user_idx
    ON public.facturas(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS facturas_estado_idx
    ON public.facturas(user_id, estado);
CREATE INDEX IF NOT EXISTS facturas_vencimiento_idx
    ON public.facturas(user_id, fecha_vencimiento)
    WHERE estado <> 'pagada';
CREATE INDEX IF NOT EXISTS facturas_oc_idx
    ON public.facturas(oc_id) WHERE oc_id IS NOT NULL;

-- Reprocesar el mismo mensaje de Gmail no debe duplicar una factura.
CREATE UNIQUE INDEX IF NOT EXISTS facturas_email_message_uniq
    ON public.facturas(email_message_id)
    WHERE email_message_id IS NOT NULL;

ALTER TABLE public.facturas ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS facturas_por_organizacion ON public.facturas;
CREATE POLICY facturas_por_organizacion ON public.facturas
    USING (user_id IN (
        SELECT m.user_id
        FROM public.membresias_organizacion m
        WHERE m.organizacion_id IN (
            SELECT organizacion_id
            FROM public.membresias_organizacion
            WHERE user_id = auth.uid()
        )
    ))
    WITH CHECK (user_id IN (
        SELECT m.user_id
        FROM public.membresias_organizacion m
        WHERE m.organizacion_id IN (
            SELECT organizacion_id
            FROM public.membresias_organizacion
            WHERE user_id = auth.uid()
        )
    ));

COMMENT ON TABLE public.facturas IS
    'Facturas recibidas manualmente, por Gmail o por importación MCP.';

-- Verificación posterior a aplicar:
-- SELECT column_name, data_type
-- FROM information_schema.columns
-- WHERE table_schema = 'public' AND table_name = 'facturas'
-- ORDER BY ordinal_position;

-- Rollback lógico (sólo si no se han ingresado facturas reales):
-- DROP TABLE IF EXISTS public.facturas;
