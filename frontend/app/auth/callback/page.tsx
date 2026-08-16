"use client";
/**
 * Callback de OAuth (Google) 100% client-side: intercambia el código por sesión
 * en el navegador (donde está el code_verifier de PKCE) y redirige con
 * window.location al host público. Evita los problemas de host interno
 * (localhost:8080) que ocurren al redirigir server-side detrás del proxy de Railway.
 */
import { Suspense, useEffect, useRef } from "react";
import { useSearchParams } from "next/navigation";
import { createClient } from "@/lib/supabase/client";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

/**
 * Si el login vino con "conectar_gmail=1" (botón de Google en login/registro),
 * encadena el consentimiento de correo real (/api/gmail/auth) cuando el usuario
 * todavía no lo tiene conectado, para no exigir un segundo paso manual desde el
 * dashboard. Si ya está conectado, o el chequeo falla, sigue al destino normal.
 */
async function resolverDestinoGmail(accessToken: string | undefined, userId: string, next: string): Promise<string> {
  if (!accessToken) return next;
  try {
    const resp = await fetch(`${API_URL}/api/gmail/status`, {
      headers: { Authorization: `Bearer ${accessToken}` },
    });
    if (!resp.ok) return next;
    const data = await resp.json();
    if (data.connected) return next;
  } catch {
    return next;
  }
  return `${API_URL}/api/gmail/auth?user_id=${encodeURIComponent(userId)}&next=${encodeURIComponent(next)}`;
}

/** Mismo patrón que resolverDestinoGmail, para el login con Outlook. */
async function resolverDestinoOutlook(accessToken: string | undefined, userId: string, next: string): Promise<string> {
  if (!accessToken) return next;
  try {
    const resp = await fetch(`${API_URL}/api/outlook/status`, {
      headers: { Authorization: `Bearer ${accessToken}` },
    });
    if (!resp.ok) return next;
    const data = await resp.json();
    if (data.connected) return next;
  } catch {
    return next;
  }
  return `${API_URL}/api/outlook/auth?user_id=${encodeURIComponent(userId)}&next=${encodeURIComponent(next)}`;
}

function CallbackInner() {
  const params = useSearchParams();
  const yaCorrio = useRef(false);   // evita el doble intercambio (StrictMode/remount)

  useEffect(() => {
    if (yaCorrio.current) return;
    yaCorrio.current = true;

    const code = params.get("code");
    // Un callback sin destino explícito corresponde a un login, no a un
    // registro. El onboarding decide por completitud del perfil, nunca por
    // el mero hecho de haber usado Google OAuth.
    const next = params.get("next") || "/dashboard";
    const isRecovery = params.get("flow") === "recovery";
    const conectarGmail = params.get("conectar_gmail") === "1";
    const conectarOutlook = params.get("conectar_outlook") === "1";
    const supabase = createClient();

    const irA = (destino: string) => window.location.replace(destino);

    if (!code) { irA("/login?error=oauth"); return; }

    supabase.auth.exchangeCodeForSession(code).then(async ({ data, error }) => {
      if (!error) {
        if (isRecovery) {
          if (!data.user?.id) {
            await supabase.auth.signOut({ scope: "local" });
            irA("/login?error=recovery");
            return;
          }
          sessionStorage.setItem("baiyer_password_recovery", "verified");
          sessionStorage.setItem("baiyer_password_recovery_user_id", data.user.id);
          irA(next);
          return;
        }
        if (conectarGmail && data.user?.id) {
          const destino = await resolverDestinoGmail(data.session?.access_token, data.user.id, next);
          irA(destino);
          return;
        }
        if (conectarOutlook && data.user?.id) {
          const destino = await resolverDestinoOutlook(data.session?.access_token, data.user.id, next);
          irA(destino);
          return;
        }
        irA(next);
        return;
      }
      // En recuperación nunca aceptamos como fallback una sesión anterior:
      // podría corresponder a un usuario distinto del destinatario del correo.
      if (isRecovery) {
        sessionStorage.removeItem("baiyer_password_recovery");
        sessionStorage.removeItem("baiyer_password_recovery_user_id");
        await supabase.auth.signOut({ scope: "local" });
        irA("/login?error=recovery");
        return;
      }
      // Si "falló" pero la sesión igual quedó creada (código ya consumido), entrar.
      const { data: sessionData } = await supabase.auth.getSession();
      irA(sessionData.session ? next : "/login?error=oauth");
    });
  }, [params]);

  return (
    <div style={{ minHeight: "100vh", background: "var(--bg-base)", display: "flex", alignItems: "center", justifyContent: "center" }}>
      <div style={{ textAlign: "center" }}>
        <div style={{ display: "flex", gap: 6, justifyContent: "center", marginBottom: 16 }}>
          {[0, 1, 2].map(i => <div key={i} style={{ width: 8, height: 8, background: "var(--accent)", opacity: 0.3 + i * 0.35, animation: "pulse 1s infinite" }} />)}
        </div>
        <div style={{ fontSize: 13, color: "var(--text-muted)" }}>Iniciando sesión…</div>
      </div>
      <style>{`@keyframes pulse { 0%,100% { opacity:.3 } 50% { opacity:1 } }`}</style>
    </div>
  );
}

export default function AuthCallbackPage() {
  return (
    <Suspense fallback={<div style={{ minHeight: "100vh", background: "var(--bg-base)" }} />}>
      <CallbackInner />
    </Suspense>
  );
}
