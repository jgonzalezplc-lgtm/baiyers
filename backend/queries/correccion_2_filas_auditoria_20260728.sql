-- ============================================================================
-- Corrección puntual: 2 filas de auditoría que decían "aplicado" sin haberlo
-- estado. Detectadas el 2026-08-20 con reconciliacion_item_field_updates.sql.
--
-- Contexto: ambas son del resultado 33c68eb6-0bd5-4e9a-97e4-5e8daac9c73f
-- (campo precio_unitario, gmail_agent, 2026-07-28 19:44 y 19:48). El resultado
-- quedó en estado 'contactado' con respuesta_recibida_at NULL, o sea que la
-- escritura nunca ocurrió. Es el bug corregido en el commit 223882a.
--
-- Alcance verificado contra la DB: 2 filas mentirosas de 27 aplicadas, sobre
-- 1 resultado de 6. No es sistémico; el resto aterrizó bien.
--
-- Lo que hace: devolver esas dos filas a 'propuesta' para que aparezcan en la
-- UI de revisión y una persona decida qué hacer con ese precio.
--
-- Lo que NO hace, a propósito: tocar `resultados`. Reaplicar `new_value` podría
-- pisar un valor más nuevo cargado a mano, y ningún dato de la auditoría alcanza
-- para saber si eso pasó. Corregir el registro es seguro; reescribir el dato de
-- negocio no lo es.
--
-- Van por id explícito y no por condición: así no puede alcanzar ninguna otra
-- fila aunque se ejecute dos veces o en otro momento.
-- ============================================================================


-- ── 1. ANTES — confirmar que son las esperadas ──────────────────────────────
SELECT id, entity_id, field, estado, new_value, reviewed_by, created_at
FROM public.item_field_updates
WHERE id IN (
  'b6fbf333-b29e-4b99-ae15-64ca81b346f4',
  '28f92319-3a64-43e8-95b3-5e077a3c1575'
);
-- Esperado: 2 filas, ambas con estado='aplicado' y reviewed_by='gmail_agent_auto'.
-- Si no es eso, PARAR.


-- ── 2. La corrección ────────────────────────────────────────────────────────
UPDATE public.item_field_updates
SET estado      = 'propuesta',
    reviewed_at = NULL,
    reviewed_by = NULL
WHERE id IN (
  'b6fbf333-b29e-4b99-ae15-64ca81b346f4',
  '28f92319-3a64-43e8-95b3-5e077a3c1575'
)
AND estado = 'aplicado';   -- no-op si ya se corrigió antes


-- ── 3. DESPUÉS — verificar ──────────────────────────────────────────────────
SELECT id, entity_id, field, estado, reviewed_by
FROM public.item_field_updates
WHERE id IN (
  'b6fbf333-b29e-4b99-ae15-64ca81b346f4',
  '28f92319-3a64-43e8-95b3-5e077a3c1575'
);
-- Esperado: 2 filas con estado='propuesta' y reviewed_by NULL.


-- ── 4. Confirmar que la reconciliación queda limpia ─────────────────────────
SELECT
  count(*) FILTER (WHERE r.estado IS DISTINCT FROM 'respondido') AS nunca_aterrizaron,
  count(*)                                                       AS total_aplicadas
FROM public.item_field_updates ifu
JOIN public.resultados r ON r.id::text = ifu.entity_id
WHERE ifu.estado = 'aplicado'
  AND ifu.entity_type = 'resultado';
-- Esperado: nunca_aterrizaron = 0, total_aplicadas = 25.
