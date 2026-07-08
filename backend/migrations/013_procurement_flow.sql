-- Etapa 13: Flujo de Procurement (funnel secuencial estilo Kayak/Google Flights)
-- Tablas: suppliers, purchase_events, quote_items, quote_suppliers, procurement_timeline
-- Diseño aditivo: no modifica tablas existentes salvo referencias FK opcionales.

-- ============================================================
-- suppliers — Base de proveedores (se puebla al emitir OC)
-- ============================================================
CREATE TABLE IF NOT EXISTS public.suppliers (
    id                          UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id                     UUID REFERENCES auth.users(id) ON DELETE CASCADE NOT NULL,
    nombre                      TEXT NOT NULL,
    email                       TEXT,
    telefono                    TEXT,
    sitio_web                   TEXT,
    fuente                      TEXT,                 -- 'mercadolibre', 'mouser', 'manual', etc.
    proveedor_id_externo        TEXT,                 -- ID en la fuente original (ej. seller.id de ML)
    pais                        TEXT DEFAULT 'CL',
    categoria                   TEXT,
    -- Historial agregado (se actualiza al emitir OC / registrar despacho)
    total_ocs                   INT DEFAULT 0,
    monto_total_clp             BIGINT DEFAULT 0,
    ultima_oc_at                TIMESTAMPTZ,
    plazo_entrega_promedio_dias INT,
    -- Compra recurrente
    recurrente                  BOOLEAN DEFAULT FALSE,
    frecuencia                  TEXT CHECK (frecuencia IN ('semanal','mensual','trimestral')),
    proxima_compra_at           DATE,
    created_at                  TIMESTAMPTZ DEFAULT NOW(),
    updated_at                  TIMESTAMPTZ DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS suppliers_user_email_idx
    ON public.suppliers(user_id, email) WHERE email IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS suppliers_user_fuente_ext_idx
    ON public.suppliers(user_id, fuente, proveedor_id_externo) WHERE proveedor_id_externo IS NOT NULL;
CREATE INDEX IF NOT EXISTS suppliers_user_idx ON public.suppliers(user_id);

ALTER TABLE public.suppliers ENABLE ROW LEVEL SECURITY;
CREATE POLICY "suppliers_own" ON public.suppliers FOR ALL USING (auth.uid() = user_id);

-- ============================================================
-- purchase_events — Evento de compra (agrupa ítems)
-- ============================================================
CREATE TABLE IF NOT EXISTS public.purchase_events (
    id             UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id        UUID REFERENCES auth.users(id) ON DELETE CASCADE NOT NULL,
    nombre         TEXT NOT NULL,
    descripcion    TEXT,
    estado         TEXT NOT NULL DEFAULT 'borrador'
                   CHECK (estado IN ('borrador','en_cotizacion','oc_emitida','cerrado','cancelado')),
    cotizacion_id  UUID REFERENCES public.cotizaciones(id) ON DELETE SET NULL,
    created_at     TIMESTAMPTZ DEFAULT NOW(),
    updated_at     TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS purchase_events_user_idx ON public.purchase_events(user_id, created_at DESC);

ALTER TABLE public.purchase_events ENABLE ROW LEVEL SECURITY;
CREATE POLICY "purchase_events_own" ON public.purchase_events FOR ALL USING (auth.uid() = user_id);

-- ============================================================
-- quote_items — Ítem/producto dentro del evento
-- ============================================================
CREATE TABLE IF NOT EXISTS public.quote_items (
    id                 UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    purchase_event_id  UUID REFERENCES public.purchase_events(id) ON DELETE CASCADE NOT NULL,
    nombre             TEXT NOT NULL,
    descripcion        TEXT,
    numero_parte       TEXT,
    marca              TEXT,
    cantidad           INT NOT NULL DEFAULT 1,
    unidad             TEXT DEFAULT 'und',
    resultado_id       UUID REFERENCES public.resultados(id) ON DELETE SET NULL,
    orden              INT DEFAULT 0,
    created_at         TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS quote_items_event_idx ON public.quote_items(purchase_event_id, orden);

ALTER TABLE public.quote_items ENABLE ROW LEVEL SECURITY;
CREATE POLICY "quote_items_own" ON public.quote_items FOR ALL USING (
    auth.uid() = (SELECT user_id FROM public.purchase_events WHERE id = purchase_event_id)
);

-- ============================================================
-- quote_suppliers — Proveedor por ítem (fila central del funnel)
-- ============================================================
CREATE TABLE IF NOT EXISTS public.quote_suppliers (
    id                     UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    quote_item_id          UUID REFERENCES public.quote_items(id) ON DELETE CASCADE NOT NULL,
    supplier_id            UUID REFERENCES public.suppliers(id) ON DELETE SET NULL,
    proveedor_nombre       TEXT NOT NULL,
    proveedor_email        TEXT,
    fuente                 TEXT,
    url_referencia         TEXT,
    -- Precios
    precio_referencial     NUMERIC,
    moneda_referencial     TEXT DEFAULT 'CLP',
    precio_cotizado        NUMERIC,
    moneda_cotizada        TEXT DEFAULT 'CLP',
    -- Logística
    plazo_entrega_estimado TEXT,
    plazo_entrega_dias     INT,
    condiciones            TEXT,
    -- Estado del flujo
    estado                 TEXT NOT NULL DEFAULT 'pendiente_cotizar'
                           CHECK (estado IN (
                               'pendiente_cotizar','correo_enviado','respuesta_recibida',
                               'seleccionado','oc_emitida','descartado'
                           )),
    -- Badge de ranking (sugerido por sistema, editable)
    badge                  TEXT CHECK (badge IN ('mas_conveniente','mas_economico','disponibilidad_inmediata')),
    -- OC
    oc_numero              TEXT,
    oc_emitida_at          TIMESTAMPTZ,
    despacho_recibido_at   TIMESTAMPTZ,
    -- Correo
    correo_enviado_at      TIMESTAMPTZ,
    correo_thread_id       TEXT,
    created_at             TIMESTAMPTZ DEFAULT NOW(),
    updated_at             TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS quote_suppliers_item_idx ON public.quote_suppliers(quote_item_id);
CREATE INDEX IF NOT EXISTS quote_suppliers_estado_idx ON public.quote_suppliers(estado);

ALTER TABLE public.quote_suppliers ENABLE ROW LEVEL SECURITY;
CREATE POLICY "quote_suppliers_own" ON public.quote_suppliers FOR ALL USING (
    auth.uid() = (
        SELECT pe.user_id
        FROM public.quote_items qi
        JOIN public.purchase_events pe ON pe.id = qi.purchase_event_id
        WHERE qi.id = quote_item_id
    )
);

-- ============================================================
-- procurement_timeline — Log append-only de eventos
-- ============================================================
CREATE TABLE IF NOT EXISTS public.procurement_timeline (
    id                 UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    purchase_event_id  UUID REFERENCES public.purchase_events(id) ON DELETE CASCADE NOT NULL,
    quote_supplier_id  UUID REFERENCES public.quote_suppliers(id) ON DELETE SET NULL,
    quote_item_id      UUID REFERENCES public.quote_items(id) ON DELETE SET NULL,
    tipo               TEXT NOT NULL CHECK (tipo IN (
                           'evento_creado','proveedor_agregado','cotizacion_enviada',
                           'respuesta_recibida','proveedor_seleccionado','oc_emitida',
                           'despacho_recibido','nota'
                       )),
    descripcion        TEXT,
    metadata           JSONB DEFAULT '{}',
    created_at         TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS procurement_timeline_event_idx
    ON public.procurement_timeline(purchase_event_id, created_at DESC);

ALTER TABLE public.procurement_timeline ENABLE ROW LEVEL SECURITY;
CREATE POLICY "procurement_timeline_own" ON public.procurement_timeline FOR ALL USING (
    auth.uid() = (SELECT user_id FROM public.purchase_events WHERE id = purchase_event_id)
);
