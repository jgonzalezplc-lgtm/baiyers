-- 042: Workflow unificado Fase D — enlaza RFQ batch con instancia/ejecución.
-- Aditiva e idempotente. Aplicación manual en Supabase.

ALTER TABLE public.rfq_batches
    ADD COLUMN IF NOT EXISTS workflow_instance_id UUID
        REFERENCES public.workflow_instances(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS node_execution_id UUID
        REFERENCES public.workflow_node_executions(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS execution_owner TEXT NOT NULL DEFAULT 'legacy'
        CHECK (execution_owner IN ('legacy', 'unified')),
    ADD COLUMN IF NOT EXISTS resolution_state TEXT NOT NULL DEFAULT 'pendiente'
        CHECK (resolution_state IN ('pendiente', 'completa', 'descartada')),
    ADD COLUMN IF NOT EXISTS resolved_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_rfq_batches_workflow_instance
    ON public.rfq_batches(workflow_instance_id, resolution_state);
CREATE INDEX IF NOT EXISTS idx_rfq_batches_node_execution
    ON public.rfq_batches(node_execution_id, resolution_state);

-- Las filas históricas siguen perteneciendo al emisor legacy. Sólo una RFQ
-- enlazada explícitamente por el código de Fase D queda bajo el motor nuevo.
UPDATE public.rfq_batches
   SET execution_owner = 'legacy'
 WHERE execution_owner IS NULL;
