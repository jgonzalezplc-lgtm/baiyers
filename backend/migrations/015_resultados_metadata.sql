-- ============================================================
-- 015: arreglos a la tabla resultados
--
-- 1) Columna metadata: info enriquecida de cada resultado (JSON string):
--    ubicacion_vendedor, plazo_entrega_estimado, stock, rating, garantía,
--    fuente_label, etc. Usada por la vista comparador (UBICACIÓN / ENTREGA).
--
-- 2) Constraint de fuente: el CHECK original solo aceptaba
--    google/mercadolibre/alibaba/manual, lo que hacía fallar el guardado
--    completo de resultados cuando la búsqueda incluía fuentes nuevas
--    (Mouser, DigiKey, TME, Sodimac, Easy, La Sierra, Construmart,
--    Vitel, Dartel, Ferrelectrica, Gobantes, Rhona).
-- ============================================================

ALTER TABLE public.resultados ADD COLUMN IF NOT EXISTS metadata TEXT;

ALTER TABLE public.resultados DROP CONSTRAINT IF EXISTS resultados_fuente_check;
ALTER TABLE public.resultados ADD CONSTRAINT resultados_fuente_check
    CHECK (fuente IN (
        'google', 'mercadolibre', 'alibaba', 'manual',
        'mouser', 'digikey', 'tme',
        'sodimac', 'easy', 'lasierra', 'construmart',
        'vitel', 'dartel', 'ferrelectrica', 'gobantes', 'rhona'
    ));
