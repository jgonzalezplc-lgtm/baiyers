"use client";
/**
 * Inicia el consentimiento OAuth del buzón (Gmail / Outlook).
 *
 * Antes esto era un `<Link>` directo a `/api/gmail/auth?user_id=...`: el flujo
 * arrancaba sin sesión y con el `user_id` en la query, así que con el UUID de
 * otra persona se completaba el consentimiento con la cuenta de Google propia y
 * los tokens del atacante terminaban en la fila de la víctima. Ahora el backend
 * deriva el usuario de la sesión y devuelve la URL de Google/Microsoft; el
 * navegador sólo navega a esa URL.
 */
import { authFetch } from "@/lib/authFetch";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export async function urlConsentimientoCorreo(
  proveedor: "gmail" | "outlook", next = "/dashboard",
): Promise<string | null> {
  const resp = await authFetch(
    `${API_URL}/api/${proveedor}/conectar?next=${encodeURIComponent(next)}`,
    { method: "POST" },
  );
  if (!resp.ok) return null;
  const data = await resp.json();
  return data.url ?? null;
}

/** Versión para usar directo en un `onClick`. */
export async function conectarCorreo(proveedor: "gmail" | "outlook", next = "/dashboard") {
  const url = await urlConsentimientoCorreo(proveedor, next);
  if (url) window.location.href = url;
}
