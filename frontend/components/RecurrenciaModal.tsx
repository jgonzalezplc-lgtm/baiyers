"use client";
import { useState, useEffect } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface Proveedor {
  id: string;
  nombre: string;
}

interface RecurrenciaData {
  id?: string;
  nombre: string;
  items: string;
  frecuencia: string;
  dia_ejecucion?: number | null;
  proveedor_id?: string | null;
  cotizar_antes: boolean;
  monto_maximo?: number | null;
  dias_aviso: number;
}

interface Props {
  userId: string;
  recurrencia?: RecurrenciaData | null;
  onGuardado: () => void;
  onCerrar: () => void;
}

const FRECUENCIAS = [
  { val: "diaria", label: "Diaria" },
  { val: "semanal", label: "Semanal" },
  { val: "mensual", label: "Mensual" },
  { val: "bimestral", label: "Bimestral (cada 2 meses)" },
  { val: "trimestral", label: "Trimestral (cada 3 meses)" },
  { val: "anual", label: "Anual" },
];

export default function RecurrenciaModal({ userId, recurrencia, onGuardado, onCerrar }: Props) {
  const [nombre, setNombre] = useState(recurrencia?.nombre ?? "");
  const [items, setItems] = useState(recurrencia?.items ?? "");
  const [frecuencia, setFrecuencia] = useState(recurrencia?.frecuencia ?? "mensual");
  const [diaEjecucion, setDiaEjecucion] = useState<string>(String(recurrencia?.dia_ejecucion ?? "1"));
  const [proveedorId, setProveedorId] = useState<string>(recurrencia?.proveedor_id ?? "");
  const [cotizarAntes, setCotizarAntes] = useState(recurrencia?.cotizar_antes ?? true);
  const [montoMaximo, setMontoMaximo] = useState<string>(String(recurrencia?.monto_maximo ?? ""));
  const [diasAviso, setDiasAviso] = useState<string>(String(recurrencia?.dias_aviso ?? 3));
  const [proveedores, setProveedores] = useState<Proveedor[]>([]);
  const [guardando, setGuardando] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    fetch(`${API_URL}/api/suppliers?user_id=${userId}`)
      .then(r => r.json())
      .then(data => setProveedores(data))
      .catch(() => {});
  }, [userId]);

  const handleGuardar = async () => {
    if (!nombre.trim()) { setError("El nombre es requerido"); return; }
    if (!items.trim()) { setError("Los items son requeridos"); return; }

    setGuardando(true);
    setError("");

    const payload = {
      user_id: userId,
      nombre: nombre.trim(),
      items: items.trim(),
      frecuencia,
      dia_ejecucion: diaEjecucion ? parseInt(diaEjecucion) : null,
      proveedor_id: proveedorId || null,
      cotizar_antes: cotizarAntes,
      monto_maximo: montoMaximo ? parseFloat(montoMaximo) : null,
      dias_aviso: parseInt(diasAviso) || 3,
    };

    try {
      const url = recurrencia?.id
        ? `${API_URL}/api/recurrencias/${recurrencia.id}`
        : `${API_URL}/api/recurrencias`;
      const method = recurrencia?.id ? "PUT" : "POST";

      const res = await fetch(url, {
        method,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!res.ok) throw new Error(await res.text());
      onGuardado();
    } catch {
      setError("Error guardando la recurrencia. Intenta de nuevo.");
    } finally {
      setGuardando(false);
    }
  };

  const inputStyle: React.CSSProperties = {
    width: "100%",
    padding: "10px 12px",
    background: "var(--bg-base)",
    border: "1px solid var(--border-default)",
    color: "var(--text-primary)",
    fontSize: 11,
    outline: "none",
    fontFamily: "var(--font-mono)",
    boxSizing: "border-box",
  };

  return (
    <div style={{
      position: "fixed", inset: 0,
      background: "rgba(0,0,0,0.6)",
      display: "flex", alignItems: "center", justifyContent: "center",
      zIndex: 1000, padding: 16,
    }}>
      <div style={{
        width: "100%", maxWidth: 500,
        background: "var(--bg-surface)",
        border: "1px solid var(--border-default)",
        overflow: "hidden",
        maxHeight: "90vh",
        overflowY: "auto",
      }}>

        <div style={{
          padding: "16px 20px",
          borderBottom: "1px solid var(--border-default)",
          display: "flex", justifyContent: "space-between", alignItems: "center",
          position: "sticky", top: 0,
          background: "var(--bg-surface)",
          zIndex: 1,
        }}>
          <div>
            <span className="label" style={{ color: "var(--accent)", display: "block", marginBottom: 2 }}>
              Compras Recurrentes
            </span>
            <h2 style={{ fontSize: 15, fontWeight: 700, color: "var(--text-primary)", margin: 0, letterSpacing: "-0.01em" }}>
              {recurrencia?.id ? "Editar recurrencia" : "Nueva recurrencia"}
            </h2>
          </div>
          <button onClick={onCerrar} style={{ background: "none", border: "none", color: "var(--text-muted)", cursor: "pointer", fontSize: 18 }}>✕</button>
        </div>

        <div style={{ padding: 20, display: "flex", flexDirection: "column", gap: 16 }}>

          <div>
            <label className="label" style={{ color: "var(--text-muted)", display: "block", marginBottom: 6 }}>
              Nombre descriptivo
            </label>
            <input value={nombre} onChange={e => setNombre(e.target.value)} placeholder="Ej: Papel higienico mensual" style={inputStyle} />
          </div>

          <div>
            <label className="label" style={{ color: "var(--text-muted)", display: "block", marginBottom: 6 }}>
              Items (uno por linea)
            </label>
            <textarea
              value={items}
              onChange={e => setItems(e.target.value)}
              rows={3}
              placeholder={"Papel higienico doble hoja x 48\nToalla de papel x 12"}
              style={{ ...inputStyle, resize: "none" }}
            />
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
            <div>
              <label className="label" style={{ color: "var(--text-muted)", display: "block", marginBottom: 6 }}>Frecuencia</label>
              <select value={frecuencia} onChange={e => setFrecuencia(e.target.value)} style={{ ...inputStyle, cursor: "pointer" }}>
                {FRECUENCIAS.map(f => <option key={f.val} value={f.val}>{f.label}</option>)}
              </select>
            </div>
            {["mensual","bimestral","trimestral","anual"].includes(frecuencia) && (
              <div>
                <label className="label" style={{ color: "var(--text-muted)", display: "block", marginBottom: 6 }}>Dia del mes</label>
                <input type="number" min={1} max={28} value={diaEjecucion} onChange={e => setDiaEjecucion(e.target.value)} style={inputStyle} />
              </div>
            )}
          </div>

          <div>
            <label className="label" style={{ color: "var(--text-muted)", display: "block", marginBottom: 6 }}>
              Proveedor preferido (opcional)
            </label>
            <select value={proveedorId} onChange={e => setProveedorId(e.target.value)} style={{ ...inputStyle, cursor: "pointer" }}>
              <option value="">— Sin asignar —</option>
              {proveedores.map(p => <option key={p.id} value={p.id}>{p.nombre}</option>)}
            </select>
          </div>

          {/* Toggle cotizar antes */}
          <div style={{
            background: "var(--bg-base)",
            border: "1px solid var(--border-default)",
            padding: "12px 16px",
            display: "flex", justifyContent: "space-between", alignItems: "center",
          }}>
            <div>
              <div style={{ fontSize: 11, color: "var(--text-primary)", fontWeight: 600 }}>Cotizar antes de emitir OC?</div>
              <div className="label" style={{ color: "var(--text-muted)", marginTop: 2 }}>
                {cotizarAntes ? "Envia solicitud de cotizacion al proveedor" : "Emite OC directamente con ultimo precio conocido"}
              </div>
            </div>
            <button
              onClick={() => setCotizarAntes(!cotizarAntes)}
              style={{
                width: 40, height: 22,
                border: "none",
                cursor: "pointer",
                background: cotizarAntes ? "var(--accent)" : "var(--border-default)",
                position: "relative",
                flexShrink: 0,
              }}
            >
              <span style={{
                position: "absolute",
                top: 3,
                left: cotizarAntes ? 21 : 3,
                width: 16,
                height: 16,
                background: "#fff",
                transition: "left 0.2s",
              }} />
            </button>
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
            <div>
              <label className="label" style={{ color: "var(--text-muted)", display: "block", marginBottom: 6 }}>
                Monto max. autorizado (opcional)
              </label>
              <input type="number" value={montoMaximo} onChange={e => setMontoMaximo(e.target.value)} placeholder="Sin limite" style={inputStyle} />
            </div>
            <div>
              <label className="label" style={{ color: "var(--text-muted)", display: "block", marginBottom: 6 }}>Avisar X dias antes</label>
              <input type="number" min={0} max={30} value={diasAviso} onChange={e => setDiasAviso(e.target.value)} style={inputStyle} />
            </div>
          </div>

          {error && (
            <div style={{
              fontSize: 11,
              color: "var(--text-error)",
              background: "var(--fill-error)",
              border: "1px solid var(--border-accent)",
              padding: "8px 12px",
            }}>{error}</div>
          )}

          <div style={{ display: "flex", gap: 8 }}>
            <button onClick={onCerrar} className="btn-swiss-secondary" style={{ flex: 1 }}>Cancelar</button>
            <button onClick={handleGuardar} disabled={guardando} className="btn-swiss-primary" style={{ flex: 2 }}>
              {guardando ? "Guardando..." : recurrencia?.id ? "Actualizar" : "Crear recurrencia"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
