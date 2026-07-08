"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { createClient } from "@/lib/supabase/client";
import Link from "next/link";
import { BtnPrimary, Input } from "@/components/ui";

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
      router.push("/dashboard");
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
