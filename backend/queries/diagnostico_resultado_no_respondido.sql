-- ============================================================================
-- Seguimiento del PASO 4: por qué esas escrituras en `resultados` no ocurrieron.
--
-- Hallazgo que dispara esto: 2 filas de item_field_updates dicen "aplicado"
-- sobre el mismo resultado (33c68eb6-0bd5-4e9a-97e4-5e8daac9c73f), mismo campo
-- (precio_unitario), con 4 minutos de diferencia, y el resultado sigue en
-- estado 'contactado' con respuesta_recibida_at NULL.
--
-- HIPÓTESIS A CONFIRMAR O DESCARTAR: hay un CHECK constraint en
-- `resultados.estado` que NO acepta el literal 'respondido'.
-- `_aplicar_campo_resultado` (gmail.py:586 y outlook.py:429) escribe
-- {"estado": "respondido", ...}, pero el único lugar del repo que enumera los
-- estados de esa tabla (migrations/add_resultado_respuesta_fields.sql:14) dice
-- 'respondio', SIN la "d" final.
--
-- Si el constraint es 'respondio', TODA auto-aplicación falla siempre, para
-- todos los usuarios, desde siempre. No sería un fallo transitorio.
--
-- Sólo lectura.
-- ============================================================================


-- ── A — La prueba decisiva y más barata ─────────────────────────────────────
-- Si existe aunque sea UN resultado en 'respondido', el constraint acepta ese
-- literal y la hipótesis queda descartada de inmediato.
SELECT estado, count(*) AS filas
FROM public.resultados
GROUP BY estado
ORDER BY filas DESC;


-- ── B — El constraint, textual ──────────────────────────────────────────────
SELECT con.conname, pg_get_constraintdef(con.oid) AS definicion
FROM pg_constraint con
JOIN pg_class rel ON rel.oid = con.conrelid
JOIN pg_namespace nsp ON nsp.oid = rel.relnamespace
WHERE nsp.nspname = 'public'
  AND rel.relname = 'resultados'
  AND con.contype = 'c';


-- ── C — El resultado afectado, completo ─────────────────────────────────────
-- Interesa si precio_cotizado quedó NULL (escritura fallida) o si tiene un
-- valor que llegó por otra vía.
SELECT id, estado, precio_cotizado, moneda_cotizada, plazo_entrega,
       condiciones_pago, notas_respuesta, respuesta_recibida_at
FROM public.resultados
WHERE id = '33c68eb6-0bd5-4e9a-97e4-5e8daac9c73f';


-- ── D — Qué valor se intentó escribir ───────────────────────────────────────
-- Si las dos filas traen el MISMO new_value, son dos intentos del mismo dato
-- (reintento tras un fallo). Si traen valores distintos, fueron dos correos.
SELECT id, field, new_value, previous_value, confidence, currency,
       source_type, source_id, created_at, reviewed_by
FROM public.item_field_updates
WHERE entity_id = '33c68eb6-0bd5-4e9a-97e4-5e8daac9c73f'
ORDER BY created_at;


-- ── E — ¿Es un caso aislado o sistémico? ────────────────────────────────────
-- Cuántos resultados distintos tienen auto-aplicaciones que nunca aterrizaron.
-- Si el número es parecido al total de auto-aplicaciones, es sistémico.
SELECT
  count(*) FILTER (WHERE r.estado IS DISTINCT FROM 'respondido') AS nunca_aterrizaron,
  count(*)                                                       AS total_aplicadas,
  count(DISTINCT ifu.entity_id)                                  AS resultados_distintos
FROM public.item_field_updates ifu
JOIN public.resultados r ON r.id::text = ifu.entity_id
WHERE ifu.estado = 'aplicado'
  AND ifu.entity_type = 'resultado';
