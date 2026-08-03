-- 027: Workflow Builder de compras/autorizaciones — fundación (Fase 1).
-- Todo nuevo. No toca approval_workflows/approval_requests (siguen siendo la
-- fuente real del magic link de autorización, sin cambios); este workflow
-- decide CUÁNDO y A QUIÉN corresponde disparar esa autorización, no la
-- reemplaza. No aplicar sin confirmar — ejecutar manualmente en el SQL
-- Editor de Supabase.

-- ─── Definición del workflow (versionado, borrador → activo → archivado) ──
CREATE TABLE IF NOT EXISTS public.workflow_definitions (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id      UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  nombre       TEXT NOT NULL,
  version      INT NOT NULL DEFAULT 1,
  estado       TEXT NOT NULL DEFAULT 'borrador' CHECK (estado IN ('borrador', 'activo', 'archivado')),
  origen       TEXT NOT NULL DEFAULT 'visual' CHECK (origen IN ('conversacional', 'visual', 'mixto')),
  nodos        JSONB NOT NULL DEFAULT '[]'::jsonb,
  conexiones   JSONB NOT NULL DEFAULT '[]'::jsonb,
  creado_por   UUID,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_workflow_definitions_user ON public.workflow_definitions(user_id, estado);

ALTER TABLE public.workflow_definitions ENABLE ROW LEVEL SECURITY;
CREATE POLICY "workflow_definitions_own" ON public.workflow_definitions FOR ALL USING (auth.uid() = user_id);

-- Solo un workflow activo por (user_id, nombre) a la vez — activar una nueva
-- versión implica archivar la anterior primero (lo hace el servicio, no un
-- trigger, para dejar el archivo de la transición explícito en el código).
CREATE UNIQUE INDEX IF NOT EXISTS uniq_workflow_activo_por_nombre
  ON public.workflow_definitions(user_id, nombre) WHERE estado = 'activo';

-- ─── Roles del workflow (no personas) ──────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.workflow_roles (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  workflow_id  UUID NOT NULL REFERENCES public.workflow_definitions(id) ON DELETE CASCADE,
  clave        TEXT NOT NULL,
  nombre       TEXT NOT NULL,
  descripcion  TEXT,
  UNIQUE(workflow_id, clave)
);

ALTER TABLE public.workflow_roles ENABLE ROW LEVEL SECURITY;
CREATE POLICY "workflow_roles_own" ON public.workflow_roles FOR ALL USING (
  auth.uid() = (SELECT user_id FROM public.workflow_definitions WHERE id = workflow_id)
);

-- ─── Responsables (personas reales, independientes del workflow) ──────────
CREATE TABLE IF NOT EXISTS public.responsables (
  id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id            UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  nombre             TEXT NOT NULL,
  cargo              TEXT,
  email              TEXT,
  telefono           TEXT,
  usuario_baiyer_id  UUID REFERENCES auth.users(id) ON DELETE SET NULL,
  suplente_id        UUID REFERENCES public.responsables(id) ON DELETE SET NULL,
  activo             BOOLEAN NOT NULL DEFAULT true,
  created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_responsables_user ON public.responsables(user_id, activo);

ALTER TABLE public.responsables ENABLE ROW LEVEL SECURITY;
CREATE POLICY "responsables_own" ON public.responsables FOR ALL USING (auth.uid() = user_id);

-- ─── Asignación de roles a responsables, por workflow (N:M) ───────────────
-- Una persona puede tener varios roles; un rol puede tener varias personas
-- (autorización paralela) u orden explícito (autorización secuencial).
CREATE TABLE IF NOT EXISTS public.responsable_roles (
  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  responsable_id      UUID NOT NULL REFERENCES public.responsables(id) ON DELETE CASCADE,
  workflow_id         UUID NOT NULL REFERENCES public.workflow_definitions(id) ON DELETE CASCADE,
  rol_clave           TEXT NOT NULL,
  orden_autorizacion  INT,
  UNIQUE(responsable_id, workflow_id, rol_clave)
);

CREATE INDEX IF NOT EXISTS idx_responsable_roles_workflow ON public.responsable_roles(workflow_id, rol_clave);

ALTER TABLE public.responsable_roles ENABLE ROW LEVEL SECURITY;
CREATE POLICY "responsable_roles_own" ON public.responsable_roles FOR ALL USING (
  auth.uid() = (SELECT user_id FROM public.workflow_definitions WHERE id = workflow_id)
);

-- ─── Instancias del workflow sobre una lista/cotización real ──────────────
CREATE TABLE IF NOT EXISTS public.workflow_instances (
  id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id            UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  workflow_id        UUID NOT NULL REFERENCES public.workflow_definitions(id) ON DELETE RESTRICT,
  lista_proyecto_id  UUID REFERENCES public.proyectos(id) ON DELETE SET NULL,
  nodo_actual_id     TEXT,
  estado_workflow    TEXT NOT NULL DEFAULT 'activo' CHECK (estado_workflow IN ('activo', 'pausado', 'completado', 'cancelado')),
  created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_workflow_instances_lista ON public.workflow_instances(lista_proyecto_id);
CREATE INDEX IF NOT EXISTS idx_workflow_instances_user ON public.workflow_instances(user_id, estado_workflow);

ALTER TABLE public.workflow_instances ENABLE ROW LEVEL SECURITY;
CREATE POLICY "workflow_instances_own" ON public.workflow_instances FOR ALL USING (auth.uid() = user_id);

-- ─── Historial inmutable (mismo patrón que supplier_capability_events) ────
CREATE TABLE IF NOT EXISTS public.workflow_events (
  id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  instance_id           UUID NOT NULL REFERENCES public.workflow_instances(id) ON DELETE CASCADE,
  nodo_id               TEXT,
  actor_responsable_id  UUID REFERENCES public.responsables(id) ON DELETE SET NULL,
  rol_usado             TEXT,
  accion                TEXT NOT NULL,
  estado_anterior       TEXT,
  estado_nuevo          TEXT,
  comentario            TEXT,
  canal                 TEXT NOT NULL DEFAULT 'baiyer' CHECK (canal IN ('baiyer', 'email')),
  referencia_externa    TEXT,
  workflow_version      INT,
  clave_idempotencia    TEXT NOT NULL UNIQUE,
  created_at            TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_workflow_events_instance ON public.workflow_events(instance_id, created_at);

ALTER TABLE public.workflow_events ENABLE ROW LEVEL SECURITY;
CREATE POLICY "workflow_events_own" ON public.workflow_events FOR ALL USING (
  auth.uid() = (SELECT user_id FROM public.workflow_instances WHERE id = instance_id)
);
