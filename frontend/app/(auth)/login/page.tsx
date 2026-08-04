"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { createClient } from "@/lib/supabase/client";
import Link from "next/link";
import { BtnPrimary, BtnSecondary, Input } from "@/components/ui";
import { Eye, EyeOff } from "lucide-react";

function GoogleIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 48 48" aria-hidden="true">
      <path fill="#4285F4" d="M45.12 24.5c0-1.56-.14-3.06-.4-4.5H24v8.51h11.84a10.13 10.13 0 0 1-4.4 6.65v5.52h7.11c4.16-3.83 6.57-9.47 6.57-16.18z" />
      <path fill="#34A853" d="M24 46c5.94 0 10.92-1.97 14.56-5.33l-7.11-5.52c-1.97 1.32-4.49 2.1-7.45 2.1-5.73 0-10.58-3.87-12.31-9.07H4.34v5.7A21.99 21.99 0 0 0 24 46z" />
      <path fill="#FBBC05" d="M11.69 28.18a13.2 13.2 0 0 1 0-8.36v-5.7H4.34a22 22 0 0 0 0 19.76z" />
      <path fill="#EA4335" d="M24 10.75c3.23 0 6.13 1.11 8.41 3.29l6.31-6.31C34.91 4.18 29.93 2 24 2 15.4 2 7.96 6.94 4.34 14.12l7.35 5.7c1.73-5.2 6.58-9.07 12.31-9.07z" />
    </svg>
  );
}

function OutlookIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 48 48" aria-hidden="true">
      <path fill="#0364B8" d="M29 8h14a1 1 0 0 1 1 1v15H29z" />
      <path fill="#0078D4" d="M15 15a8 8 0 1 0 0 16 8 8 0 0 0 0-16zm0 13a5 5 0 1 1 0-10 5 5 0 0 1 0 10z" />
      <path fill="#0A2767" d="M4 11l20-4v34L4 37z" />
      <path fill="#fff" d="M15 16.5a6.5 6.5 0 1 0 0 13 6.5 6.5 0 0 0 0-13zm0 10.5a4 4 0 1 1 0-8 4 4 0 0 1 0 8z" />
    </svg>
  );
}

export default function LoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [verPassword, setVerPassword] = useState(false);
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

  const handleGoogle = async () => {
    setError("");
    const { error } = await supabase.auth.signInWithOAuth({
      provider: "google",
      options: { redirectTo: `${window.location.origin}/auth/callback?next=/onboarding` },
    });
    if (error) setError("No se pudo iniciar con Google. Intenta de nuevo.");
  };

  const handleOutlook = async () => {
    setError("");
    const { error } = await supabase.auth.signInWithOAuth({
      provider: "azure",
      options: {
        scopes: "openid profile email",
        redirectTo: `${window.location.origin}/auth/callback?next=/onboarding`,
      },
    });
    if (error) setError("Outlook aún no está habilitado. Usa Google o email por ahora.");
  };

  const handleRecovery = async () => {
    if (!email) { setError("Ingresa tu email primero"); return; }
    setLoading(true);
    setError("");
    // Evita que una sesión abierta de otra cuenta sea reutilizada por error
    // mientras se procesa el enlace de recuperación.
    sessionStorage.removeItem("baiyer_password_recovery");
    sessionStorage.removeItem("baiyer_password_recovery_user_id");
    await supabase.auth.signOut({ scope: "local" });
    const { error } = await supabase.auth.resetPasswordForEmail(email, {
      redirectTo: `${window.location.origin}/auth/callback?flow=recovery&next=${encodeURIComponent("/reset-password")}`,
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
      background: "var(--canvas)",
      padding: 20,
    }}>
      <div style={{
        width: "100%",
        maxWidth: 400,
        padding: 32,
        background: "var(--surface)",
        border: "1px solid var(--n-200)",
        borderRadius: "var(--r-xl)",
        boxShadow: "var(--shadow-card)",
      }}>
        {/* Marca */}
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 20 }}>
          <span style={{
            width: 30, height: 30, borderRadius: 8,
            background: "var(--brand)", color: "#fff",
            display: "inline-flex", alignItems: "center", justifyContent: "center",
            fontSize: 16, fontWeight: 700,
          }}>B</span>
          <span style={{ fontSize: 16, fontWeight: 600, color: "var(--n-900)", letterSpacing: "-0.015em" }}>Baiyer</span>
        </div>

        <h1 style={{
          fontSize: 22,
          fontWeight: 600,
          color: "var(--n-900)",
          margin: "0 0 6px",
          letterSpacing: "-0.015em",
        }}>
          {modo === "login" ? "Iniciar sesión" : "Recuperar contraseña"}
        </h1>
        <p style={{ fontSize: 14, color: "var(--n-600)", margin: "0 0 24px" }}>
          {modo === "login"
            ? "Entra a tu cuenta para seguir cotizando."
            : "Te enviamos un enlace para restablecerla."}
        </p>

        {/* Error */}
        {error && (
          <div style={{
            background: "var(--st-rechazada-bg)",
            border: "1px solid #c8623f",
            borderRadius: "var(--r-md)",
            padding: "10px 12px",
            fontSize: 13.5,
            color: "var(--danger)",
            marginBottom: 18,
          }}>
            {error}
          </div>
        )}

        {modo === "recovery" && recoveryEnviado ? (
          <div>
            <div style={{
              background: "var(--st-aprobada-bg)",
              border: "1px solid var(--success)",
              borderRadius: "var(--r-md)",
              padding: 14,
              fontSize: 13.5,
              color: "var(--st-aprobada-fg)",
              marginBottom: 20,
              lineHeight: 1.6,
            }}>
              Correo enviado a <strong>{email}</strong>. Revisa tu bandeja de entrada
              y sigue el enlace para restablecer tu contraseña.
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
                    <span style={{ fontSize: 13, fontWeight: 500, color: "var(--n-700)" }}>Contraseña</span>
                    <button
                      onClick={() => { setModo("recovery"); setError(""); }}
                      style={{
                        fontSize: 13,
                        color: "var(--brand)",
                        background: "none",
                        border: "none",
                        cursor: "pointer",
                        fontFamily: "var(--font-sans)",
                        padding: 0,
                      }}
                    >
                      Olvidé mi contraseña
                    </button>
                  </div>
                  <div style={{ position: "relative" }}>
                    <input
                      type={verPassword ? "text" : "password"}
                      value={password}
                      onChange={e => setPassword(e.target.value)}
                      onKeyDown={e => e.key === "Enter" && handleLogin()}
                      placeholder="••••••••"
                      style={{
                        width: "100%", height: 42, padding: "0 40px 0 12px",
                        background: "var(--surface)", color: "var(--n-900)",
                        border: "1px solid var(--n-300)", borderRadius: "var(--r-md)",
                        fontFamily: "var(--font-sans)", fontSize: 14, outline: "none",
                      }}
                    />
                    <button
                      type="button"
                      onClick={() => setVerPassword(v => !v)}
                      tabIndex={-1}
                      aria-label={verPassword ? "Ocultar contraseña" : "Mostrar contraseña"}
                      style={{
                        position: "absolute", right: 10, top: 0, height: 42,
                        display: "inline-flex", alignItems: "center",
                        background: "none", border: "none", cursor: "pointer",
                        color: "var(--n-500)", padding: 0,
                      }}
                    >
                      {verPassword ? <EyeOff size={17} strokeWidth={1.75} /> : <Eye size={17} strokeWidth={1.75} />}
                    </button>
                  </div>
                </div>
              )}
            </div>

            <div style={{ marginTop: 24, display: "flex", flexDirection: "column", gap: 8 }}>
              <BtnPrimary
                onClick={modo === "login" ? handleLogin : handleRecovery}
                disabled={loading}
                style={{ width: "100%" }}
              >
                {loading ? "…" : modo === "login" ? "Ingresar" : "Enviar correo de recuperación"}
              </BtnPrimary>

              {modo === "recovery" && (
                <BtnSecondary
                  onClick={() => { setModo("login"); setError(""); }}
                  style={{ width: "100%" }}
                >
                  Volver al inicio de sesión
                </BtnSecondary>
              )}
            </div>
          </>
        )}

        {modo === "login" && (
          <>
            <div style={{ display: "flex", alignItems: "center", gap: 12, margin: "20px 0" }}>
              <div style={{ flex: 1, height: 1, background: "var(--n-200)" }} />
              <span style={{ fontSize: 12.5, color: "var(--n-500)" }}>o</span>
              <div style={{ flex: 1, height: 1, background: "var(--n-200)" }} />
            </div>
            <button onClick={handleGoogle} className="btn-swiss-secondary"
              style={{ width: "100%", marginBottom: 8 }}>
              <GoogleIcon /> Continuar con Google
            </button>
            {/* Outlook oculto hasta configurar Azure AD (cuenta Microsoft de trabajo). Reactivar: false → true */}
            {false && (
              <button onClick={handleOutlook} className="btn-swiss-secondary" style={{ width: "100%" }}>
                <OutlookIcon /> Continuar con Outlook
              </button>
            )}
            <p style={{ textAlign: "center", fontSize: 13.5, color: "var(--n-600)", marginTop: 20 }}>
              ¿No tienes cuenta?{" "}
              <Link href="/register" style={{ color: "var(--brand)", textDecoration: "none", fontWeight: 500 }}>
                Regístrate gratis
              </Link>
            </p>
          </>
        )}
      </div>
    </div>
  );
}
