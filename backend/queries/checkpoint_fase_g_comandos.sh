#!/usr/bin/env bash
# ============================================================================
# Checkpoint productivo de Fase G — comandos del runbook
# (WORKFLOW_ROLLOUT_RUNBOOK.md, pasos 3 a 5)
#
# No hay UI para el rollout: los endpoints sólo se alcanzan por API con JWT.
# El PUT además exige es_admin.
#
# Organización objetivo: Vital (dd2f4312-fa17-4753-9536-caa39297f374)
# ============================================================================

API="https://baiyers-production.up.railway.app"

# ── Obtener el JWT ──────────────────────────────────────────────────────────
# En https://www.baiyer.cl, con sesión iniciada, abrir la consola del navegador:
#
#   JSON.parse(Object.entries(localStorage)
#     .find(([k]) => k.includes('auth-token'))[1]).access_token
#
# Copiar el valor y pegarlo acá. Es una credencial: no la commitees ni la
# pegues en un chat. Caduca en ~1 hora.
TOKEN="PEGAR_AQUI"


# ── PASO 3 — Baseline. Guardar esta salida ANTES de cambiar nada ────────────
# Es el punto de comparación para saber si el ciclo unified se comportó igual
# o mejor que legacy. Sin baseline, el checkpoint no prueba nada.
echo "=== BASELINE (guardar) ==="
curl -s "$API/api/workflows/rollout/estado" \
  -H "Authorization: Bearer $TOKEN" | tee baseline_rollout.json | python3 -m json.tool


# ── PASO 2 (verificación previa) — el workflow activo debe validar limpio ────
# cambiar_rollout() rechaza habilitar unified si hay errores, pero conviene
# verlos antes para no descubrirlo con un 400 opaco.
# Reemplazar WORKFLOW_ID por el id del workflow activo (GET /api/workflows).
echo
echo "=== WORKFLOWS ==="
curl -s "$API/api/workflows" -H "Authorization: Bearer $TOKEN" | python3 -m json.tool

# echo "=== VALIDACIÓN ==="
# curl -s "$API/api/workflows/WORKFLOW_ID/validar" \
#   -H "Authorization: Bearer $TOKEN" | python3 -m json.tool


# ── PASO 4 — Habilitar unified ──────────────────────────────────────────────
# DESCOMENTAR SÓLO cuando el baseline esté guardado y la validación limpia.
# Esto gobierna COMPRAS NUEVAS únicamente; no reescribe nada existente.
#
# curl -s -X PUT "$API/api/workflows/rollout/estado" \
#   -H "Authorization: Bearer $TOKEN" \
#   -H "Content-Type: application/json" \
#   -d '{"execution_mode":"unified","reason":"Checkpoint productivo Fase G"}' \
#   | python3 -m json.tool


# ── PASO 5 — Después del ciclo controlado, comparar contra el baseline ──────
# echo "=== DESPUÉS ==="
# curl -s "$API/api/workflows/rollout/estado" \
#   -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
#
# Criterios de aprobación (runbook, "Criterio para retirar código legacy"):
#   - cero envíos duplicados
#   - cero delivery_uncertain sin resolver
#   - transiciones y cancelaciones visibles en el timeline
#   - métricas de finalización equivalentes o mejores que el baseline
#   - rollback ensayado sin alterar instancias en curso


# ── ROLLBACK — si algo sale mal ─────────────────────────────────────────────
# Desvía sólo compras NUEVAS. Las instancias unified ya iniciadas siguen
# siendo consumidas por el scheduler y hay que completarlas, pausarlas o
# cancelarlas explícitamente. NO borrar filas ni tocar execution_owner a mano:
# el runbook advierte que eso puede duplicar correos o dejar loops sin dueño.
#
# curl -s -X PUT "$API/api/workflows/rollout/estado" \
#   -H "Authorization: Bearer $TOKEN" \
#   -H "Content-Type: application/json" \
#   -d '{"execution_mode":"legacy","reason":"Rollback: <incidente>"}' \
#   | python3 -m json.tool
