"use client";
import { useEffect } from "react";
import { useParams, useRouter } from "next/navigation";
import { Spinner } from "@/components/ui";

/**
 * "Cotizaciones" se unificó con "Listas de cotización": toda compra (1 ítem o
 * varios) es ahora una lista. `/listas/{id}` envuelve automáticamente una
 * cotización suelta si aún no tenía lista propia. Esta ruta se mantiene solo
 * para no romper enlaces viejos guardados por el usuario.
 */
export default function CotizacionDetalleRedirectPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  useEffect(() => { router.replace(`/listas/${id}`); }, [router, id]);
  return <Spinner label="Redirigiendo…" />;
}
