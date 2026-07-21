"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { createClient } from "@/lib/supabase/client";
import Link from "next/link";
import { BtnPrimary, Input } from "@/components/ui";

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

export default function RegisterPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [empresa, setEmpresa] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const router = useRouter();
  const supabase = createClient();

  const handleRegister = async () => {
    if (!email || !password || !empresa) {
      setError("Completa todos los campos");
      return;
    }
    setLoading(true);
    setError("");

    const { error } = await supabase.auth.signUp({
      email,
      password,
      options: { data: { empresa, plan: "free" } },
    });

    if (error) {
      setError(error.message);
      setLoading(false);
    } else {
      router.push("/onboarding");
    }
  };

  const handleGoogle = async () => {
    setError("");
    const { error } = await supabase.auth.signInWithOAuth({
      provider: "google",
      options: { redirectTo: `${window.location.origin}/auth/callback?next=/onboarding` },
    });
    if (error) setError("No se pudo continuar con Google. Intenta de nuevo.");
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
        <h1 style={{ fontSize: 20, fontWeight: 700, color: "var(--text-primary)", margin: "0 0 4px", letterSpacing: "-0.02em" }}>
          Crear cuenta
        </h1>
        <p style={{ fontSize: 11, color: "var(--text-muted)", marginBottom: 24 }}>
          Plan Free permanente. Sin tarjeta de credito.
        </p>

        <div style={{
          background: "var(--bg-base)",
          border: "1px solid var(--border-default)",
          padding: "8px 12px",
          marginBottom: 20,
        }}>
          <span className="label" style={{ color: "var(--text-muted)" }}>
            Free: 3 cotizaciones/mes · Upgrade cuando quieras
          </span>
        </div>

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

        <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          <Input
            label="Nombre de empresa"
            type="text"
            value={empresa}
            onChange={e => setEmpresa(e.target.value)}
            placeholder="Empresa SpA"
          />
          <Input
            label="Email corporativo"
            type="email"
            value={email}
            onChange={e => setEmail(e.target.value)}
            placeholder="tu@empresa.cl"
          />
          <Input
            label="Contrasena"
            type="password"
            value={password}
            onChange={e => setPassword(e.target.value)}
            placeholder="Minimo 8 caracteres"
          />
        </div>

        <BtnPrimary
          onClick={handleRegister}
          disabled={loading}
          className="w-full justify-center"
          style={{ marginTop: 20 }}
        >
          {loading ? "Creando cuenta..." : "Crear cuenta gratis"}
        </BtnPrimary>

        <div style={{ display: "flex", alignItems: "center", gap: 12, margin: "18px 0" }}>
          <div style={{ flex: 1, height: 1, background: "var(--border-default)" }} />
          <span className="label" style={{ color: "var(--text-muted)" }}>o</span>
          <div style={{ flex: 1, height: 1, background: "var(--border-default)" }} />
        </div>
        <button onClick={handleGoogle} className="btn-swiss-secondary"
          style={{ width: "100%", display: "flex", alignItems: "center", justifyContent: "center", gap: 8, padding: 12 }}>
          <GoogleIcon /> Continuar con Google
        </button>

        <p style={{ textAlign: "center", fontSize: 11, color: "var(--text-muted)", marginTop: 16 }}>
          Ya tienes cuenta?{" "}
          <Link href="/login" style={{ color: "var(--accent)", textDecoration: "none" }}>
            Inicia sesion
          </Link>
        </p>
      </div>
    </div>
  );
}
