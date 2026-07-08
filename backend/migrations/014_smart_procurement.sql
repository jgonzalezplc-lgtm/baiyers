-- Etapa 14: Smart Procurement Platform (v2)
-- Tablas: supplier_categories (Fase 1/2), procurement_ledger (Fase 4), approval_workflows (Fase 6)

-- ============================================================
-- supplier_categories — categorización de proveedores custom
-- ============================================================
CREATE TABLE IF NOT EXISTS public.supplier_categories (
    id                  UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id             UUID REFERENCES auth.users(id) ON DELETE CASCADE NOT NULL,
    supplier_id         UUID,                          -- referencia flexible (proveedores o suppliers)
    supplier_nombre     TEXT,
    categoria_principal TEXT NOT NULL,                 -- electronica|construccion|insumos_medicos|industrial|tuberias_valvulas|...
    subcategorias       TEXT[] DEFAULT '{}',
    keywords_asociadas  TEXT[] DEFAULT '{}',
    created_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS supplier_categories_user_idx ON public.supplier_categories(user_id, categoria_principal);

ALTER TABLE public.supplier_categories ENABLE ROW LEVEL SECURITY;
CREATE POLICY "supplier_categories_own" ON public.supplier_categories FOR ALL USING (auth.uid() = user_id);

-- ============================================================
-- procurement_ledger — fuente de verdad del ciclo de compra
-- ============================================================
CREATE TABLE IF NOT EXISTS public.procurement_ledger (
    id                      UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id                 UUID REFERENCES auth.users(id) ON DELETE CASCADE NOT NULL,
    item_name               TEXT NOT NULL,
    categoria               TEXT,
    supplier_id             UUID,
    proveedor_nombre        TEXT NOT NULL,
    cantidad_solicitada     INT DEFAULT 1,
    precio_unitario         NUMERIC,
    precio_total            NUMERIC,
    moneda                  TEXT DEFAULT 'CLP',
    fecha_cotizacion        TIMESTAMPTZ,
    fecha_oc                TIMESTAMPTZ,
    fecha_entrega_esperada  DATE,
    fecha_entrega_real      DATE,
    estado                  TEXT NOT NULL DEFAULT 'cotizacion_pendiente'
                            CHECK (estado IN ('cotizacion_pendiente','oc_enviada','en_transito','entregado','facturado')),
    facturas_asociadas      TEXT[] DEFAULT '{}',
    numeros_oc              TEXT[] DEFAULT '{}',
    observaciones           TEXT,
    -- Referencias al origen (flexibles, sin FK duras para no acoplar)
    cotizacion_id           UUID,
    quote_supplier_id       UUID,
    purchase_event_id       UUID,
    created_at              TIMESTAMPTZ DEFAULT NOW(),
    updated_at              TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ledger_user_item_idx ON public.procurement_ledger(user_id, item_name);
CREATE INDEX IF NOT EXISTS ledger_user_proveedor_idx ON public.procurement_ledger(user_id, proveedor_nombre);
CREATE INDEX IF NOT EXISTS ledger_user_estado_idx ON public.procurement_ledger(user_id, estado, created_at DESC);

ALTER TABLE public.procurement_ledger ENABLE ROW LEVEL SECURITY;
CREATE POLICY "procurement_ledger_own" ON public.procurement_ledger FOR ALL USING (auth.uid() = user_id);

-- ============================================================
-- approval_workflows — cadenas de aprobación por empresa
-- ============================================================
CREATE TABLE IF NOT EXISTS public.approval_workflows (
    id             UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id        UUID REFERENCES auth.users(id) ON DELETE CASCADE NOT NULL,
    nombre         TEXT NOT NULL DEFAULT 'Flujo por defecto',
    pasos          JSONB NOT NULL DEFAULT '[]',   -- [{orden, rol, nombre, email}]
    monto_minimo   NUMERIC DEFAULT 0,             -- aplica si monto OC >= este valor
    activo         BOOLEAN DEFAULT TRUE,
    created_at     TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE public.approval_workflows ENABLE ROW LEVEL SECURITY;
CREATE POLICY "approval_workflows_own" ON public.approval_workflows FOR ALL USING (auth.uid() = user_id);

-- approval_requests — solicitudes con magic link
CREATE TABLE IF NOT EXISTS public.approval_requests (
    id             UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id        UUID REFERENCES auth.users(id) ON DELETE CASCADE NOT NULL,
    workflow_id    UUID REFERENCES public.approval_workflows(id) ON DELETE SET NULL,
    referencia     TEXT,                          -- "quote_supplier:<id>" | "oc:<id>"
    resumen        JSONB DEFAULT '{}',            -- snapshot de la comparativa/OC
    token          TEXT NOT NULL UNIQUE,          -- para magic link /authorize/{token}
    aprobador_email TEXT,
    estado         TEXT NOT NULL DEFAULT 'pendiente'
                   CHECK (estado IN ('pendiente','aprobado','rechazado','expirado')),
    decidido_at    TIMESTAMPTZ,
    expira_at      TIMESTAMPTZ,
    created_at     TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS approval_requests_token_idx ON public.approval_requests(token);
CREATE INDEX IF NOT EXISTS approval_requests_user_idx ON public.approval_requests(user_id, estado);

ALTER TABLE public.approval_requests ENABLE ROW LEVEL SECURITY;
CREATE POLICY "approval_requests_own" ON public.approval_requests FOR ALL USING (auth.uid() = user_id);

-- ============================================================
-- Fase 7: recurrencias smart — modo explícito + log de auditoría
-- ============================================================
ALTER TABLE public.recurrencias ADD COLUMN IF NOT EXISTS modo TEXT DEFAULT 're_cotizar'
    CHECK (modo IN ('re_cotizar','oc_directa','a_aprobacion'));

CREATE TABLE IF NOT EXISTS public.recurrencia_logs (
    id              UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    recurrencia_id  UUID REFERENCES public.recurrencias(id) ON DELETE CASCADE,
    user_id         UUID REFERENCES auth.users(id) ON DELETE CASCADE,
    modo            TEXT,
    resultado       TEXT,
    exitoso         BOOLEAN DEFAULT TRUE,
    ejecutado_at    TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS recurrencia_logs_rec_idx ON public.recurrencia_logs(recurrencia_id, ejecutado_at DESC);

ALTER TABLE public.recurrencia_logs ENABLE ROW LEVEL SECURITY;
CREATE POLICY "recurrencia_logs_own" ON public.recurrencia_logs FOR ALL USING (auth.uid() = user_id);
