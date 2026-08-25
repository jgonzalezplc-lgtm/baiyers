"use client";
/**
 * Botón "Conectar Gmail/Outlook". Existe como componente cliente porque el
 * dashboard es un Server Component y esto necesita un handler: iniciar el
 * consentimiento dejó de ser un link navegable (`/api/gmail/auth?user_id=...`,
 * sin sesión) y pasó a ser un POST autenticado que devuelve la URL del
 * proveedor. Ver `lib/conectarCorreo.ts`.
 */
import { useState } from "react";
import { conectarCorreo } from "@/lib/conectarCorreo";

export default function ConectarCorreoBoton({
  proveedor = "gmail", label, next = "/dashboard",
}: {
  proveedor?: "gmail" | "outlook"; label: string; next?: string;
}) {
  const [yendo, setYendo] = useState(false);
  return (
    <button
      onClick={async () => { setYendo(true); await conectarCorreo(proveedor, next); setYendo(false); }}
      disabled={yendo}
      style={{
        fontSize: 12.5, fontWeight: 500, color: "var(--brand)",
        whiteSpace: "nowrap", flexShrink: 0, background: "none", border: "none",
        padding: 0, cursor: yendo ? "default" : "pointer", fontFamily: "inherit",
        opacity: yendo ? 0.6 : 1,
      }}
    >
      {yendo ? "Abriendo…" : `${label} →`}
    </button>
  );
}
