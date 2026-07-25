"use client";
import { useState, useEffect } from "react";
import { createClient } from "@/lib/supabase/client";
import { AlertCircle } from "lucide-react";
import { BtnPrimary, Input, PageHeader, Card, Spinner } from "@/components/ui";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const CAMPOS_PERFIL = [
  { key: "empresa", label: "Empresa", placeholder: "Mi Empresa S.A." },
  { key: "industria", label: "Industria / rubro", placeholder: "Construcción, Tecnología, etc." },
  { key: "rut", label: "RUT empresa", placeholder: "76.123.456-7" },
  { key: "nombre_usuario", label: "Tu nombre", placeholder: "Juan Pérez" },
  { key: "pais", label: "País", placeholder: "Chile" },
  { key: "sitio_web", label: "Sitio web", placeholder: "https://miempresa.cl" },
  { key: "proceso_compra", label: "Proceso de compra", placeholder: "Ej: yo cotizo y mi jefe autoriza sobre $500.000" },
  { key: "autorizador_email", label: "Email del autorizador", placeholder: "jefe@empresa.cl — quién aprueba tus compras" },
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
          background: "var(--n-900)", color: "var(--canvas)",
          padding: "11px 16px", borderRadius: "var(--r-md)",
          fontSize: 13.5, fontWeight: 500,
          zIndex: 100, boxShadow: "var(--shadow-pop)",
        }}>
          {toast}
        </div>
      )}

      <PageHeader
        title="Configuración"
        subtitle={`Datos de tu cuenta y empresa.${email ? ` (${email})` : ""}`}
      />

      <div style={{ maxWidth: 620 }}>
        {loading ? (
          <Spinner />
        ) : (
          <>
            {/* Alerta de perfil incompleto */}
            {!perfilCompleto && (
              <div style={{
                background: "var(--st-cotizando-bg)", color: "var(--st-cotizando-fg)",
                border: "1px solid rgba(124,92,18,.25)", borderRadius: "var(--r-md)",
                padding: "12px 14px", marginBottom: 16,
                fontSize: 13.5, fontWeight: 500,
                display: "flex", alignItems: "flex-start", gap: 10,
              }}>
                <AlertCircle size={17} strokeWidth={1.75} style={{ flexShrink: 0, marginTop: 1 }} />
                <span>
                  Completa tu perfil — faltan:{" "}
                  <strong>{camposFaltantes.map(k => CAMPOS_PERFIL.find(c => c.key === k)!.label).join(", ")}</strong>
                </span>
              </div>
            )}

            {/* Logo + empresa */}
            <Card style={{ marginBottom: 16, display: "flex", alignItems: "center", gap: 16 }} padding={20}>
              {logoUrl ? (
                <img src={logoUrl} alt="Logo" width={56} height={56}
                  style={{ objectFit: "contain", borderRadius: "var(--r-md)", border: "1px solid var(--n-200)", background: "#fff", flexShrink: 0 }}
                />
              ) : (
                <div style={{
                  width: 56, height: 56, flexShrink: 0, borderRadius: "var(--r-md)",
                  background: "var(--brand-50)", color: "var(--brand)",
                  display: "flex", alignItems: "center", justifyContent: "center",
                  fontSize: 22, fontWeight: 600,
                }}>
                  {perfil.empresa ? perfil.empresa.charAt(0).toUpperCase() : "?"}
                </div>
              )}
              <div>
                <div style={{ fontSize: 17, fontWeight: 600, color: "var(--n-900)" }}>
                  {perfil.empresa || "Sin nombre de empresa"}
                </div>
                {perfil.industria && (
                  <div style={{ fontSize: 13.5, color: "var(--n-600)", marginTop: 2 }}>
                    {perfil.industria}{perfil.pais ? ` · ${perfil.pais}` : ""}
                  </div>
                )}
              </div>
            </Card>

            {/* Formulario */}
            <Card padding={24} style={{ display: "flex", flexDirection: "column", gap: 16 }}>
              {CAMPOS_PERFIL.map(({ key, label, placeholder }) => {
                const faltante = CAMPOS_REQUERIDOS.includes(key) && !perfil[key]?.trim();
                return (
                  <Input
                    key={key}
                    label={faltante ? `${label} · requerido` : label}
                    value={perfil[key]}
                    onChange={e => setField(key, e.target.value)}
                    placeholder={placeholder}
                  />
                );
              })}

              <BtnPrimary onClick={handleGuardar} disabled={guardando} style={{ width: "100%" }}>
                {guardando ? "Guardando…" : "Guardar cambios"}
              </BtnPrimary>
            </Card>
          </>
        )}

        {/* Zona de peligro */}
        {!loading && (() => {
          const confirmado = confirmBaja.trim().toUpperCase() === "ELIMINAR";
          return (
            <div style={{
              marginTop: 28, background: "var(--surface)",
              border: "1px solid rgba(154,63,40,.3)", borderRadius: "var(--r-lg)", padding: 24,
            }}>
              <div style={{ fontSize: 13, fontWeight: 600, color: "var(--danger)", marginBottom: 6 }}>Zona de peligro</div>
              <div style={{ fontSize: 16, fontWeight: 600, color: "var(--n-900)", marginBottom: 4 }}>Darse de baja</div>
              <p style={{ fontSize: 13.5, color: "var(--n-600)", lineHeight: 1.6, marginBottom: 14 }}>
                Elimina tu cuenta y sus datos de forma permanente. Esta acción no se puede deshacer.
                Podrás volver a registrarte con el mismo correo. Para confirmar, escribe <strong>ELIMINAR</strong>.
              </p>
              <Input value={confirmBaja} onChange={e => setConfirmBaja(e.target.value)} placeholder="Escribe ELIMINAR" />
              <button
                onClick={handleEliminar}
                disabled={!confirmado || eliminando}
                style={{
                  marginTop: 12, width: "100%", padding: "10px 16px",
                  fontSize: 14, fontWeight: 600, fontFamily: "var(--font-sans)",
                  borderRadius: "var(--r-md)",
                  cursor: confirmado && !eliminando ? "pointer" : "not-allowed",
                  background: confirmado ? "var(--danger)" : "var(--surface-2)",
                  color: confirmado ? "#fff" : "var(--n-500)",
                  border: `1px solid ${confirmado ? "var(--danger)" : "var(--n-300)"}`,
                }}
              >
                {eliminando ? "Eliminando cuenta…" : "Eliminar mi cuenta permanentemente"}
              </button>
            </div>
          );
        })()}
      </div>
    </>
  );
}
