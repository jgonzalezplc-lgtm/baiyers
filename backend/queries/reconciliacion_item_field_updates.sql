-- ============================================================================
-- Reconciliación: filas de `item_field_updates` que dicen "aplicado" pero cuyo
-- valor no está en `resultados`.
--
-- Motivo: hasta el commit 223882a los agentes de Gmail y Outlook insertaban la
-- fila ya marcada como `aplicado` y escribían en `resultados` después. Si ese
-- segundo paso fallaba, la auditoría quedaba afirmando algo que nunca ocurrió.
-- El código ya está corregido; esto sirve para saber cuántos datos VIEJOS
-- quedaron mintiendo.
--
-- TODO ESTE ARCHIVO ES DE SÓLO LECTURA. No hay UPDATE ni DELETE a propósito
-- (ver la nota del final antes de "corregir" nada).
--
-- Ejecutar en el SQL Editor de Supabase, paso por paso y en orden.
-- ============================================================================


-- ── PASO 0 — Confirmar el esquema real antes de creer en nada de lo que sigue ─
-- `backend/migrations/add_resultado_respuesta_fields.sql` declara columnas
-- (`precio_respuesta`, `moneda_respuesta`) DISTINTAS de las que el código
-- escribe hoy (`precio_cotizado`, `moneda_cotizada`, según _FIELD_MAP_RESULTADOS
-- en routers/gmail.py). O sea que los .sql del repo no reflejan la tabla real.
--
-- Correr esto PRIMERO. Si `precio_cotizado` / `moneda_cotizada` no aparecen,
-- parar y ajustar los nombres en el PASO 3 antes de seguir.
SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_schema = 'public' AND table_name = 'resultados'
  AND column_name IN (
    'id', 'estado', 'precio_cotizado', 'moneda_cotizada', 'plazo_entrega',
    'condiciones_pago', 'notas_respuesta', 'respuesta_recibida_at',
    -- candidatas alternativas, por si el nombre real es otro:
    'precio_respuesta', 'moneda_respuesta', 'respuesta_at'
  )
ORDER BY column_name;


-- ── PASO 1 — Dimensionar el universo ────────────────────────────────────────
-- Cuánto hay que reconciliar y de qué agente vino.
SELECT
  updated_by,
  field,
  count(*) AS filas,
  min(created_at)::date AS desde,
  max(created_at)::date AS hasta
FROM public.item_field_updates
WHERE estado = 'aplicado'
  AND entity_type = 'resultado'
GROUP BY updated_by, field
ORDER BY filas DESC;


-- ── PASO 2 — Huérfanas: el resultado ni siquiera existe ─────────────────────
-- `entity_id` es TEXT (no UUID) y no tiene FK, así que puede apuntar a nada.
-- Se compara con cast a texto para no reventar si hay algún valor no-UUID.
SELECT ifu.id, ifu.entity_id, ifu.field, ifu.updated_by, ifu.created_at
FROM public.item_field_updates ifu
LEFT JOIN public.resultados r ON r.id::text = ifu.entity_id
WHERE ifu.estado = 'aplicado'
  AND ifu.entity_type = 'resultado'
  AND r.id IS NULL
ORDER BY ifu.created_at DESC;


-- ── PASO 3 — El chequeo principal: ¿el valor está realmente en `resultados`? ─
--
-- Sutileza importante para no generar falsos positivos en masa: un mismo
-- (entity_id, field) puede tener VARIAS filas aplicadas a lo largo del tiempo
-- (el proveedor corrige el precio en un correo posterior). Que una fila vieja
-- no coincida con la columna es lo ESPERADO si después vino otra más nueva.
-- Por eso se compara únicamente la fila MÁS RECIENTE de cada (entity_id, field).
--
-- `new_value` es JSONB escalar (viene de json.dumps), así que `#>> '{}'` extrae
-- el valor como texto tanto si era número como si era string.
WITH ultima_aplicada AS (
  SELECT DISTINCT ON (ifu.entity_id, ifu.field)
    ifu.id,
    ifu.entity_id,
    ifu.field,
    ifu.new_value #>> '{}' AS valor_esperado,
    ifu.updated_by,
    ifu.confidence,
    ifu.created_at
  FROM public.item_field_updates ifu
  WHERE ifu.estado = 'aplicado'
    AND ifu.entity_type = 'resultado'
    -- Sólo los campos con columna dedicada. Los demás (disponibilidad,
    -- stock_disponible) se acumulan como texto libre en notas_respuesta y no
    -- se pueden comparar de forma confiable — ver PASO 4.
    AND ifu.field IN ('precio_unitario', 'moneda', 'plazo_entrega', 'condiciones_pago')
  ORDER BY ifu.entity_id, ifu.field, ifu.created_at DESC
),
comparacion AS (
  SELECT
    u.*,
    r.estado AS estado_resultado,
    r.respuesta_recibida_at,
    CASE u.field
      WHEN 'precio_unitario'  THEN r.precio_cotizado::text
      WHEN 'moneda'           THEN r.moneda_cotizada
      WHEN 'plazo_entrega'    THEN r.plazo_entrega
      WHEN 'condiciones_pago' THEN r.condiciones_pago
    END AS valor_real
  FROM ultima_aplicada u
  JOIN public.resultados r ON r.id::text = u.entity_id
)
SELECT
  id            AS item_field_update_id,
  entity_id     AS resultado_id,
  field,
  valor_esperado,
  valor_real,
  estado_resultado,
  updated_by,
  confidence,
  created_at,
  CASE
    WHEN valor_real IS NULL THEN 'FALTA: la columna está vacía'
    WHEN field = 'precio_unitario'
         AND valor_esperado ~ '^-?[0-9]+(\.[0-9]+)?$'
         AND valor_real     ~ '^-?[0-9]+(\.[0-9]+)?$'
         AND valor_esperado::numeric = valor_real::numeric
      THEN 'OK'
    WHEN btrim(lower(valor_esperado)) = btrim(lower(valor_real)) THEN 'OK'
    ELSE 'DIFIERE'
  END AS diagnostico
FROM comparacion
WHERE
  valor_real IS NULL
  OR NOT (
    (field = 'precio_unitario'
      AND valor_esperado ~ '^-?[0-9]+(\.[0-9]+)?$'
      AND valor_real     ~ '^-?[0-9]+(\.[0-9]+)?$'
      AND valor_esperado::numeric = valor_real::numeric)
    OR btrim(lower(valor_esperado)) = btrim(lower(valor_real))
  )
ORDER BY created_at DESC;


-- ── PASO 4 — Señal indirecta para los campos sin columna dedicada ────────────
-- `disponibilidad` / `stock_disponible` se acumulan en notas_respuesta como
-- texto, así que no se puede comparar el valor exacto. Lo que SÍ es
-- inequívoco: _aplicar_campo_resultado siempre setea estado='respondido' y
-- respuesta_recibida_at. Si la fila dice "aplicado" y el resultado no quedó
-- respondido, esa escritura no ocurrió.
SELECT
  ifu.id AS item_field_update_id,
  ifu.entity_id AS resultado_id,
  ifu.field,
  ifu.updated_by,
  ifu.created_at,
  r.estado AS estado_resultado,
  r.respuesta_recibida_at
FROM public.item_field_updates ifu
JOIN public.resultados r ON r.id::text = ifu.entity_id
WHERE ifu.estado = 'aplicado'
  AND ifu.entity_type = 'resultado'
  AND (r.respuesta_recibida_at IS NULL OR r.estado IS DISTINCT FROM 'respondido')
ORDER BY ifu.created_at DESC;


-- ============================================================================
-- ANTES DE "CORREGIR": leer esto.
--
-- La tentación es un UPDATE masivo que reaplique `new_value` sobre `resultados`,
-- o que pase esas filas a 'propuesta'. NO hacerlo a ciegas:
--
-- 1. Reaplicar un valor viejo puede PISAR uno más nuevo y correcto (cargado a
--    mano, o por un correo posterior). El PASO 3 ya sólo mira la fila más
--    reciente, pero "más reciente en item_field_updates" no es lo mismo que
--    "más reciente en resultados": una edición manual no deja rastro acá.
-- 2. Una fila que dice DIFIERE puede ser un dato corregido a mano después, que
--    es exactamente lo que se quiere conservar.
-- 3. Los resultados ya usados en una OC emitida no deberían tocarse: cambiar el
--    precio a posteriori desalinea la OC de su cotización.
--
-- Lo razonable es revisar los casos 'FALTA' (donde la columna está vacía y no
-- hay nada que pisar) y decidir uno por uno. Si el volumen es alto, cruzar
-- primero contra `ordenes_compra` para excluir lo ya comprado.
-- ============================================================================
