"use client";
import { useState, useEffect } from "react";
import { createClient } from "@/lib/supabase/client";
import { BtnPrimary, Input } from "@/components/ui";

export default function SettingsPage() {
  const supabase = createClient();
  const [userId, setUserId] = useState("");
  const [empresa, setEmpresa] = useState("");
  const [rut, setRut] = useState("");
  const [direccion, setDireccion] = useState("");
  const [telefono, setTelefono] = useState("");
  const [loading, setLoading] = useState(true);
  const [guardando, setGuardando] = useState(false);
  const [toast, setToast] = useState("");

  useEffect(() => {
    (async () => {
      const { data: { user } } = await supabase.auth.getUser();
      if (!user) { window.location.href = "/login"; return; }
      setUserId(user.id);

      const { data } = await supabase.from("user_settings").select("*").eq("user_id", user.id).single();
      if (data) {
        setEmpresa(data.empresa || "");
        setRut(data.rut || "");
        setDireccion(data.direccion || "");
        setTelefono(data.telefono || "");
      }
      setLoading(false);
    })();
  }, []);

  const handleGuardar = async () => {
    setGuardando(true);
    const { error } = await supabase.from("user_settings").upsert({
      user_id: userId,
      empresa,
      rut,
      direccion,
      telefono,
      updated_at: new Date().toISOString(),
    });
    setGuardando(false);
    setToast(error ? "Error guardando. Verifica que la tabla user_settings existe." : "Datos guardados");
    setTimeout(() => setToast(""), 3000);
  };

  return (
    <>
      {toast && (
        <div style={{
          position: "fixed",
          top: 20,
          right: 20,
          background: "var(--bg-inverse)",
          padding: "10px 16px",
          fontSize: 11,
          color: "var(--text-inverse)",
          fontWeight: 700,
          zIndex: 100,
          fontFamily: "var(--font-mono)",
        }}>
          {toast}
        </div>
      )}

      {/* Page header */}
      <div style={{ marginBottom: 28 }}>
        <div className="section-rule" style={{ marginBottom: 16 }} />
        <span style={{ fontSize: 10, fontWeight: 700, color: "var(--text-muted)", letterSpacing: "0.06em", display: "block", marginBottom: 6 }}>
          SISTEMA
        </span>
        <h1 style={{ fontSize: 26, fontWeight: 700, color: "var(--text-primary)", margin: "0 0 6px", letterSpacing: "-0.02em" }}>
          Configuración
        </h1>
        <p style={{ fontSize: 12, color: "var(--text-secondary)", margin: 0 }}>Configuración de tu cuenta y empresa.</p>
      </div>

      <div style={{ maxWidth: 600 }}>
        {loading ? (
          <div style={{ color: "var(--text-muted)", fontSize: 12 }}>Cargando...</div>
        ) : (
          <div style={{
            background: "var(--bg-surface)",
            border: "1px solid var(--border-default)",
            padding: 24,
            display: "flex",
            flexDirection: "column",
            gap: 16,
          }}>
            <Input label="Nombre empresa" value={empresa} onChange={e => setEmpresa(e.target.value)} placeholder="Mi Empresa S.A." />
            <Input label="RUT empresa" value={rut} onChange={e => setRut(e.target.value)} placeholder="76.123.456-7" />
            <Input label="Direccion" value={direccion} onChange={e => setDireccion(e.target.value)} placeholder="Av. Ejemplo 1234, Santiago" />
            <Input label="Telefono" value={telefono} onChange={e => setTelefono(e.target.value)} placeholder="+56 9 1234 5678" />

            <BtnPrimary onClick={handleGuardar} disabled={guardando} className="w-full justify-center">
              {guardando ? "Guardando..." : "Guardar"}
            </BtnPrimary>
          </div>
        )}
      </div>
    </>
  );
}
