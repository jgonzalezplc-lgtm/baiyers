"use client";
/**
 * Chat de onboarding flotante: aparece sobre el dashboard mientras falten datos
 * requeridos del perfil (empresa, RUT, nombre, industria). "Omitir por ahora" lo
 * oculta sólo para la sesión actual del navegador (sessionStorage) — al iniciar
 * sesión de nuevo (nueva pestaña/sesión) vuelve a aparecer hasta completarse.
 */
import { useEffect, useState } from "react";
import { X } from "lucide-react";
import OnboardingChat from "./OnboardingChat";

const DISMISS_KEY = "baiyer-onboarding-omitido";

export default function OnboardingFloating() {
  const [abierto, setAbierto] = useState(false);
  const [listo, setListo] = useState(false);

  useEffect(() => {
    import("@/lib/supabase/client").then(({ createClient }) => createClient().auth.getSession()).then(({ data }) => {
      const sesionActual = data.session?.access_token || "";
      const omitidoEn = typeof window !== "undefined" ? sessionStorage.getItem(DISMISS_KEY) : null;
      if (!sesionActual || omitidoEn !== sesionActual) setAbierto(true);
      setListo(true);
    }).catch(() => {
      setAbierto(true);
      setListo(true);
    });
  }, []);

  const omitir = async () => {
    try {
      const { createClient } = await import("@/lib/supabase/client");
      const { data } = await createClient().auth.getSession();
      sessionStorage.setItem(DISMISS_KEY, data.session?.access_token || "sesion-actual");
    } catch { /* ignore */ }
    setAbierto(false);
  };

  const onDone = () => setAbierto(false);

  if (!listo || !abierto) return null;

  return (
    <div style={{
      position: "fixed", bottom: 20, right: 20, zIndex: 80,
      width: 380, maxWidth: "calc(100vw - 32px)", height: 520, maxHeight: "calc(100vh - 100px)",
      background: "var(--surface)", border: "1px solid var(--n-200)",
      borderRadius: "var(--r-lg)", boxShadow: "var(--shadow-pop)",
      display: "flex", flexDirection: "column", overflow: "hidden",
    }}>
      {/* Header */}
      <div style={{
        display: "flex", alignItems: "center", gap: 10,
        padding: "12px 14px", borderBottom: "1px solid var(--n-200)", flexShrink: 0,
      }}>
        <span style={{
          width: 26, height: 26, borderRadius: 7, flexShrink: 0,
          background: "var(--brand)", color: "#fff",
          display: "inline-flex", alignItems: "center", justifyContent: "center",
          fontSize: 13, fontWeight: 700,
        }}>B</span>
        <div style={{ minWidth: 0, flex: 1 }}>
          <div style={{ fontSize: 13.5, fontWeight: 600, color: "var(--n-900)" }}>Completa tu perfil</div>
          <div style={{ fontSize: 11.5, color: "var(--n-500)" }}>Un par de datos y listo</div>
        </div>
        <button
          onClick={omitir}
          aria-label="Omitir por ahora"
          title="Omitir por ahora"
          style={{
            background: "none", border: "none", cursor: "pointer",
            color: "var(--n-500)", display: "inline-flex", padding: 4, flexShrink: 0,
          }}
        >
          <X size={17} strokeWidth={1.75} />
        </button>
      </div>

      <div style={{ flex: 1, minHeight: 0, display: "flex", flexDirection: "column" }}>
        <OnboardingChat floating onDone={onDone} onSkip={omitir} />
      </div>
    </div>
  );
}
