-- Migración 017: permitir plan 'free' (y demás planes de la app) en users.
-- El registro fallaba con: users_plan_check violado — el trigger de signup
-- inserta plan='free' pero la restricción no lo permitía.
-- Idempotente: se puede correr más de una vez.
--
-- Ejecutar en el SQL Editor de Supabase.

ALTER TABLE public.users DROP CONSTRAINT IF EXISTS users_plan_check;

ALTER TABLE public.users ADD CONSTRAINT users_plan_check
  CHECK (plan IN ('free', 'trial', 'pro', 'business', 'enterprise'));
