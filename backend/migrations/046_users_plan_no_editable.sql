-- Migración 046: que un usuario no pueda editarse su propio plan/cuota.
--
-- Hallazgo de la auditoría externa del 25-08-2026: con la publishable key (que
-- está en el bundle JS, por diseño) y el access_token de la sesión propia,
-- cualquiera hacía
--
--   PATCH /rest/v1/users?id=eq.<mi_id>   {"plan": "enterprise"}
--
-- y la policy de UPDATE lo aceptaba. Postgres no permite restringir columnas
-- desde RLS, así que el candado va en un trigger.
--
-- Alcance real: hoy NINGÚN gate del backend lee `public.users.plan` — el plan
-- que sí se aplica vive en `api_keys.plan` (ese camino se cerró por separado el
-- 25-08-2026, ver `api_publica/router.py`). O sea que esto es higiene, no una
-- fuga de ingresos en curso: se aplica para que el día que algo empiece a leer
-- esta tabla no herede un campo escribible por el usuario.
--
-- El trigger corre con los privilegios del definidor y sólo bloquea a los roles
-- de cliente: `service_role` (el backend) y los cambios hechos por el propio
-- Postgres/admin siguen pasando.
--
-- Idempotente: se puede correr más de una vez.
-- Ejecutar en el SQL Editor de Supabase.

CREATE OR REPLACE FUNCTION public.impedir_autoedicion_de_plan()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  columna text;
  protegidas text[] := ARRAY[
    'plan', 'trial_hasta', 'plan_activo_hasta', 'cotizaciones_mes_actual'
  ];
  antes jsonb := to_jsonb(OLD);
  despues jsonb := to_jsonb(NEW);
BEGIN
  -- El backend usa la service key y tiene que poder cambiar el plan (alta,
  -- upgrade, reset mensual de cuota). Sólo se frena al cliente.
  IF current_setting('request.jwt.claim.role', true) IS DISTINCT FROM 'authenticated'
     AND current_setting('request.jwt.claim.role', true) IS DISTINCT FROM 'anon' THEN
    RETURN NEW;
  END IF;

  FOREACH columna IN ARRAY protegidas LOOP
    -- `? columna` tolera que alguna de estas columnas no exista en esta base:
    -- si no está, no hay nada que proteger.
    IF antes ? columna AND (antes -> columna) IS DISTINCT FROM (despues -> columna) THEN
      RAISE EXCEPTION 'La columna % no se puede modificar desde el cliente', columna
        USING ERRCODE = '42501';
    END IF;
  END LOOP;

  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS impedir_autoedicion_de_plan ON public.users;

CREATE TRIGGER impedir_autoedicion_de_plan
  BEFORE UPDATE ON public.users
  FOR EACH ROW
  EXECUTE FUNCTION public.impedir_autoedicion_de_plan();
