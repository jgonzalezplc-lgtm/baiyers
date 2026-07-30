-- 023: seguimiento de OC por respuesta de correo. Hasta ahora la única forma
-- de marcar una OC como recibida era que el proveedor hiciera clic en un link
-- de confirmación — poco realista, un proveedor real simplemente responde el
-- correo. Se mantiene el link como alternativa, pero ahora el agente de
-- Gmail (mismo cron de 1 min que ya lee respuestas de cotización) también
-- puede detectar un acuse de recibo o un aviso de despacho por correo y
-- mover el estado solo.

ALTER TABLE public.ordenes_compra ADD COLUMN IF NOT EXISTS recibido_conforme_at TIMESTAMPTZ;
ALTER TABLE public.ordenes_compra ADD COLUMN IF NOT EXISTS despacho_at TIMESTAMPTZ;
ALTER TABLE public.ordenes_compra ADD COLUMN IF NOT EXISTS despacho_detalle TEXT;

-- Vincula la conversación de Gmail con la OC que la originó (paralelo a
-- resultado_id/cotizacion_id, que son para el flujo de cotización).
ALTER TABLE public.gmail_conversations ADD COLUMN IF NOT EXISTS oc_id UUID REFERENCES public.ordenes_compra(id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS idx_gmail_conversations_oc ON public.gmail_conversations(oc_id);
