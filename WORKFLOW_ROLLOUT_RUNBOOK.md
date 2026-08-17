# Runbook — rollout y rollback del workflow unificado

## Contrato operativo

`workflow_rollout_settings.execution_mode` decide quién gobierna **compras nuevas**:

- `unified`: el ciclo configurado por tarjeta gobierna RFQ, autorización, homologación y OC.
- `legacy`: se conservan los emisores y contratos anteriores.

Cada instancia fija su dueño en `workflow_instances.execution_owner`. Cambiar el rollout nunca
reescribe instancias, eventos, acciones programadas, entregas ni OCs existentes.

## Habilitación

1. Aplicar manualmente `backend/migrations/045_workflow_rollout_control.sql`.
2. Confirmar que el workflow activo valida sin errores y que sus tarjetas tienen responsables/reglas.
3. Consultar `GET /api/workflows/rollout/estado` y guardar el baseline `legacy`/`unified`.
4. Como administrador, ejecutar `PUT /api/workflows/rollout/estado`:

```json
{"execution_mode":"unified","reason":"Ciclo validado por el equipo de compras"}
```

5. Ejecutar una compra controlada completa y revisar instancias, eventos, loops agotados y envíos
   inciertos desde el mismo endpoint antes de ampliar la cohorte.

La migración habilita automáticamente sólo organizaciones que ya tienen un workflow activo con
asignaciones y reglas explícitas por tarjeta. Las demás quedan en `legacy` por ausencia de fila.

## Rollback

Como administrador:

```json
{"execution_mode":"legacy","reason":"Rollback: describir incidente y ticket"}
```

Esto desvía únicamente compras nuevas. Las instancias `unified` ya iniciadas siguen siendo consumidas
por el scheduler y deben completarse, pausarse o cancelarse explícitamente. No borrar filas ni cambiar
`execution_owner` manualmente: hacerlo puede duplicar correos o dejar loops sin dueño.

## Criterio para retirar código legacy

No eliminar bifurcaciones hasta completar al menos un ciclo productivo controlado y confirmar:

- ausencia de envíos duplicados;
- cero `delivery_uncertain` sin resolver;
- transiciones y cancelaciones visibles en timeline;
- métricas de finalización equivalentes o mejores;
- rollback ensayado sin alterar instancias en curso.
