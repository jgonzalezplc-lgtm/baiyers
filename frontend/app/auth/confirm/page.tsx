"use client";

import { Suspense, useEffect, useRef } from "react";
import { useSearchParams } from "next/navigation";
import type { EmailOtpType } from "@supabase/supabase-js";
import { createClient } from "@/lib/supabase/client";

function ConfirmInner() {
  const params = useSearchParams();
  const yaCorrio = useRef(false);

  useEffect(() => {
    if (yaCorrio.current) return;
    yaCorrio.current = true;

    const tokenHash = params.get("token_hash");
    const type = params.get("type") as EmailOtpType | null;
    const next = params.get("next") || "/reset-password";
    const supabase = createClient();
    const irA = (destino: string) => window.location.replace(destino);

    const confirmar = async () => {
      sessionStorage.removeItem("baiyer_password_recovery");
      sessionStorage.removeItem("baiyer_password_recovery_user_id");
      await supabase.auth.signOut({ scope: "local" });

      if (!tokenHash || type !== "recovery") {
        irA("/login?error=recovery");
        return;
      }

      const { data, error } = await supabase.auth.verifyOtp({
        token_hash: tokenHash,
        type,
      });

      if (error || !data.user?.id) {
        await supabase.auth.signOut({ scope: "local" });
        irA("/login?error=recovery");
        return;
      }

      sessionStorage.setItem("baiyer_password_recovery", "verified");
      sessionStorage.setItem("baiyer_password_recovery_user_id", data.user.id);
      irA(next.startsWith("/") ? next : "/reset-password");
    };

    void confirmar();
  }, [params]);

  return (
    <div style={{ minHeight: "100vh", background: "var(--canvas)", display: "flex", alignItems: "center", justifyContent: "center" }}>
      <div style={{ fontSize: 14, color: "var(--n-600)" }}>Verificando enlace seguro…</div>
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
