"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { createClient } from "@/lib/supabase/client";
import Link from "next/link";
import { BtnPrimary, BtnSecondary, Input } from "@/components/ui";

export default function LoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [modo, setModo] = useState<"login" | "recovery">("login");
  const [recoveryEnviado, setRecoveryEnviado] = useState(false);
  const router = useRouter();
  const supabase = createClient();

  const handleLogin = async () => {
    setLoading(true);
    setError("");
    const { data, error } = await supabase.auth.signInWithPassword({ email, password });
    console.log("[login] Supabase response:", { data, error });
    if (error) {
      setError("Email o contrasena incorrectos");
      setLoading(false);
    } else {
      window.location.href = "/dashboard";
    }
  };

  const handleRecovery = async () => {
    if (!email) { setError("Ingresa tu email primero"); return; }
    setLoading(true);
    setError("");
    const { error } = await supabase.auth.resetPasswordForEmail(email, {
      redirectTo: `${window.location.origin}/reset-password`,
    });
    setLoading(false);
    if (error) {
      setError("Error al enviar el correo. Verifica el email ingresado.");
    } else {
      setRecoveryEnviado(true);
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
        maxWidth: 380,
        padding: "40px 36px",
        background: "var(--bg-surface)",
        border: "1px solid var(--border-default)",
      }}>
        {/* Header */}
        <div className="label" style={{ color: "var(--accent)", marginBottom: 6 }}>
          Claria
        </div>
        <h1 style={{
          fontSize: 20,
          fontWeight: 700,
          color: "var(--text-primary)",
          margin: "0 0 28px",
          letterSpacing: "-0.02em",
        }}>
          {modo === "login" ? "Iniciar sesion" : "Recuperar contrasena"}
        </h1>

        {/* Error */}
        {error && (
          <div style={{
            background: "var(--fill-error)",
            border: "1px solid var(--border-accent)",
            padding: "10px 12px",
            fontSize: 11,
            color: "var(--text-error)",
            marginBottom: 20,
          }}>
            {error}
          </div>
        )}

        {modo === "recovery" && recoveryEnviado ? (
          <div>
            <div style={{
              background: "var(--fill-success)",
              border: "1px solid var(--palette-green-500)",
              padding: "14px",
              fontSize: 12,
              color: "var(--text-success)",
              marginBottom: 20,
              lineHeight: 1.6,
            }}>
              Correo enviado a <strong>{email}</strong>. Revisa tu bandeja de entrada
              y sigue el enlace para restablecer tu contrasena.
            </div>
            <BtnSecondary
              onClick={() => { setModo("login"); setRecoveryEnviado(false); }}
              className="w-full"
            >
              Volver al login
            </BtnSecondary>
          </div>
        ) : (
          <>
            <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
              <Input
                label="Email"
                type="email"
                value={email}
                onChange={e => setEmail(e.target.value)}
                placeholder="tu@empresa.cl"
              />

              {modo === "login" && (
                <div>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
                    <span className="label">Contrasena</span>
                    <button
                      onClick={() => { setModo("recovery"); setError(""); }}
                      style={{
                        fontSize: 10,
                        color: "var(--accent)",
                        background: "none",
                        border: "none",
                        cursor: "pointer",
                        fontFamily: "var(--font-mono)",
                        padding: 0,
                        letterSpacing: "0.05em",
                      }}
                    >
                      Olvide mi contrasena
                    </button>
                  </div>
                  <input
                    type="password"
                    value={password}
                    onChange={e => setPassword(e.target.value)}
                    onKeyDown={e => e.key === "Enter" && handleLogin()}
                    placeholder="••••••••"
                    className="w-full px-4 py-3 bg-[var(--bg-surface)] border border-[var(--border-default)]
                               text-[var(--text-primary)] font-mono text-sm
                               focus:outline-none focus:border-[var(--border-strong)]
                               placeholder:text-[var(--text-muted)]"
                    style={{ borderRadius: "var(--radius-default)" }}
                  />
                </div>
              )}
            </div>

            <div style={{ marginTop: 24, display: "flex", flexDirection: "column", gap: 8 }}>
              <BtnPrimary
                onClick={modo === "login" ? handleLogin : handleRecovery}
                disabled={loading}
                className="w-full justify-center"
              >
                {loading ? "..." : modo === "login" ? "Ingresar" : "Enviar correo de recuperacion"}
              </BtnPrimary>

              {modo === "recovery" && (
                <BtnSecondary
                  onClick={() => { setModo("login"); setError(""); }}
                  className="w-full"
                >
                  Volver al login
                </BtnSecondary>
              )}
            </div>
          </>
        )}

        {modo === "login" && (
          <p style={{ textAlign: "center", fontSize: 11, color: "var(--text-muted)", marginTop: 20 }}>
            No tienes cuenta?{" "}
            <Link href="/register" style={{ color: "var(--accent)", textDecoration: "none" }}>
              Registrate gratis
            </Link>
          </p>
        )}
      </div>
    </div>
  );
}
