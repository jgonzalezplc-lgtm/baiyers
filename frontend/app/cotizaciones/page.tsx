"use client";
import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { Spinner } from "@/components/ui";

/**
 * "Cotizaciones" se unificó con "Listas de cotización": toda compra (1 ítem o
 * varios) es ahora una lista. Esta ruta se mantiene solo para no romper enlaces
 * viejos guardados por el usuario.
 */
export default function CotizacionesRedirectPage() {
  const router = useRouter();
  useEffect(() => { router.replace("/listas"); }, [router]);
  return <Spinner label="Redirigiendo…" />;
}
