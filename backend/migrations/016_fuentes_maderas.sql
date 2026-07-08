-- Migración 016: fuentes de proveedores de madera y construcción CL.
-- Amplía el CHECK constraint de resultados.fuente con las fuentes del sprint
-- de maderas. Idempotente: se puede ejecutar más de una vez.
--
-- Ejecutar en el SQL Editor de Supabase (el service key no puede hacer DDL).

ALTER TABLE resultados DROP CONSTRAINT IF EXISTS resultados_fuente_check;

ALTER TABLE resultados ADD CONSTRAINT resultados_fuente_check
  CHECK (fuente IN (
    -- v1
    'google', 'mercadolibre', 'alibaba', 'manual',
    -- electrónica
    'mouser', 'digikey', 'tme',
    -- retail construcción CL
    'sodimac', 'easy', 'lasierra', 'construmart',
    -- eléctrico CL
    'vitel', 'dartel', 'ferrelectrica', 'gobantes', 'rhona',
    -- maderas CL (migración 016)
    'clcsa', 'wmaderas', 'ferramenta', 'maderas_dir'
  ));
