"use client";
import { useState, useRef } from "react";
import { useRouter } from "next/navigation";
import { createClient } from "@/lib/supabase/client";
import Link from "next/link";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface ItemParsed {
  item: string;
  descripcion: string | null;
  cantidad: number;
  unidad: string;
  categoria: string | null;
}

const inputStyle = {
  width: "100%",
  padding: "9px 12px",
  background: "var(--bg-base)",
  border: "1px solid var(--border-default)",
  color: "var(--text-primary)",
  fontSize: 12,
  outline: "none",
  fontFamily: "var(--font-mono)",
  boxSizing: "border-box" as const,
};

const labelStyle = {
  display: "block" as const,
  fontSize: 9,
  color: "var(--text-muted)",
  textTransform: "uppercase" as const,
  letterSpacing: "0.1em",
  fontWeight: 700,
  marginBottom: 6,
};

export default function NuevoProyectoPage() {
  const router = useRouter();
  const [paso, setPaso] = useState(1);
  const [userId, setUserId] = useState<string | null>(null);

  const [nombre, setNombre] = useState("");
  const [cliente, setCliente] = useState("");
  const [fechaInicio, setFechaInicio] = useState(new Date().toISOString().slice(0, 10));
  const [descripcion, setDescripcion] = useState("");

  const [archivo, setArchivo] = useState<File | null>(null);
  const [arrastrando, setArrastrando] = useState(false);
  const [parseando, setParseando] = useState(false);
  const [items, setItems] = useState<ItemParsed[]>([]);
  const inputRef = useRef<HTMLInputElement>(null);

  const [proyectoId, setProyectoId] = useState<string | null>(null);
  const [cotizando, setCotizando] = useState(false);
  const [progreso, setProgreso] = useState({ completados: 0, total: 0, terminado: false });

  const [guardando, setGuardando] = useState(false);
  const [error, setError] = useState("");

  useState(() => {
    createClient().auth.getUser().then(({ data }) => setUserId(data.user?.id ?? null));
  });

  const handleParsear = async (file: File) => {
    setArchivo(file);
    setParseando(true);
    setError("");
    try {
      const form = new FormData();
      form.append("file", file);
      const res = await fetch(`${API_URL}/api/proyectos/parsear-cubicacion`, { method: "POST", body: form });
      if (!res.ok) throw new Error("Error parseando");
      const data = await res.json();
      setItems(data.items);
    } catch {
      setError("Error analizando el archivo. Verifica que sea un Excel o CSV válido.");
    } finally {
      setParseando(false);
    }
  };

  const handleCrearProyecto = async () => {
    if (!userId || !nombre.trim()) return;
    setGuardando(true);
    setError("");
    try {
      const res = await fetch(`${API_URL}/api/proyectos`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user_id: userId, nombre, cliente: cliente || null, fecha_inicio: fechaInicio, descripcion: descripcion || null }),
      });
      if (!res.ok) throw new Error("Error creando proyecto");
      const proy = await res.json();
      setProyectoId(proy.id);

      if (items.length > 0) {
        await fetch(`${API_URL}/api/proyectos/${proy.id}/items?user_id=${userId}`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(items.map((it, i) => ({ ...it, orden: i }))),
        });
      }
      setPaso(3);
    } catch {
      setError("Error creando el proyecto. Intenta de nuevo.");
    } finally {
      setGuardando(false);
    }
  };

  const handleCotizar = async () => {
    if (!proyectoId || !userId) return;
    setCotizando(true);
    try {
      await fetch(`${API_URL}/api/proyectos/${proyectoId}/cotizar?user_id=${userId}`, { method: "POST" });
      const poll = setInterval(async () => {
        const res = await fetch(`${API_URL}/api/proyectos/${proyectoId}/cotizar/progreso`);
        const data = await res.json();
        setProgreso(data);
        if (data.terminado) { clearInterval(poll); setCotizando(false); }
      }, 1500);
    } catch {
      setError("Error iniciando la cotización.");
      setCotizando(false);
    }
  };

  const pct = progreso.total > 0 ? Math.round((progreso.completados / progreso.total) * 100) : 0;

  const PASOS = ["Info", "Cubicación", "Cotizar"];

  return (
    <>
      {/* Header */}
      <div style={{ marginBottom: 28 }}>
        <div className="section-rule" style={{ marginBottom: 16 }} />
        <span style={{ fontSize: 10, fontWeight: 700, color: "var(--text-muted)", letterSpacing: "0.06em", display: "block", marginBottom: 6 }}>
          NUEVO PROYECTO
        </span>
        <h1 style={{ fontSize: 26, fontWeight: 700, color: "var(--text-primary)", margin: "0 0 6px", letterSpacing: "-0.02em" }}>
          {paso === 1 ? "Información básica" : paso === 2 ? "Cubicación de materiales" : "Cotización automática"}
        </h1>
      </div>

      <div style={{ maxWidth: 680 }}>
        {/* Steps indicator */}
        <div style={{ display: "flex", gap: 0, marginBottom: 32 }}>
          {PASOS.map((s, i) => (
            <div key={s} style={{ display: "flex", alignItems: "center", flex: 1 }}>
              <div style={{
                width: 22,
                height: 22,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                fontSize: 10,
                fontWeight: 700,
                background: paso > i + 1 ? "var(--text-success)" : paso === i + 1 ? "var(--accent)" : "var(--bg-surface)",
                border: `1px solid ${paso > i + 1 ? "var(--text-success)" : paso === i + 1 ? "var(--accent)" : "var(--border-default)"}`,
                color: paso >= i + 1 ? "#fff" : "var(--text-muted)",
                flexShrink: 0,
              }}>
                {paso > i + 1 ? "✓" : i + 1}
              </div>
              <span style={{ fontSize: 10, fontWeight: paso === i + 1 ? 700 : 400, color: paso === i + 1 ? "var(--text-primary)" : "var(--text-muted)", marginLeft: 6, marginRight: 12 }}>{s}</span>
              {i < 2 && <div style={{ flex: 1, height: 1, background: paso > i + 1 ? "var(--accent)" : "var(--border-default)" }} />}
            </div>
          ))}
        </div>

        {error && (
          <div style={{
            background: "var(--accent-muted)",
            border: "1px solid var(--border-accent)",
            padding: "10px 14px",
            fontSize: 11,
            color: "var(--text-error)",
            marginBottom: 20,
          }}>{error}</div>
        )}

        {/* PASO 1 */}
        {paso === 1 && (
          <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
            <div>
              <label style={labelStyle}>Nombre del proyecto *</label>
              <input value={nombre} onChange={e => setNombre(e.target.value)} placeholder="Ej: Construcción Edificio Providencia" style={inputStyle} />
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
              <div>
                <label style={labelStyle}>Cliente</label>
                <input value={cliente} onChange={e => setCliente(e.target.value)} placeholder="Nombre del cliente" style={inputStyle} />
              </div>
              <div>
                <label style={labelStyle}>Fecha inicio estimada</label>
                <input type="date" value={fechaInicio} onChange={e => setFechaInicio(e.target.value)} style={inputStyle} />
              </div>
            </div>
            <div>
              <label style={labelStyle}>Descripción opcional</label>
              <textarea value={descripcion} onChange={e => setDescripcion(e.target.value)} rows={3} style={{ ...inputStyle, resize: "none" }} placeholder="Descripción del proyecto..." />
            </div>
            <button
              onClick={() => { if (!nombre.trim()) { setError("El nombre es requerido"); return; } setError(""); setPaso(2); }}
              className="btn-swiss-primary"
              style={{ padding: "12px 20px", fontSize: 11, cursor: "pointer" }}
            >
              Siguiente →
            </button>
          </div>
        )}

        {/* PASO 2 */}
        {paso === 2 && (
          <div>
            <div
              onDragOver={e => { e.preventDefault(); setArrastrando(true); }}
              onDragLeave={() => setArrastrando(false)}
              onDrop={e => { e.preventDefault(); setArrastrando(false); const f = e.dataTransfer.files[0]; if (f) handleParsear(f); }}
              onClick={() => inputRef.current?.click()}
              style={{
                border: `2px dashed ${arrastrando ? "var(--accent)" : archivo ? "var(--text-success)" : "var(--border-default)"}`,
                padding: "32px 20px",
                textAlign: "center",
                cursor: "pointer",
                background: "var(--bg-surface)",
                marginBottom: 20,
              }}
            >
              <input ref={inputRef} type="file" accept=".xlsx,.xls,.csv" style={{ display: "none" }} onChange={e => e.target.files?.[0] && handleParsear(e.target.files[0])} />
              <div style={{ fontSize: 11, fontWeight: 700, color: "var(--text-primary)", marginBottom: 4 }}>
                {parseando ? "Analizando con Gemini..." : archivo ? archivo.name : "Arrastra una cubicación Excel o CSV"}
              </div>
              <div style={{ fontSize: 11, color: "var(--text-muted)" }}>
                {parseando ? "Detectando ítems, cantidades y unidades..." : "Gemini detecta columnas automáticamente · .xlsx, .xls, .csv"}
              </div>
            </div>

            {items.length > 0 && (
              <div style={{ marginBottom: 20 }}>
                <div style={{ fontSize: 10, fontWeight: 700, color: "var(--text-success)", letterSpacing: "0.05em", marginBottom: 10 }}>
                  {items.length} ÍTEMS DETECTADOS — puedes editar antes de confirmar
                </div>
                <div style={{ border: "1px solid var(--border-default)", background: "var(--bg-surface)", maxHeight: 320, overflowY: "auto" }}>
                  <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 11 }}>
                    <thead>
                      <tr style={{ background: "var(--bg-base)", borderBottom: "1px solid var(--border-default)" }}>
                        {["Ítem", "Descripción", "Cant.", "Unidad", "Categoría"].map(h => (
                          <th key={h} style={{ padding: "8px 10px", textAlign: "left", fontSize: 9, fontWeight: 700, color: "var(--text-muted)", letterSpacing: "0.06em" }}>{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {items.map((it, i) => (
                        <tr key={i} style={{ borderBottom: i < items.length - 1 ? "1px solid var(--border-subtle)" : "none" }}>
                          <td style={{ padding: "7px 10px" }}>
                            <input value={it.item} onChange={e => setItems(prev => prev.map((x, j) => j === i ? { ...x, item: e.target.value } : x))} style={{ background: "none", border: "none", color: "var(--text-primary)", fontSize: 11, outline: "none", width: "100%", fontFamily: "inherit" }} />
                          </td>
                          <td style={{ padding: "7px 10px", color: "var(--text-muted)", maxWidth: 140, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{it.descripcion || "—"}</td>
                          <td style={{ padding: "7px 10px" }}>
                            <input type="number" value={it.cantidad} onChange={e => setItems(prev => prev.map((x, j) => j === i ? { ...x, cantidad: parseFloat(e.target.value) || 1 } : x))} style={{ background: "none", border: "none", color: "var(--text-primary)", fontSize: 11, outline: "none", width: 55, fontFamily: "inherit" }} />
                          </td>
                          <td style={{ padding: "7px 10px", color: "var(--text-secondary)" }}>{it.unidad}</td>
                          <td style={{ padding: "7px 10px", color: "var(--accent)" }}>{it.categoria || "—"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            <div style={{ display: "flex", gap: 8 }}>
              <button onClick={() => setPaso(1)} className="btn-swiss-secondary" style={{ padding: "10px 18px", fontSize: 11, cursor: "pointer" }}>← Atrás</button>
              <button
                onClick={handleCrearProyecto}
                disabled={guardando || items.length === 0}
                className="btn-swiss-primary"
                style={{ flex: 1, padding: "10px 18px", fontSize: 11, cursor: guardando || items.length === 0 ? "not-allowed" : "pointer", opacity: items.length === 0 ? 0.5 : 1 }}
              >
                {guardando ? "Creando proyecto..." : `Confirmar ${items.length} ítems →`}
              </button>
            </div>
          </div>
        )}

        {/* PASO 3 */}
        {paso === 3 && (
          <div style={{ textAlign: "center", padding: "40px 20px" }}>
            {!cotizando && !progreso.terminado && (
              <>
                <div className="section-rule" style={{ margin: "0 auto 24px" }} />
                <div style={{ fontSize: 14, fontWeight: 700, color: "var(--text-primary)", marginBottom: 8 }}>
                  Proyecto creado con {items.length} ítems
                </div>
                <div style={{ fontSize: 11, color: "var(--text-secondary)", marginBottom: 28, lineHeight: 1.6 }}>
                  Claria buscará el mejor precio para cada ítem en proveedores disponibles en paralelo.
                </div>
                <button onClick={handleCotizar} className="btn-swiss-primary" style={{ padding: "12px 32px", fontSize: 12, cursor: "pointer" }}>
                  Iniciar cotización automática
                </button>
              </>
            )}

            {(cotizando || (progreso.total > 0 && !progreso.terminado)) && (
              <>
                <div style={{ fontSize: 13, fontWeight: 700, color: "var(--text-primary)", marginBottom: 20 }}>
                  Cotizando {progreso.completados} / {progreso.total} ítems...
                </div>
                <div style={{ background: "var(--border-default)", height: 6, marginBottom: 12, overflow: "hidden" }}>
                  <div style={{ height: "100%", background: "var(--accent)", width: `${pct}%`, transition: "width 0.5s" }} />
                </div>
                <div style={{ fontSize: 11, color: "var(--text-muted)" }}>{pct}% completado</div>
              </>
            )}

            {progreso.terminado && (
              <>
                <div className="section-rule" style={{ margin: "0 auto 24px" }} />
                <div style={{ fontSize: 14, fontWeight: 700, color: "var(--text-success)", marginBottom: 8 }}>Cotización completada</div>
                <div style={{ fontSize: 11, color: "var(--text-secondary)", marginBottom: 28 }}>
                  Se cotizaron {progreso.total} ítems. Revisa los resultados y ajusta proveedores.
                </div>
                <Link href={`/proyectos/${proyectoId}`} className="btn-swiss-primary" style={{ padding: "12px 32px", fontSize: 12, textDecoration: "none", display: "inline-block" }}>
                  Ver proyecto completo →
                </Link>
              </>
            )}
          </div>
        )}
      </div>
    </>
  );
}
