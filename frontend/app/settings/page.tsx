"use client";
import { useState, useEffect } from "react";
import { createClient } from "@/lib/supabase/client";
import { BtnPrimary, Input } from "@/components/ui";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const CAMPOS_PERFIL = [
  { key: "empresa", label: "EMPRESA", placeholder: "Mi Empresa S.A." },
  { key: "industria", label: "INDUSTRIA / RUBRO", placeholder: "Construcción, Tecnología, etc." },
  { key: "rut", label: "RUT EMPRESA", placeholder: "76.123.456-7" },
  { key: "nombre_usuario", label: "TU NOMBRE", placeholder: "Juan Pérez" },
  { key: "pais", label: "PAÍS", placeholder: "Chile" },
  { key: "sitio_web", label: "SITIO WEB", placeholder: "https://miempresa.cl" },
  { key: "proceso_compra", label: "PROCESO DE COMPRA", placeholder: "Ej: yo cotizo y mi jefe autoriza sobre $500.000" },
  { key: "autorizador_email", label: "EMAIL DEL AUTORIZADOR", placeholder: "jefe@empresa.cl — quién aprueba tus compras" },
] as const;

type CampoKey = typeof CAMPOS_PERFIL[number]["key"];

const CAMPOS_REQUERIDOS: CampoKey[] = ["empresa", "nombre_usuario", "rut", "industria"];

export default function SettingsPage() {
  const supabase = createClient();
  const [loading, setLoading] = useState(true);
  const [guardando, setGuardando] = useState(false);
  const [toast, setToast] = useState("");
  const [confirmBaja, setConfirmBaja] = useState("");
  const [eliminando, setEliminando] = useState(false);
  const [logoUrl, setLogoUrl] = useState<string | null>(null);
  const [email, setEmail] = useState("");

  const [perfil, setPerfil] = useState<Record<CampoKey, string>>({
    empresa: "", industria: "", rut: "", nombre_usuario: "",
    pais: "", sitio_web: "", proceso_compra: "", autorizador_email: "",
  });

  const camposFaltantes = CAMPOS_REQUERIDOS.filter(k => !perfil[k]?.trim());
  const perfilCompleto = camposFaltantes.length === 0;

  useEffect(() => {
    (async () => {
      const { data: { user } } = await supabase.auth.getUser();
      if (!user) { window.location.href = "/login"; return; }
      setEmail(user.email ?? "");
      const m = user.user_metadata ?? {};
      setPerfil({
        empresa: m.empresa ?? "",
        industria: m.industria ?? "",
        rut: m.rut ?? "",
        nombre_usuario: m.nombre_usuario ?? "",
        pais: m.pais ?? "",
        sitio_web: m.sitio_web ?? "",
        proceso_compra: m.proceso_compra ?? "",
        autorizador_email: m.autorizador_email ?? "",
      });
      setLogoUrl(m.logo_url ?? null);
      setLoading(false);
    })();
  }, []);

  const setField = (key: CampoKey, val: string) =>
    setPerfil(p => ({ ...p, [key]: val }));

  const handleGuardar = async () => {
    setGuardando(true);
    const { error } = await supabase.auth.updateUser({
      data: {
        empresa: perfil.empresa.trim() || null,
        industria: perfil.industria.trim() || null,
        rut: perfil.rut.trim() || null,
        nombre_usuario: perfil.nombre_usuario.trim() || null,
        pais: perfil.pais.trim() || null,
        sitio_web: perfil.sitio_web.trim() || null,
        proceso_compra: perfil.proceso_compra.trim() || null,
        autorizador_email: perfil.autorizador_email.trim() || null,
      },
    });
    setGuardando(false);
    setToast(error ? "Error guardando configuración." : "Datos guardados");
    setTimeout(() => setToast(""), 3000);
  };

  const handleEliminar = async () => {
    setEliminando(true);
    try {
      const { data } = await supabase.auth.getSession();
      const token = data.session?.access_token;
      if (!token) throw new Error("Sesión no válida");
      const res = await fetch(`${API_URL}/api/cuenta/eliminar`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ access_token: token }),
      });
      if (!res.ok) throw new Error("No se pudo eliminar la cuenta");
      await supabase.auth.signOut();
      window.location.href = "/register";
    } catch {
      setToast("No se pudo eliminar la cuenta. Intenta de nuevo.");
      setTimeout(() => setToast(""), 3500);
      setEliminando(false);
    }
  };

  return (
    <>
      {toast && (
        <div style={{
          position: "fixed", top: 20, right: 20,
          background: "var(--bg-inverse)", padding: "10px 16px",
          fontSize: 11, color: "var(--text-inverse)", fontWeight: 700,
          zIndex: 100, fontFamily: "var(--font-mono)",
        }}>
          {toast}
        </div>
      )}

      {/* Header */}
      <div style={{ marginBottom: 28 }}>
        <div className="section-rule" style={{ marginBottom: 16 }} />
        <span style={{ fontSize: 10, fontWeight: 700, color: "var(--text-muted)", letterSpacing: "0.06em", display: "block", marginBottom: 6 }}>
          SISTEMA
        </span>
        <h1 style={{ fontSize: 26, fontWeight: 700, color: "var(--text-primary)", margin: "0 0 6px", letterSpacing: "-0.02em" }}>
          Configuración
        </h1>
        <p style={{ fontSize: 12, color: "var(--text-secondary)", margin: 0 }}>
          Datos de tu cuenta y empresa. {email && <span style={{ color: "var(--text-muted)" }}>({email})</span>}
        </p>
      </div>

      <div style={{ maxWidth: 600 }}>
        {loading ? (
          <div style={{ color: "var(--text-muted)", fontSize: 12 }}>Cargando...</div>
        ) : (
          <>
            {/* Alerta de perfil incompleto */}
            {!perfilCompleto && (
              <div style={{
                background: "var(--accent)", color: "#fff",
                padding: "10px 14px", marginBottom: 16,
                fontSize: 11, fontWeight: 700, fontFamily: "var(--font-mono)",
                letterSpacing: "0.03em",
                display: "flex", alignItems: "center", gap: 8,
              }}>
                <span style={{ fontSize: 14 }}>!</span>
                Completa tu perfil — faltan: {camposFaltantes.map(k =>
                  CAMPOS_PERFIL.find(c => c.key === k)!.label
                ).join(", ")}
              </div>
            )}

            {/* Logo + empresa header */}
            <div style={{
              background: "var(--bg-surface)", border: "1px solid var(--border-default)",
              padding: 20, marginBottom: 16,
              display: "flex", alignItems: "center", gap: 16,
            }}>
              {logoUrl ? (
                <img src={logoUrl} alt="Logo" width={56} height={56}
                  style={{ objectFit: "contain", border: "1px solid var(--border-subtle)", background: "#fff", flexShrink: 0 }}
                />
              ) : (
                <div style={{
                  width: 56, height: 56, flexShrink: 0,
                  border: "2px dashed var(--border-default)",
                  display: "flex", alignItems: "center", justifyContent: "center",
                  fontSize: 20, color: "var(--text-muted)", fontWeight: 700,
                }}>
                  {perfil.empresa ? perfil.empresa.charAt(0).toUpperCase() : "?"}
                </div>
              )}
              <div>
                <div style={{ fontSize: 17, fontWeight: 800, color: "var(--text-primary)" }}>
                  {perfil.empresa || "Sin nombre de empresa"}
                </div>
                {perfil.industria && (
                  <div className="label" style={{ color: "var(--accent)", marginTop: 2 }}>
                    {perfil.industria}{perfil.pais ? ` · ${perfil.pais}` : ""}
                  </div>
                )}
              </div>
            </div>

            {/* Formulario */}
            <div style={{
              background: "var(--bg-surface)", border: "1px solid var(--border-default)",
              padding: 24, display: "flex", flexDirection: "column", gap: 16,
            }}>
              {CAMPOS_PERFIL.map(({ key, label, placeholder }) => {
                const faltante = CAMPOS_REQUERIDOS.includes(key) && !perfil[key]?.trim();
                return (
                  <div key={key} style={{ position: "relative" }}>
                    {faltante && (
                      <div style={{
                        position: "absolute", left: -12, top: 0, bottom: 0,
                        width: 3, background: "var(--accent)",
                      }} />
                    )}
                    <Input
                      label={faltante ? `${label} *` : label}
                      value={perfil[key]}
                      onChange={e => setField(key, e.target.value)}
                      placeholder={placeholder}
                    />
                  </div>
                );
              })}

              <BtnPrimary onClick={handleGuardar} disabled={guardando} className="w-full justify-center">
                {guardando ? "Guardando..." : "Guardar"}
              </BtnPrimary>
            </div>
          </>
        )}

        {/* Zona de peligro */}
        {!loading && (
          <div style={{
            marginTop: 28, background: "var(--bg-surface)",
            border: "1px solid var(--border-accent)", padding: 24,
          }}>
            <div className="label" style={{ color: "var(--text-error)", fontWeight: 800, marginBottom: 6 }}>ZONA DE PELIGRO</div>
            <div style={{ fontSize: 14, fontWeight: 700, color: "var(--text-primary)", marginBottom: 4 }}>Darse de baja</div>
            <p style={{ fontSize: 11, color: "var(--text-secondary)", lineHeight: 1.6, marginBottom: 14 }}>
              Elimina tu cuenta y sus datos de forma permanente. Esta acción no se puede deshacer.
              Podrás volver a registrarte con el mismo correo. Para confirmar, escribe <strong>ELIMINAR</strong>.
            </p>
            <Input label="" value={confirmBaja} onChange={e => setConfirmBaja(e.target.value)} placeholder="Escribe ELIMINAR" />
            <button
              onClick={handleEliminar}
              disabled={confirmBaja.trim().toUpperCase() !== "ELIMINAR" || eliminando}
              style={{
                marginTop: 12, width: "100%", padding: "10px 12px", fontSize: 12, fontWeight: 700,
                fontFamily: "var(--font-mono)",
                cursor: confirmBaja.trim().toUpperCase() === "ELIMINAR" && !eliminando ? "pointer" : "not-allowed",
                background: confirmBaja.trim().toUpperCase() === "ELIMINAR" ? "var(--accent)" : "var(--bg-base)",
                color: confirmBaja.trim().toUpperCase() === "ELIMINAR" ? "#fff" : "var(--text-muted)",
                border: "1px solid var(--border-accent)",
              }}
            >
              {eliminando ? "Eliminando cuenta..." : "Eliminar mi cuenta permanentemente"}
            </button>
          </div>
        )}
      </div>
    </>
  );
}
