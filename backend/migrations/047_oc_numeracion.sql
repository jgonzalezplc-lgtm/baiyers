-- 047 — Numeración de Órdenes de Compra por empresa: OC-2026-BVITAL-0007
--
-- Problema que resuelve (bugs reales, verificados en producción):
--
--   1. `correlativo = len(filas) + 1` contaba filas en vez de leer el máximo:
--      borrar una OC hacía que la siguiente reutilizara un número ya emitido.
--   2. El conteo no filtraba por organización, así que el correlativo de una
--      empresa avanzaba cuando otra emitía una OC. Se ve en los datos: la
--      organización de prueba tiene 0002, 0003, 0004, 0005 y 0007 — faltan la
--      0001 y la 0006, consumidas por otra organización.
--   3. No había restricción de unicidad: dos creaciones simultáneas obtenían el
--      mismo número y la base aceptaba las dos.
--
-- El código de empresa además cumple un requisito del negocio: Baiyer se integra
-- a empresas que YA emiten sus propias OC. Sin un marcador de origen, un
-- `OC-2026-0007` de Baiyer puede confundirse con el `OC-2026-0007` del ERP del
-- cliente en una auditoría.

-- ── 1. Código de empresa, asignado una sola vez ─────────────────────────────
-- Va en la organización y no se deriva del nombre en cada emisión: si la
-- empresa se renombra, las OCs nuevas cambiarían de código y arrancarían un
-- correlativo paralelo para la misma empresa.
ALTER TABLE public.organizaciones
    ADD COLUMN IF NOT EXISTS codigo_oc TEXT;

-- Parcial: varias organizaciones pueden tener NULL mientras no emitan ninguna OC.
CREATE UNIQUE INDEX IF NOT EXISTS organizaciones_codigo_oc_uniq
    ON public.organizaciones (codigo_oc)
    WHERE codigo_oc IS NOT NULL;

-- ── 2. Unicidad del número de OC ────────────────────────────────────────────
-- Índice PARCIAL, sólo sobre el formato nuevo (el que lleva `-B...-`).
--
-- Es deliberado y es el punto más importante de esta migración: las OCs legado
-- (`OC-2026-0007`) YA FUERON ENVIADAS a proveedores en PDF. Renumerarlas para
-- que un índice global pudiera aplicarse significaría que el número del
-- documento que el proveedor tiene en su bandeja deja de existir en el sistema.
-- Un índice global además fallaría al crearse si dos organizaciones comparten un
-- número histórico, que es justamente lo que el bug 2 produjo.
--
-- Los números nuevos son únicos por construcción (incluyen el código de
-- empresa); este índice lo hace cumplir también ante inserciones concurrentes,
-- que es lo único que el código Python no puede garantizar por sí solo.
CREATE UNIQUE INDEX IF NOT EXISTS ordenes_compra_numero_oc_nuevo_uniq
    ON public.ordenes_compra (numero_oc)
    WHERE numero_oc ~ '^OC-[0-9]{4}-B[A-Z0-9]+-[0-9]+$';

-- ── Verificación ────────────────────────────────────────────────────────────
-- Después de aplicar, esto debería devolver 0 filas (ningún duplicado en el
-- formato nuevo). Si devuelve algo, hay que resolverlo antes de emitir más OCs:
--
--   SELECT numero_oc, count(*)
--   FROM public.ordenes_compra
--   WHERE numero_oc ~ '^OC-[0-9]{4}-B[A-Z0-9]+-[0-9]+$'
--   GROUP BY numero_oc HAVING count(*) > 1;
--
-- Y esto muestra los códigos asignados a cada organización:
--
--   SELECT nombre, codigo_oc FROM public.organizaciones ORDER BY codigo_oc;
