-- 045: Fase G — rollout/rollback explícito por organización.
-- Aditiva e idempotente. Sólo afecta compras NUEVAS; las instancias existentes
-- conservan workflow_instances.execution_owner.

CREATE TABLE IF NOT EXISTS public.workflow_rollout_settings (
    organization_id UUID PRIMARY KEY
        REFERENCES public.organizaciones(id) ON DELETE CASCADE,
    execution_mode TEXT NOT NULL DEFAULT 'legacy'
        CHECK (execution_mode IN ('legacy', 'unified')),
    changed_by UUID REFERENCES auth.users(id) ON DELETE SET NULL,
    change_reason TEXT,
    changed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE public.workflow_rollout_settings ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS workflow_rollout_settings_org_read ON public.workflow_rollout_settings;
CREATE POLICY workflow_rollout_settings_org_read ON public.workflow_rollout_settings
    FOR SELECT USING (
        EXISTS (
            SELECT 1 FROM public.membresias_organizacion m
            WHERE m.organizacion_id = workflow_rollout_settings.organization_id
              AND m.user_id = auth.uid()
        )
    );

DROP POLICY IF EXISTS workflow_rollout_settings_admin_write ON public.workflow_rollout_settings;
CREATE POLICY workflow_rollout_settings_admin_write ON public.workflow_rollout_settings
    FOR ALL USING (
        EXISTS (
            SELECT 1 FROM public.membresias_organizacion m
            WHERE m.organizacion_id = workflow_rollout_settings.organization_id
              AND m.user_id = auth.uid() AND m.rol = 'admin'
        )
    ) WITH CHECK (
        EXISTS (
            SELECT 1 FROM public.membresias_organizacion m
            WHERE m.organizacion_id = workflow_rollout_settings.organization_id
              AND m.user_id = auth.uid() AND m.rol = 'admin'
        )
    );

-- Cohorte habilitada: organizaciones que ya activaron un workflow con
-- asignaciones y reglas explícitas por tarjeta. Las demás quedan en legacy.
INSERT INTO public.workflow_rollout_settings (
    organization_id, execution_mode, change_reason
)
SELECT DISTINCT m.organizacion_id, 'unified',
       'Migración Fase G: workflow activo con asignaciones por tarjeta'
FROM public.workflow_definitions w
JOIN public.workflow_node_assignments a ON a.workflow_id = w.id
JOIN public.workflow_node_communication_rules r ON r.workflow_id = w.id AND r.activa = TRUE
JOIN public.membresias_organizacion m ON m.user_id = w.user_id
WHERE w.estado = 'activo'
ON CONFLICT (organization_id) DO NOTHING;
