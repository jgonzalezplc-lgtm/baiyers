-- 031: Organización multi-usuario — FASE B (RLS extendido, aditivo).
--
-- Agrega una policy _org por tabla que permite a cualquier miembro de la
-- misma organización leer/escribir las filas del owner. Se COMBINA con las
-- policies existentes vía OR (así funciona RLS en Postgres cuando hay
-- múltiples policies), así que:
--
-- - Un usuario solo en su organización (100% de los actuales) sigue con
--   comportamiento idéntico: la policy _own lo cubre igual que antes.
-- - Un miembro invitado accede vía la nueva policy _org.
--
-- IMPORTANTE: el backend usa service key, que BYPASSEA RLS. Esta migración
-- por sí sola NO cambia nada del comportamiento actual — es defensa en
-- profundidad. El acceso compartido real llega cuando los routers pasan de
-- `.eq("user_id", uid)` a `.in_("user_id", ids_organizacion(uid))`.
--
-- Se cubren solo las tablas de trabajo compartido. Tablas personales
-- (user_integrations, notificaciones, search_sessions, search_feedback) NO
-- se comparten por diseño.
--
-- IDEMPOTENTE — se puede correr varias veces.

-- ─── Tablas de trabajo con user_id directo ─────────────────────────────────
-- Cada bloque: DROP POLICY IF EXISTS + CREATE POLICY con el mismo nombre.

DROP POLICY IF EXISTS proyectos_org ON public.proyectos;
CREATE POLICY proyectos_org ON public.proyectos
    FOR ALL USING (public.es_miembro_de_organizacion(auth.uid(), user_id));

DROP POLICY IF EXISTS cotizaciones_org ON public.cotizaciones;
CREATE POLICY cotizaciones_org ON public.cotizaciones
    FOR ALL USING (public.es_miembro_de_organizacion(auth.uid(), user_id));

DROP POLICY IF EXISTS proveedores_org ON public.proveedores;
CREATE POLICY proveedores_org ON public.proveedores
    FOR ALL USING (public.es_miembro_de_organizacion(auth.uid(), user_id));

DROP POLICY IF EXISTS ordenes_compra_org ON public.ordenes_compra;
CREATE POLICY ordenes_compra_org ON public.ordenes_compra
    FOR ALL USING (public.es_miembro_de_organizacion(auth.uid(), user_id));

DROP POLICY IF EXISTS approval_requests_org ON public.approval_requests;
CREATE POLICY approval_requests_org ON public.approval_requests
    FOR ALL USING (public.es_miembro_de_organizacion(auth.uid(), user_id));

DROP POLICY IF EXISTS approval_workflows_org ON public.approval_workflows;
CREATE POLICY approval_workflows_org ON public.approval_workflows
    FOR ALL USING (public.es_miembro_de_organizacion(auth.uid(), user_id));

DROP POLICY IF EXISTS gmail_conversations_org ON public.gmail_conversations;
CREATE POLICY gmail_conversations_org ON public.gmail_conversations
    FOR ALL USING (public.es_miembro_de_organizacion(auth.uid(), user_id));

DROP POLICY IF EXISTS rfq_batches_org ON public.rfq_batches;
CREATE POLICY rfq_batches_org ON public.rfq_batches
    FOR ALL USING (public.es_miembro_de_organizacion(auth.uid(), user_id));

DROP POLICY IF EXISTS workflow_definitions_org ON public.workflow_definitions;
CREATE POLICY workflow_definitions_org ON public.workflow_definitions
    FOR ALL USING (public.es_miembro_de_organizacion(auth.uid(), user_id));

DROP POLICY IF EXISTS responsables_org ON public.responsables;
CREATE POLICY responsables_org ON public.responsables
    FOR ALL USING (public.es_miembro_de_organizacion(auth.uid(), user_id));

DROP POLICY IF EXISTS workflow_instances_org ON public.workflow_instances;
CREATE POLICY workflow_instances_org ON public.workflow_instances
    FOR ALL USING (public.es_miembro_de_organizacion(auth.uid(), user_id));

DROP POLICY IF EXISTS procurement_profiles_org ON public.procurement_profiles;
CREATE POLICY procurement_profiles_org ON public.procurement_profiles
    FOR ALL USING (public.es_miembro_de_organizacion(auth.uid(), user_id));

DROP POLICY IF EXISTS supplier_capabilities_org ON public.supplier_capabilities;
CREATE POLICY supplier_capabilities_org ON public.supplier_capabilities
    FOR ALL USING (public.es_miembro_de_organizacion(auth.uid(), user_id));

DROP POLICY IF EXISTS supplier_capability_events_org ON public.supplier_capability_events;
CREATE POLICY supplier_capability_events_org ON public.supplier_capability_events
    FOR ALL USING (public.es_miembro_de_organizacion(auth.uid(), user_id));

-- ─── Tablas hijas (sin user_id directo, se filtran vía subquery al padre) ──
-- Sus policies existentes hacen `auth.uid() = padre.user_id`. Agregamos una
-- policy _org paralela que usa el helper contra el mismo padre.

DROP POLICY IF EXISTS resultados_org ON public.resultados;
CREATE POLICY resultados_org ON public.resultados
    FOR ALL USING (
        public.es_miembro_de_organizacion(
            auth.uid(),
            (SELECT user_id FROM public.cotizaciones WHERE id = resultados.cotizacion_id)
        )
    );

DROP POLICY IF EXISTS rfq_batch_items_org ON public.rfq_batch_items;
CREATE POLICY rfq_batch_items_org ON public.rfq_batch_items
    FOR ALL USING (
        public.es_miembro_de_organizacion(
            auth.uid(),
            (SELECT user_id FROM public.rfq_batches WHERE id = rfq_batch_items.rfq_batch_id)
        )
    );

DROP POLICY IF EXISTS workflow_roles_org ON public.workflow_roles;
CREATE POLICY workflow_roles_org ON public.workflow_roles
    FOR ALL USING (
        public.es_miembro_de_organizacion(
            auth.uid(),
            (SELECT user_id FROM public.workflow_definitions WHERE id = workflow_roles.workflow_id)
        )
    );

DROP POLICY IF EXISTS responsable_roles_org ON public.responsable_roles;
CREATE POLICY responsable_roles_org ON public.responsable_roles
    FOR ALL USING (
        public.es_miembro_de_organizacion(
            auth.uid(),
            (SELECT user_id FROM public.workflow_definitions WHERE id = responsable_roles.workflow_id)
        )
    );

DROP POLICY IF EXISTS workflow_events_org ON public.workflow_events;
CREATE POLICY workflow_events_org ON public.workflow_events
    FOR ALL USING (
        public.es_miembro_de_organizacion(
            auth.uid(),
            (SELECT user_id FROM public.workflow_instances WHERE id = workflow_events.instance_id)
        )
    );

DROP POLICY IF EXISTS procurement_profile_categories_org ON public.procurement_profile_categories;
CREATE POLICY procurement_profile_categories_org ON public.procurement_profile_categories
    FOR ALL USING (
        public.es_miembro_de_organizacion(
            auth.uid(),
            (SELECT user_id FROM public.procurement_profiles WHERE id = procurement_profile_categories.profile_id)
        )
    );

-- Ver también las membresías de la organización propia (Fase A solo dejaba
-- ver la propia). Fase C usará esto para mostrar "otros miembros de tu org".
DROP POLICY IF EXISTS membresias_org ON public.membresias_organizacion;
CREATE POLICY membresias_org ON public.membresias_organizacion
    FOR SELECT USING (
        public.es_miembro_de_organizacion(auth.uid(), user_id)
    );
