-- 030: Organización multi-usuario — FASE A (fundación retrocompatible).
--
-- Introduce el concepto de organización sin cambiar el modelo de datos: cada
-- usuario existente queda con SU PROPIA organización, siendo el único miembro
-- admin. Los datos siguen siendo del mismo user_id de siempre, las políticas
-- RLS existentes (auth.uid() = user_id) siguen funcionando igual, y el
-- backend puede seguir usando .eq("user_id", ...) sin cambios.
--
-- Fases posteriores usarán estas tablas para: (B) compartir acceso entre
-- miembros de una misma organización, (C) invitar responsables por correo,
-- (D) firmar cada acción con actor_user_id.
--
-- IDEMPOTENTE — se puede correr varias veces sin efectos duplicados.

-- ─── Tablas ─────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS public.organizaciones (
    id              UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    nombre          TEXT NOT NULL,
    -- Dueño histórico de los datos: el user_id que hoy figura en
    -- proyectos/cotizaciones/etc. Todas las filas existentes con ese
    -- user_id pertenecen a esta organización. NO cambia al invitar gente
    -- nueva — sigue siendo la referencia histórica de propiedad.
    owner_user_id   UUID REFERENCES auth.users(id) ON DELETE CASCADE NOT NULL UNIQUE,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS organizaciones_owner_idx
    ON public.organizaciones(owner_user_id);

CREATE TABLE IF NOT EXISTS public.membresias_organizacion (
    id                 UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    organizacion_id    UUID REFERENCES public.organizaciones(id) ON DELETE CASCADE NOT NULL,
    user_id            UUID REFERENCES auth.users(id) ON DELETE CASCADE NOT NULL,
    rol                TEXT NOT NULL DEFAULT 'miembro'
                       CHECK (rol IN ('admin', 'miembro')),
    invitado_por       UUID REFERENCES auth.users(id) ON DELETE SET NULL,
    created_at         TIMESTAMPTZ DEFAULT NOW(),
    -- Por ahora un usuario pertenece a una sola organización (decisión
    -- explícita del producto — se puede relajar cuando lo pida un caso real).
    UNIQUE(user_id)
);

CREATE INDEX IF NOT EXISTS membresias_org_idx
    ON public.membresias_organizacion(organizacion_id);
CREATE INDEX IF NOT EXISTS membresias_user_idx
    ON public.membresias_organizacion(user_id);

-- ─── RLS ────────────────────────────────────────────────────────────────────
-- Cada usuario ve su propia organización y su propia membresía. Ver a otros
-- miembros de la MISMA organización se habilita recién en la Fase B (cuando
-- se comparte acceso real de datos), no ahora.

ALTER TABLE public.organizaciones ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.membresias_organizacion ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS organizaciones_mia ON public.organizaciones;
CREATE POLICY organizaciones_mia ON public.organizaciones
    FOR SELECT USING (
        owner_user_id = auth.uid()
        OR EXISTS (
            SELECT 1 FROM public.membresias_organizacion m
            WHERE m.organizacion_id = organizaciones.id
              AND m.user_id = auth.uid()
        )
    );

DROP POLICY IF EXISTS membresias_mia ON public.membresias_organizacion;
CREATE POLICY membresias_mia ON public.membresias_organizacion
    FOR SELECT USING (user_id = auth.uid());

-- ─── Helper de dominio ─────────────────────────────────────────────────────
-- Devuelve TRUE si `a` y `b` pertenecen a la misma organización. Se usará en
-- la Fase B para extender las políticas RLS existentes (proyectos, suppliers,
-- etc.) sin romper el filtro por user_id actual. Marcada STABLE para que el
-- planner la pueda cachear dentro de una misma query.

CREATE OR REPLACE FUNCTION public.es_miembro_de_organizacion(a UUID, b UUID)
RETURNS BOOLEAN
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
    SELECT EXISTS (
        SELECT 1
        FROM public.membresias_organizacion ma
        JOIN public.membresias_organizacion mb
          ON ma.organizacion_id = mb.organizacion_id
        WHERE ma.user_id = a
          AND mb.user_id = b
    );
$$;

-- ─── Backfill retrocompatible ───────────────────────────────────────────────
-- Cada auth.users existente que aún no tenga organización, obtiene la suya
-- propia y queda como miembro admin. Idempotente vía ON CONFLICT.

DO $$
DECLARE
    u RECORD;
    org_id UUID;
    nombre_default TEXT;
BEGIN
    FOR u IN
        SELECT au.id, au.email,
               COALESCE(au.raw_user_meta_data->>'empresa', au.email, 'Mi organización') AS nombre
        FROM auth.users au
        LEFT JOIN public.organizaciones o ON o.owner_user_id = au.id
        WHERE o.id IS NULL
    LOOP
        nombre_default := u.nombre;
        INSERT INTO public.organizaciones (nombre, owner_user_id)
        VALUES (nombre_default, u.id)
        RETURNING id INTO org_id;

        INSERT INTO public.membresias_organizacion (organizacion_id, user_id, rol)
        VALUES (org_id, u.id, 'admin')
        ON CONFLICT (user_id) DO NOTHING;
    END LOOP;
END $$;

-- Backfill de membresías: cualquier organización creada arriba sin
-- membresía correspondiente (no debería pasar, pero por si el DO se
-- interrumpe a mitad de camino, esto lo cierra).
INSERT INTO public.membresias_organizacion (organizacion_id, user_id, rol)
SELECT o.id, o.owner_user_id, 'admin'
FROM public.organizaciones o
LEFT JOIN public.membresias_organizacion m
    ON m.organizacion_id = o.id AND m.user_id = o.owner_user_id
WHERE m.id IS NULL
ON CONFLICT (user_id) DO NOTHING;
