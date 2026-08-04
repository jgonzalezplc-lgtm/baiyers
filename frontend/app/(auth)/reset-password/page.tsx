"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { createClient } from "@/lib/supabase/client";
import { BtnPrimary, Input } from "@/components/ui";

export default function ResetPasswordPage() {
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [listo, setListo] = useState(false);
  const [recoveryReady, setRecoveryReady] = useState(false);
  const router = useRouter();
  const [supabase] = useState(() => createClient());

  useEffect(() => {
    let activo = true;
    const recoveryUserId = sessionStorage.getItem("baiyer_password_recovery_user_id");

    if (sessionStorage.getItem("baiyer_password_recovery") !== "verified" || !recoveryUserId) {
      setError("Esta pantalla no fue abierta desde un enlace de recuperación válido. Solicita uno nuevo.");
      return () => { activo = false; };
    }

    supabase.auth.getUser().then(({ data, error: sessionError }) => {
      if (!activo) return;
      if (sessionError || !data.user || data.user.id !== recoveryUserId) {
        sessionStorage.removeItem("baiyer_password_recovery");
        sessionStorage.removeItem("baiyer_password_recovery_user_id");
        void supabase.auth.signOut({ scope: "local" });
        setError("Este enlace no tiene una sesión de recuperación válida. Solicita uno nuevo.");
        return;
      }
      setRecoveryReady(true);
    });

    return () => { activo = false; };
  }, [supabase]);

  const handleReset = async () => {
    if (!recoveryReady) {
      setError("La sesión de recuperación aún no está lista. Solicita un enlace nuevo.");
      return;
    }
    if (password.length < 6) {
      setError("La contrasena debe tener al menos 6 caracteres");
      return;
    }
    if (password !== confirm) {
      setError("Las contrasenas no coinciden");
      return;
    }
    setLoading(true);
    setError("");
    const recoveryUserId = sessionStorage.getItem("baiyer_password_recovery_user_id");
    const { data: currentUserData, error: currentUserError } = await supabase.auth.getUser();
    if (currentUserError || !currentUserData.user || !recoveryUserId || currentUserData.user.id !== recoveryUserId) {
      sessionStorage.removeItem("baiyer_password_recovery");
      sessionStorage.removeItem("baiyer_password_recovery_user_id");
      await supabase.auth.signOut({ scope: "local" });
      setLoading(false);
      setRecoveryReady(false);
      setError("La identidad de recuperación no coincide con la sesión actual. Solicita un enlace nuevo.");
      return;
    }
    const { error } = await supabase.auth.updateUser({ password });
    setLoading(false);
    if (error) {
      const detalle = error.message.toLowerCase();
      if (detalle.includes("different from the old password") || detalle.includes("same password")) {
        setError("La nueva contraseña debe ser diferente de la contraseña anterior.");
      } else if (detalle.includes("session") || detalle.includes("expired") || detalle.includes("token")) {
        setError("La sesión de recuperación no es válida o expiró. Solicita un enlace nuevo.");
      } else if (detalle.includes("password") || detalle.includes("weak")) {
        setError(`La contraseña no cumple los requisitos de seguridad: ${error.message}`);
      } else {
        setError(`No se pudo actualizar la contraseña: ${error.message}`);
      }
    } else {
      sessionStorage.removeItem("baiyer_password_recovery");
      sessionStorage.removeItem("baiyer_password_recovery_user_id");
      await supabase.auth.signOut({ scope: "local" });
      setListo(true);
      setTimeout(() => router.push("/login"), 2000);
    }
  };

  return (
    <div style={{
      minHeight: "100vh",
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      background: "var(--bg-base)",
    }}>
      <div style={{
        width: "100%",
        maxWidth: 400,
        padding: "40px 36px",
        background: "var(--bg-surface)",
        border: "1px solid var(--border-default)",
      }}>
        <div className="label" style={{ color: "var(--accent)", marginBottom: 6 }}>Claria</div>
        <h1 style={{ fontSize: 20, fontWeight: 700, color: "var(--text-primary)", margin: "0 0 24px", letterSpacing: "-0.02em" }}>
          Nueva contrasena
        </h1>

        {listo ? (
          <div style={{
            background: "var(--fill-success)",
            border: "1px solid var(--palette-green-500)",
            padding: 14,
            fontSize: 12,
            color: "var(--text-success)",
            lineHeight: 1.6,
          }}>
            Contrasena actualizada. Redirigiendo al inicio de sesión...
          </div>
        ) : (
          <>
            {error && (
              <div style={{
                background: "var(--fill-error)",
                border: "1px solid var(--border-accent)",
                padding: "10px 12px",
                fontSize: 11,
                color: "var(--text-error)",
                marginBottom: 16,
              }}>
                {error}
              </div>
            )}

            <div style={{ display: "flex", flexDirection: "column", gap: 14, marginBottom: 20 }}>
              <Input
                label="Nueva contrasena"
                type="password"
                value={password}
                onChange={e => setPassword(e.target.value)}
                placeholder="••••••••"
              />
              <div>
                <label className="label" style={{ color: "var(--text-muted)", display: "block", marginBottom: 6 }}>
                  Confirmar contrasena
                </label>
                <input
                  type="password"
                  value={confirm}
                  onChange={e => setConfirm(e.target.value)}
                  onKeyDown={e => e.key === "Enter" && handleReset()}
                  placeholder="••••••••"
                  className="w-full px-4 py-3 bg-[var(--bg-surface)] border border-[var(--border-default)]
                             text-[var(--text-primary)] font-mono text-sm
                             focus:outline-none focus:border-[var(--border-strong)]
                             placeholder:text-[var(--text-muted)]"
                />
              </div>
            </div>

            <BtnPrimary onClick={handleReset} disabled={loading || !recoveryReady} className="w-full justify-center">
              {loading ? "Actualizando..." : recoveryReady ? "Guardar nueva contrasena" : "Validando enlace..."}
            </BtnPrimary>
          </>
        )}
      </div>
    </div>
  );
}
