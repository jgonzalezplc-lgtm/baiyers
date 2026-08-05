"use client";
/**
 * authFetch — igual que `fetch`, pero agrega el header
 * `Authorization: Bearer <access_token>` de la sesión activa de Supabase.
 *
 * Parte del cierre del riesgo de seguridad más importante detectado en
 * PLAN_DATA_FOUNDATION.md: hoy casi todos los fetch del frontend mandan
 * `user_id` como query/body y el backend confía en eso ciegamente. Los
 * endpoints que se migren a `Depends(get_auth_context)` van a IGNORAR ese
 * `user_id` y van a verificar quién sos de verdad contra el token — así
 * que para llamarlos hay que usar `authFetch` en vez de `fetch` a secas.
 *
 * Migración incremental: los endpoints que todavía no usan AuthContext
 * siguen funcionando igual con `fetch` normal — no hace falta cambiar los
 * ~39 puntos de la app de una sola vez.
 */
import { createClient } from "@/lib/supabase/client";

export async function authFetch(input: string, init: RequestInit = {}): Promise<Response> {
  const { data } = await createClient().auth.getSession();
  const token = data.session?.access_token;
  const headers = new Headers(init.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  return fetch(input, { ...init, headers });
}
