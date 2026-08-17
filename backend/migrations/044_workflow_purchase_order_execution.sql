-- 044: Workflow unificado Fase F — enlaza OC con instancia/ejecución.
-- Aditiva e idempotente. Aplicación manual en Supabase.

ALTER TABLE public.ordenes_compra
    ADD COLUMN IF NOT EXISTS lista_proyecto_id UUID
        REFERENCES public.proyectos(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS workflow_instance_id UUID
        REFERENCES public.workflow_instances(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS node_execution_id UUID
        REFERENCES public.workflow_node_executions(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS execution_owner TEXT NOT NULL DEFAULT 'legacy'
        CHECK (execution_owner IN ('legacy', 'unified'));

CREATE INDEX IF NOT EXISTS idx_ordenes_compra_workflow_instance
    ON public.ordenes_compra(workflow_instance_id, estado);
CREATE INDEX IF NOT EXISTS idx_ordenes_compra_node_execution
    ON public.ordenes_compra(node_execution_id, estado);

UPDATE public.ordenes_compra
   SET execution_owner = 'legacy'
 WHERE execution_owner IS NULL;
