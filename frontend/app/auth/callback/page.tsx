"use client";
/**
 * Callback de OAuth (Google) 100% client-side: intercambia el código por sesión
 * en el navegador (donde está el code_verifier de PKCE) y redirige con
 * window.location al host público. Evita los problemas de host interno
 * (localhost:8080) que ocurren al redirigir server-side detrás del proxy de Railway.
 */
import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { createClient } from "@/lib/supabase/client";

function CallbackInner() {
  const params = useSearchParams();
  const [msg, setMsg] = useState("Iniciando sesión…");

  useEffect(() => {
    const code = params.get("code");
    const next = params.get("next") || "/onboarding";
    if (!code) { window.location.replace("/login?error=oauth"); return; }

    createClient().auth.exchangeCodeForSession(code).then(({ error }) => {
      if (error) {
        setMsg("No se pudo completar el inicio de sesión.");
        setTimeout(() => window.location.replace("/login?error=oauth"), 1200);
      } else {
        window.location.replace(next);
      }
    });
  }, [params]);

  return (
    <div style={{ minHeight: "100vh", background: "var(--bg-base)", display: "flex", alignItems: "center", justifyContent: "center" }}>
      <div style={{ textAlign: "center" }}>
        <div style={{ display: "flex", gap: 6, justifyContent: "center", marginBottom: 16 }}>
          {[0, 1, 2].map(i => <div key={i} style={{ width: 8, height: 8, background: "var(--accent)", opacity: 0.3 + i * 0.35, animation: "pulse 1s infinite" }} />)}
        </div>
        <div style={{ fontSize: 13, color: "var(--text-muted)" }}>{msg}</div>
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
