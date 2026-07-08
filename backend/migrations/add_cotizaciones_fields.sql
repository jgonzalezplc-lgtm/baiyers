-- Campos faltantes en cotizaciones y resultados
-- Ejecutar en Supabase SQL Editor

-- 1. Agregar confianza_ia a cotizaciones
ALTER TABLE cotizaciones
  ADD COLUMN IF NOT EXISTS confianza_ia TEXT CHECK (confianza_ia IN ('alto','medio','bajo'));

-- 2. Agregar campos de respuesta faltantes en resultados
ALTER TABLE resultados
  ADD COLUMN IF NOT EXISTS moneda_cotizada TEXT DEFAULT 'CLP',
  ADD COLUMN IF NOT EXISTS notas_respuesta TEXT;

-- 3. Índice útil
CREATE INDEX IF NOT EXISTS idx_resultados_cot_estado
  ON resultados(cotizacion_id, estado);

CREATE INDEX IF NOT EXISTS idx_resultados_enviado
  ON resultados(solicitud_enviada_at)
  WHERE solicitud_enviada_at IS NOT NULL;

-- Columna JSONB para campos enriquecidos de fuentes externas
ALTER TABLE resultados
  ADD COLUMN IF NOT EXISTS metadata JSONB DEFAULT '{}';
