"use client";
import { useState, useEffect } from "react";
import { createClient } from "@/lib/supabase/client";
import { BtnPrimary, Input } from "@/components/ui";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

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
  const [confirmBaja, setConfirmBaja] = useState("");
  const [eliminando, setEliminando] = useState(false);

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

        {/* Zona de peligro — darse de baja */}
        {!loading && (
          <div style={{
            marginTop: 28,
            background: "var(--bg-surface)",
            border: "1px solid var(--border-accent)",
            padding: 24,
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
