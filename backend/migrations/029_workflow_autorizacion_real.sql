-- 029: conecta el Workflow Builder (migración 027) al flujo real de
-- autorización de listas. approval_requests ya existe (014) — se le agregan
-- columnas nullable para poder emitir varias solicitudes (una por
-- responsable) atadas a un nodo/instancia de workflow, sin romper el flujo
-- legado de un solo `aprobador_email` para cuentas sin workflow activo.

ALTER TABLE public.approval_requests
    ADD COLUMN IF NOT EXISTS workflow_instance_id UUID REFERENCES public.workflow_instances(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS workflow_nodo_id TEXT,
    ADD COLUMN IF NOT EXISTS responsable_id UUID REFERENCES public.responsables(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS approval_requests_instance_idx
    ON public.approval_requests(workflow_instance_id, workflow_nodo_id);
