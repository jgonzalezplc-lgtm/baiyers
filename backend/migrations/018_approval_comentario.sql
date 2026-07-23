-- 018: Agregar campo comentario a approval_requests para comentarios de rechazo
ALTER TABLE public.approval_requests ADD COLUMN IF NOT EXISTS comentario TEXT;
