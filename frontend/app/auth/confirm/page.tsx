"use client";

import { useRef, useState, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import type { EmailOtpType } from "@supabase/supabase-js";
import { createClient } from "@/lib/supabase/client";
import { BtnPrimary } from "@/components/ui";

// Los tipos soportados por esta página (no todos los EmailOtpType de Supabase).
const TEXTOS: Partial<Record<EmailOtpType, { titulo: string; boton: string }>> = {
  signup: { titulo: "Confirma tu cuenta para terminar de registrarte.", boton: "Confirmar mi cuenta" },
  recovery: { titulo: "Confirma que quieres restablecer tu contraseña.", boton: "Continuar" },
};

function ConfirmInner() {
  const params = useSearchParams();
  const yaCorrio = useRef(false);
  const [procesando, setProcesando] = useState(false);

  const tokenHash = params.get("token_hash");
  const type = params.get("type") as EmailOtpType | null;
  const textos = type ? TEXTOS[type] : undefined;
  const next = params.get("next") || (type === "signup" ? "/onboarding" : "/reset-password");

  const irA = (destino: string) => window.location.replace(destino);

  // Requiere un clic real del usuario antes de gastar el token: los scanners
  // de enlaces de Gmail/Outlook precargan el link del correo automáticamente,
  // y si verifyOtp corriera solo al cargar la página, ese GET automático
  // consumiría el token de un solo uso antes de que la persona hiciera clic.
  const confirmar = async () => {
    if (yaCorrio.current || !tokenHash || !type) return;
    yaCorrio.current = true;
    setProcesando(true);

    const supabase = createClient();
    sessionStorage.removeItem("baiyer_password_recovery");
    sessionStorage.removeItem("baiyer_password_recovery_user_id");
    await supabase.auth.signOut({ scope: "local" });

    const { data, error } = await supabase.auth.verifyOtp({ token_hash: tokenHash, type });

    if (error || !data.user?.id) {
      await supabase.auth.signOut({ scope: "local" });
      irA(type === "signup" ? "/login?error=signup" : "/login?error=recovery");
      return;
    }

    if (type === "recovery") {
      sessionStorage.setItem("baiyer_password_recovery", "verified");
      sessionStorage.setItem("baiyer_password_recovery_user_id", data.user.id);
    }
    irA(next.startsWith("/") ? next : "/reset-password");
  };

  if (!tokenHash || !textos) {
    return (
      <div style={{ minHeight: "100vh", background: "var(--canvas)", display: "flex", alignItems: "center", justifyContent: "center" }}>
        <div style={{ fontSize: 14, color: "var(--n-600)" }}>Enlace inválido o expirado.</div>
      </div>
    );
  }

  return (
    <div style={{ minHeight: "100vh", background: "var(--canvas)", display: "flex", alignItems: "center", justifyContent: "center", padding: 20 }}>
      <div style={{ textAlign: "center", maxWidth: 360 }}>
        <div style={{ fontSize: 14, color: "var(--n-600)", marginBottom: 20 }}>{textos.titulo}</div>
        <BtnPrimary onClick={confirmar} disabled={procesando}>
          {procesando ? "Confirmando…" : textos.boton}
        </BtnPrimary>
      </div>
    </div>
  );
}

export default function ConfirmPage() {
  return (
    <Suspense fallback={<div style={{ minHeight: "100vh", background: "var(--canvas)" }} />}>
      <ConfirmInner />
    </Suspense>
  );
}
