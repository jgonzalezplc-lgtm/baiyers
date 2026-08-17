-- 041: Fundación del workflow de compras + comunicaciones unificado (PRD Fase A).
--
-- Agrega configuración por tarjeta, ejecuciones por visita y una cola durable.
-- NO conecta todavía el cron ni reemplaza emisores existentes. La aplicación
-- de esta migración es manual en Supabase y debe confirmarse antes de habilitar
-- las fases operativas.

-- ─── Responsables por acción/tarjeta ──────────────────────────────────────

CREATE TABLE IF NOT EXISTS public.workflow_node_assignments (
    id                       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workflow_id              UUID NOT NULL REFERENCES public.workflow_definitions(id) ON DELETE CASCADE,
    nodo_id                  TEXT NOT NULL,
    rol_clave                TEXT NOT NULL,
    responsable_id           UUID NOT NULL REFERENCES public.responsables(id) ON DELETE RESTRICT,
    modo                     TEXT NOT NULL DEFAULT 'individual'
                             CHECK (modo IN ('individual', 'paralelo', 'secuencial')),
    orden                    INTEGER CHECK (orden IS NULL OR orden > 0),
    es_propietario_excepcion BOOLEAN NOT NULL DEFAULT false,
    created_at               TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (workflow_id, nodo_id, rol_clave, responsable_id),
    CHECK (modo = 'secuencial' OR orden IS NULL)
);

CREATE INDEX IF NOT EXISTS idx_workflow_node_assignments_node
    ON public.workflow_node_assignments(workflow_id, nodo_id, rol_clave);

-- ─── Reglas que asocian plantillas/automatización a una tarjeta ───────────

CREATE TABLE IF NOT EXISTS public.workflow_node_communication_rules (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workflow_id           UUID NOT NULL REFERENCES public.workflow_definitions(id) ON DELETE CASCADE,
    nodo_id               TEXT NOT NULL,
    rol_clave             TEXT,
    evento_plantilla      TEXT NOT NULL,
    audiencia             TEXT NOT NULL CHECK (audiencia IN ('internal', 'external')),
    canal                 TEXT NOT NULL DEFAULT 'email' CHECK (canal = 'email'),
    destinatario_tipo     TEXT NOT NULL CHECK (destinatario_tipo IN (
                              'responsable_rol', 'solicitante', 'autorizador',
                              'equipo', 'proveedor', 'contacto_proveedor'
                          )),
    disparador_tipo       TEXT NOT NULL DEFAULT 'al_entrar' CHECK (disparador_tipo IN (
                              'al_entrar', 'al_ocurrir_evento', 'manual', 'despues_demora'
                          )),
    disparador_evento     TEXT,
    demora_inicial_dias   INTEGER NOT NULL DEFAULT 0 CHECK (demora_inicial_dias >= 0),
    repetir_cada_dias     INTEGER CHECK (repetir_cada_dias IS NULL OR repetir_cada_dias >= 1),
    max_intentos          INTEGER CHECK (max_intentos IS NULL OR max_intentos >= 1),
    evento_termino        TEXT,
    alcance_termino       TEXT NOT NULL DEFAULT 'tarjeta' CHECK (alcance_termino IN (
                              'destinatario', 'proveedor', 'tarjeta'
                          )),
    resultado_al_terminar TEXT,
    politica_agotamiento  TEXT CHECK (politica_agotamiento IS NULL OR politica_agotamiento IN (
                              'pausar', 'escalar', 'descartar_entidad', 'avanzar_timeout'
                          )),
    resultado_agotamiento TEXT,
    activa                BOOLEAN NOT NULL DEFAULT true,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (disparador_tipo <> 'al_ocurrir_evento' OR disparador_evento IS NOT NULL),
    CHECK (repetir_cada_dias IS NULL OR evento_termino IS NOT NULL),
    CHECK (repetir_cada_dias IS NULL OR politica_agotamiento IS NOT NULL),
    CHECK (politica_agotamiento <> 'avanzar_timeout' OR resultado_agotamiento IS NOT NULL)
);

CREATE INDEX IF NOT EXISTS idx_workflow_node_communication_rules_node
    ON public.workflow_node_communication_rules(workflow_id, nodo_id, activa);

-- ─── Una ejecución por cada visita real a una tarjeta ─────────────────────

CREATE TABLE IF NOT EXISTS public.workflow_node_executions (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    instance_id      UUID NOT NULL REFERENCES public.workflow_instances(id) ON DELETE CASCADE,
    nodo_id          TEXT NOT NULL,
    visit_number     INTEGER NOT NULL DEFAULT 1 CHECK (visit_number > 0),
    estado           TEXT NOT NULL DEFAULT 'pendiente' CHECK (estado IN (
                         'pendiente', 'activa', 'esperando', 'completada',
                         'omitida', 'fallida', 'pausada'
                     )),
    resultado        TEXT,
    context_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,
    started_at       TIMESTAMPTZ,
    completed_at     TIMESTAMPTZ,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (instance_id, nodo_id, visit_number)
);

CREATE INDEX IF NOT EXISTS idx_workflow_node_executions_instance
    ON public.workflow_node_executions(instance_id, created_at);

-- ─── Cola durable para envíos y vencimientos futuros ──────────────────────

CREATE TABLE IF NOT EXISTS public.workflow_scheduled_actions (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    node_execution_id     UUID NOT NULL REFERENCES public.workflow_node_executions(id) ON DELETE CASCADE,
    communication_rule_id UUID NOT NULL REFERENCES public.workflow_node_communication_rules(id) ON DELETE RESTRICT,
    recipient_key         TEXT NOT NULL,
    due_at                TIMESTAMPTZ NOT NULL,
    estado                TEXT NOT NULL DEFAULT 'programada' CHECK (estado IN (
                              'programada', 'reservada', 'ejecutando', 'enviada',
                              'cancelada', 'fallida', 'agotada', 'delivery_uncertain'
                          )),
    attempt_number        INTEGER NOT NULL DEFAULT 1 CHECK (attempt_number > 0),
    technical_attempts    INTEGER NOT NULL DEFAULT 0 CHECK (technical_attempts >= 0),
    lease_token           UUID,
    lease_until           TIMESTAMPTZ,
    last_error            TEXT,
    idempotency_key       TEXT NOT NULL UNIQUE,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (node_execution_id, communication_rule_id, recipient_key, attempt_number)
);

CREATE INDEX IF NOT EXISTS idx_workflow_scheduled_actions_due
    ON public.workflow_scheduled_actions(due_at, estado)
    WHERE estado IN ('programada', 'reservada');

-- La instancia declara quién gobierna sus efectos. Todas las existentes y
-- las creadas por el código actual quedan en `legacy`; una fase posterior
-- deberá optar explícitamente por `unified`, evitando doble envío.
ALTER TABLE public.workflow_instances
    ADD COLUMN IF NOT EXISTS workflow_version INTEGER,
    ADD COLUMN IF NOT EXISTS execution_owner TEXT NOT NULL DEFAULT 'legacy'
        CHECK (execution_owner IN ('legacy', 'unified'));

UPDATE public.workflow_instances i
   SET workflow_version = w.version
  FROM public.workflow_definitions w
 WHERE w.id = i.workflow_id
   AND i.workflow_version IS NULL;

-- Enlaces de auditoría opcionales. Las filas antiguas siguen siendo válidas.
ALTER TABLE public.workflow_events
    ADD COLUMN IF NOT EXISTS node_execution_id UUID
        REFERENCES public.workflow_node_executions(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS communication_rule_id UUID
        REFERENCES public.workflow_node_communication_rules(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_workflow_events_node_execution
    ON public.workflow_events(node_execution_id, created_at);

-- Reserva atómica de una acción. Una reserva vencida puede recuperarse; una
-- acción enviada/cancelada/agotada nunca vuelve a ser adquirible.
CREATE OR REPLACE FUNCTION public.claim_workflow_scheduled_action(
    p_action_id UUID,
    p_lease_token UUID,
    p_lease_seconds INTEGER DEFAULT 300
) RETURNS SETOF public.workflow_scheduled_actions
LANGUAGE sql
SET search_path = public
AS $$
    UPDATE public.workflow_scheduled_actions
       SET estado = 'reservada',
           lease_token = p_lease_token,
           lease_until = now() + make_interval(secs => greatest(p_lease_seconds, 1)),
           updated_at = now()
     WHERE id = p_action_id
       AND due_at <= now()
       AND (
           estado = 'programada'
           OR (estado = 'reservada' AND lease_until < now())
       )
    RETURNING *;
$$;

-- ─── Reserva previa al envío de correo ────────────────────────────────────

ALTER TABLE public.mail_delivery_events
    ADD COLUMN IF NOT EXISTS reservation_token UUID,
    ADD COLUMN IF NOT EXISTS reserved_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS scheduled_action_id UUID
        REFERENCES public.workflow_scheduled_actions(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now();

ALTER TABLE public.mail_delivery_events
    DROP CONSTRAINT IF EXISTS mail_delivery_events_estado_check;
ALTER TABLE public.mail_delivery_events
    ADD CONSTRAINT mail_delivery_events_estado_check CHECK (estado IN (
        'pendiente', 'reservada', 'enviado', 'fallido', 'delivery_uncertain'
    ));

-- Devuelve la fila sólo al proceso que adquirió una clave nueva. Si ya
-- existía, devuelve cero filas: el llamador NO tiene permiso para enviar.
CREATE OR REPLACE FUNCTION public.reserve_mail_delivery_event(
    p_organizacion_id UUID,
    p_evento TEXT,
    p_destinatario_email TEXT,
    p_idempotency_key TEXT,
    p_reservation_token UUID,
    p_definition_id UUID DEFAULT NULL,
    p_version_id UUID DEFAULT NULL,
    p_workflow_id UUID DEFAULT NULL,
    p_workflow_nodo_id TEXT DEFAULT NULL,
    p_proveedor_id UUID DEFAULT NULL,
    p_responsable_id UUID DEFAULT NULL
) RETURNS SETOF public.mail_delivery_events
LANGUAGE sql
SET search_path = public
AS $$
    INSERT INTO public.mail_delivery_events (
        organizacion_id, evento, destinatario_email, idempotency_key,
        estado, reservation_token, reserved_at, definition_id, version_id,
        workflow_id, workflow_nodo_id, proveedor_id, responsable_id, updated_at
    ) VALUES (
        p_organizacion_id, p_evento, lower(trim(p_destinatario_email)), p_idempotency_key,
        'reservada', p_reservation_token, now(), p_definition_id, p_version_id,
        p_workflow_id, p_workflow_nodo_id, p_proveedor_id, p_responsable_id, now()
    )
    ON CONFLICT (idempotency_key) DO NOTHING
    RETURNING *;
$$;

-- ─── RLS por membresía de organización ────────────────────────────────────

ALTER TABLE public.workflow_node_assignments ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.workflow_node_communication_rules ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.workflow_node_executions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.workflow_scheduled_actions ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS workflow_node_assignments_org ON public.workflow_node_assignments;
CREATE POLICY workflow_node_assignments_org ON public.workflow_node_assignments
    FOR SELECT USING (
        EXISTS (
            SELECT 1
              FROM public.workflow_definitions w
              JOIN public.membresias_organizacion owner_m ON owner_m.user_id = w.user_id
              JOIN public.membresias_organizacion actor_m
                ON actor_m.organizacion_id = owner_m.organizacion_id
             WHERE w.id = workflow_node_assignments.workflow_id
               AND actor_m.user_id = auth.uid()
        )
    );

DROP POLICY IF EXISTS workflow_node_communication_rules_org ON public.workflow_node_communication_rules;
CREATE POLICY workflow_node_communication_rules_org ON public.workflow_node_communication_rules
    FOR SELECT USING (
        EXISTS (
            SELECT 1
              FROM public.workflow_definitions w
              JOIN public.membresias_organizacion owner_m ON owner_m.user_id = w.user_id
              JOIN public.membresias_organizacion actor_m
                ON actor_m.organizacion_id = owner_m.organizacion_id
             WHERE w.id = workflow_node_communication_rules.workflow_id
               AND actor_m.user_id = auth.uid()
        )
    );

DROP POLICY IF EXISTS workflow_node_executions_org ON public.workflow_node_executions;
CREATE POLICY workflow_node_executions_org ON public.workflow_node_executions
    FOR SELECT USING (
        EXISTS (
            SELECT 1
              FROM public.workflow_instances i
              JOIN public.membresias_organizacion owner_m ON owner_m.user_id = i.user_id
              JOIN public.membresias_organizacion actor_m
                ON actor_m.organizacion_id = owner_m.organizacion_id
             WHERE i.id = workflow_node_executions.instance_id
               AND actor_m.user_id = auth.uid()
        )
    );

DROP POLICY IF EXISTS workflow_scheduled_actions_org ON public.workflow_scheduled_actions;
CREATE POLICY workflow_scheduled_actions_org ON public.workflow_scheduled_actions
    FOR SELECT USING (
        EXISTS (
            SELECT 1
              FROM public.workflow_node_executions ne
              JOIN public.workflow_instances i ON i.id = ne.instance_id
              JOIN public.membresias_organizacion owner_m ON owner_m.user_id = i.user_id
              JOIN public.membresias_organizacion actor_m
                ON actor_m.organizacion_id = owner_m.organizacion_id
             WHERE ne.id = workflow_scheduled_actions.node_execution_id
               AND actor_m.user_id = auth.uid()
        )
    );

-- Escrituras pasan por el backend con service role y chequeo admin/actor.
-- No se agregan policies INSERT/UPDATE/DELETE para clientes directos.
