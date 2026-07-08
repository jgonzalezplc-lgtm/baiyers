"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { createClient } from "@/lib/supabase/client";
import { BtnPrimary, Input } from "@/components/ui";

export default function ResetPasswordPage() {
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [listo, setListo] = useState(false);
  const router = useRouter();
  const supabase = createClient();

  const handleReset = async () => {
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
    const { error } = await supabase.auth.updateUser({ password });
    setLoading(false);
    if (error) {
      setError("Error al actualizar. El enlace puede haber expirado.");
    } else {
      setListo(true);
      setTimeout(() => router.push("/dashboard"), 2000);
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
            Contrasena actualizada. Redirigiendo al dashboard...
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

            <BtnPrimary onClick={handleReset} disabled={loading} className="w-full justify-center">
              {loading ? "Actualizando..." : "Guardar nueva contrasena"}
            </BtnPrimary>
          </>
        )}
      </div>
    </div>
  );
}
