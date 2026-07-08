-- Agregar campos de respuesta de proveedor a la tabla resultados
-- Ejecutar en Supabase SQL Editor

ALTER TABLE resultados
  ADD COLUMN IF NOT EXISTS respuesta_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS precio_respuesta NUMERIC,
  ADD COLUMN IF NOT EXISTS moneda_respuesta TEXT DEFAULT 'CLP',
  ADD COLUMN IF NOT EXISTS plazo_entrega TEXT,
  ADD COLUMN IF NOT EXISTS condiciones_pago TEXT,
  ADD COLUMN IF NOT EXISTS notas_respuesta TEXT,
  ADD COLUMN IF NOT EXISTS evaluacion_score NUMERIC;

-- Actualizar estados posibles (por si hay constraint)
-- estado: 'encontrado' | 'contactado' | 'respondio' | 'seleccionado'

-- Índice para búsquedas por cotizacion_id + estado
CREATE INDEX IF NOT EXISTS idx_resultados_cotizacion_estado
  ON resultados(cotizacion_id, estado);
