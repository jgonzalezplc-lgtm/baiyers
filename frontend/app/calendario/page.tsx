"use client";
import { useState, useEffect, useCallback } from "react";
import { createClient } from "@/lib/supabase/client";
import Link from "next/link";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type Vista = "mes" | "agenda";

interface Evento {
  id: string;
  titulo: string;
  fecha_inicio: string;
  fecha_fin: string;
  tipo: string;
  color: string;
  datos: Record<string, unknown>;
}

const TIPO_LABELS: Record<string, string> = {
  cotizacion: "Cotizacion",
  oc_emitida: "OC Emitida",
  oc_confirmada: "OC Confirmada",
  entrega_estimada: "Entrega Estimada",
  entrega_efectiva: "Llegada Efectiva",
  recurrencia: "Compra Recurrente",
  factura: "Factura",
  factura_vencimiento: "Vencimiento Factura",
};

const MESES = ["Enero","Febrero","Marzo","Abril","Mayo","Junio","Julio","Agosto","Septiembre","Octubre","Noviembre","Diciembre"];
const DIAS_SEMANA = ["Dom","Lun","Mar","Mie","Jue","Vie","Sab"];

function pad(n: number) { return String(n).padStart(2,"0"); }
function fmtDate(d: Date) { return `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}`; }

export default function CalendarioPage() {
  const [vista, setVista] = useState<Vista>("mes");
  const [hoy] = useState(new Date());
  const [current, setCurrent] = useState(new Date());
  const [eventos, setEventos] = useState<Evento[]>([]);
  const [loading, setLoading] = useState(false);
  const [userId, setUserId] = useState<string | null>(null);
  const [eventoActivo, setEventoActivo] = useState<Evento | null>(null);
  const [llegadaModal, setLlegadaModal] = useState<Evento | null>(null);
  const [fechaLlegada, setFechaLlegada] = useState("");
  const [guardando, setGuardando] = useState(false);
  const [toast, setToast] = useState("");

  useEffect(() => {
    createClient().auth.getUser().then(({ data }) => {
      setUserId(data.user?.id ?? null);
    });
  }, []);

  const cargarEventos = useCallback(async (uid: string, desde: string, hasta: string) => {
    setLoading(true);
    try {
      const res = await fetch(`${API_URL}/api/calendario/eventos?user_id=${uid}&fecha_inicio=${desde}&fecha_fin=${hasta}`);
      if (res.ok) setEventos(await res.json());
    } catch { /* silent */ } finally { setLoading(false); }
  }, []);

  useEffect(() => {
    if (!userId) return;
    const año = current.getFullYear();
    const mes = current.getMonth();
    const desde = `${año}-${pad(mes+1)}-01`;
    const ultimo = new Date(año, mes+1, 0).getDate();
    const hasta = `${año}-${pad(mes+1)}-${pad(ultimo)}`;
    cargarEventos(userId, desde, hasta);
  }, [userId, current, cargarEventos]);

  const navMes = (dir: number) => {
    const d = new Date(current);
    d.setMonth(d.getMonth() + dir);
    setCurrent(d);
  };

  const eventosPorDia = (fecha: string) =>
    eventos.filter(e => e.fecha_inicio.slice(0,10) === fecha);

  const handleLlegada = async () => {
    if (!llegadaModal || !fechaLlegada) return;
    setGuardando(true);
    try {
      const res = await fetch(`${API_URL}/api/calendario/llegada-efectiva`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ oc_id: llegadaModal.datos.oc_id, fecha_llegada: fechaLlegada }),
      });
      if (res.ok) {
        setToast("Llegada registrada");
        setLlegadaModal(null);
        setEventoActivo(null);
        if (userId) {
          const año = current.getFullYear(), mes = current.getMonth();
          const desde = `${año}-${pad(mes+1)}-01`;
          const ultimo = new Date(año, mes+1, 0).getDate();
          cargarEventos(userId, desde, `${año}-${pad(mes+1)}-${pad(ultimo)}`);
        }
      }
    } catch { setToast("Error guardando"); }
    finally { setGuardando(false); setTimeout(() => setToast(""), 3000); }
  };

  const renderMes = () => {
    const año = current.getFullYear();
    const mes = current.getMonth();
    const primerDia = new Date(año, mes, 1).getDay();
    const diasEnMes = new Date(año, mes+1, 0).getDate();
    const celdas: (number | null)[] = [...Array(primerDia).fill(null), ...Array.from({length: diasEnMes}, (_,i) => i+1)];
    while (celdas.length % 7 !== 0) celdas.push(null);

    return (
      <div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(7,1fr)", gap: 0, marginBottom: 1, border: "1px solid var(--border-default)", borderBottom: "none" }}>
          {DIAS_SEMANA.map(d => (
            <div key={d} className="label" style={{
              textAlign: "center",
              color: "var(--text-muted)",
              padding: "6px 0",
              borderRight: "1px solid var(--border-default)",
              background: "var(--bg-surface)",
            }}>{d}</div>
          ))}
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(7,1fr)", border: "1px solid var(--border-default)" }}>
          {celdas.map((dia, i) => {
            if (!dia) return <div key={i} style={{ minHeight: 90, background: "var(--bg-base)", borderRight: "1px solid var(--border-default)", borderBottom: "1px solid var(--border-default)" }} />;
            const fecha = `${año}-${pad(mes+1)}-${pad(dia)}`;
            const esHoy = fecha === fmtDate(hoy);
            const evs = eventosPorDia(fecha);
            return (
              <div key={i} style={{
                minHeight: 90,
                background: "var(--bg-surface)",
                borderRight: "1px solid var(--border-default)",
                borderBottom: "1px solid var(--border-default)",
                padding: 6,
                outline: esHoy ? `2px solid var(--accent)` : "none",
                outlineOffset: -2,
              }}>
                <div style={{
                  fontSize: 11,
                  fontWeight: esHoy ? 700 : 400,
                  color: esHoy ? "var(--accent)" : "var(--text-muted)",
                  marginBottom: 4,
                }}>{dia}</div>
                <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                  {evs.slice(0,3).map(ev => (
                    <button key={ev.id} onClick={() => setEventoActivo(ev)} style={{
                      fontSize: 9,
                      background: ev.color + "22",
                      color: ev.color,
                      border: `1px solid ${ev.color}44`,
                      padding: "2px 4px",
                      textAlign: "left",
                      cursor: "pointer",
                      fontFamily: "var(--font-mono)",
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                      whiteSpace: "nowrap",
                      width: "100%",
                    }}>
                      {ev.titulo}
                    </button>
                  ))}
                  {evs.length > 3 && (
                    <div className="label" style={{ color: "var(--text-muted)" }}>+{evs.length - 3} mas</div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    );
  };

  const renderAgenda = () => {
    const sorted = [...eventos].sort((a,b) => a.fecha_inicio.localeCompare(b.fecha_inicio));
    if (!sorted.length) return (
      <div style={{ fontSize: 11, color: "var(--text-muted)", padding: "40px 0", textAlign: "center" }}>
        Sin eventos este mes.
      </div>
    );

    const grupos: Record<string, Evento[]> = {};
    for (const ev of sorted) {
      const fecha = ev.fecha_inicio.slice(0,10);
      if (!grupos[fecha]) grupos[fecha] = [];
      grupos[fecha].push(ev);
    }

    return (
      <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
        {Object.entries(grupos).map(([fecha, evs]) => (
          <div key={fecha}>
            <div className="label" style={{ color: "var(--text-muted)", marginBottom: 6 }}>
              {new Date(fecha + "T12:00:00").toLocaleDateString("es-CL", { weekday: "long", day: "numeric", month: "long" }).toUpperCase()}
            </div>
            <div style={{ border: "1px solid var(--border-default)" }}>
              {evs.map((ev, idx) => (
                <button key={ev.id} onClick={() => setEventoActivo(ev)} style={{
                  background: "var(--bg-surface)",
                  borderBottom: idx < evs.length - 1 ? "1px solid var(--border-default)" : "none",
                  borderLeft: `3px solid ${ev.color}`,
                  padding: "10px 14px",
                  textAlign: "left",
                  cursor: "pointer",
                  fontFamily: "inherit",
                  display: "flex",
                  alignItems: "center",
                  gap: 12,
                  width: "100%",
                  border: "none",
                } as React.CSSProperties}>
                  <span className="label" style={{ color: ev.color, minWidth: 80 }}>
                    {TIPO_LABELS[ev.tipo] || ev.tipo}
                  </span>
                  <span style={{ fontSize: 11, color: "var(--text-secondary)" }}>{ev.titulo}</span>
                </button>
              ))}
            </div>
          </div>
        ))}
      </div>
    );
  };

  return (
    <>
      {toast && (
        <div style={{
          position: "fixed", top: 20, right: 20,
          background: "var(--bg-inverse)",
          padding: "12px 18px",
          fontSize: 11,
          color: "var(--text-inverse)",
          fontWeight: 700,
          zIndex: 200,
          fontFamily: "var(--font-mono)",
        }}>{toast}</div>
      )}

      {/* Page header */}
      <div style={{ marginBottom: 24 }}>
        <div className="section-rule" style={{ marginBottom: 16 }} />
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end" }}>
          <div>
            <span style={{ fontSize: 10, fontWeight: 700, color: "var(--text-muted)", letterSpacing: "0.06em", display: "block", marginBottom: 6 }}>
              PLANIFICACIÓN
            </span>
            <h1 style={{ fontSize: 26, fontWeight: 700, color: "var(--text-primary)", margin: "0 0 6px", letterSpacing: "-0.02em" }}>
              Calendario
            </h1>
            <p style={{ fontSize: 12, color: "var(--text-secondary)", margin: 0 }}>Vista de eventos y entregas.</p>
          </div>

          {/* Leyenda */}
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6, maxWidth: 320, justifyContent: "flex-end" }}>
            {[
              { color: "var(--accent)", label: "Cotizacion" },
              { color: "#8b5cf6", label: "OC Emitida" },
              { color: "#059669", label: "OC Confirmada" },
              { color: "#86efac", label: "Entrega Est." },
              { color: "#047857", label: "Llegada" },
              { color: "#d97706", label: "Recurrente" },
              { color: "var(--text-error)", label: "Vencimiento" },
            ].map(l => (
              <span key={l.label} className="label" style={{
                color: l.color,
                border: `1px solid ${l.color}44`,
                padding: "2px 8px",
              }}>{l.label}</span>
            ))}
          </div>
        </div>
      </div>

      {/* Nav mes + vistas */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <button onClick={() => navMes(-1)} className="btn-swiss-secondary" style={{ padding: "4px 10px", fontSize: 14 }}>‹</button>
          <span style={{ fontSize: 15, fontWeight: 700, color: "var(--text-primary)", minWidth: 160, textAlign: "center", letterSpacing: "-0.01em" }}>
            {MESES[current.getMonth()]} {current.getFullYear()}
          </span>
          <button onClick={() => navMes(1)} className="btn-swiss-secondary" style={{ padding: "4px 10px", fontSize: 14 }}>›</button>
          <button onClick={() => setCurrent(new Date())} className="btn-swiss-secondary" style={{ fontSize: 10 }}>Hoy</button>
        </div>
        <div style={{ display: "flex", border: "1px solid var(--border-default)" }}>
          {(["mes","agenda"] as Vista[]).map(v => (
            <button key={v} onClick={() => setVista(v)} className="label" style={{
              padding: "6px 14px",
              border: "none",
              borderRight: v === "mes" ? "1px solid var(--border-default)" : "none",
              cursor: "pointer",
              fontFamily: "var(--font-mono)",
              background: vista === v ? "var(--bg-inverse)" : "var(--bg-surface)",
              color: vista === v ? "var(--text-inverse)" : "var(--text-muted)",
            }}>
              {v === "mes" ? "MES" : "AGENDA"}
            </button>
          ))}
        </div>
      </div>

      {loading && (
        <div style={{ fontSize: 11, color: "var(--text-muted)", textAlign: "center", padding: 20 }}>
          Cargando eventos...
        </div>
      )}

      {!loading && vista === "mes" && renderMes()}
      {!loading && vista === "agenda" && renderAgenda()}

      {/* Modal evento */}
      {eventoActivo && (
        <div style={{
          position: "fixed", inset: 0,
          background: "rgba(0,0,0,0.6)",
          display: "flex", alignItems: "center", justifyContent: "center",
          zIndex: 100, padding: 16,
        }}>
          <div style={{
            width: "100%", maxWidth: 400,
            background: "var(--bg-surface)",
            border: "1px solid var(--border-default)",
            padding: 24,
          }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 16 }}>
              <div>
                <span className="label" style={{ color: eventoActivo.color }}>
                  {TIPO_LABELS[eventoActivo.tipo] || eventoActivo.tipo}
                </span>
                <h3 style={{ fontSize: 14, fontWeight: 700, color: "var(--text-primary)", margin: "8px 0 4px", letterSpacing: "-0.01em" }}>
                  {eventoActivo.titulo}
                </h3>
                <div style={{ fontSize: 11, color: "var(--text-muted)" }}>
                  {new Date(eventoActivo.fecha_inicio.slice(0,10) + "T12:00:00").toLocaleDateString("es-CL", { weekday: "long", day: "numeric", month: "long", year: "numeric" })}
                </div>
              </div>
              <button onClick={() => setEventoActivo(null)} style={{ background: "none", border: "none", color: "var(--text-muted)", cursor: "pointer", fontSize: 18 }}>✕</button>
            </div>

            <div style={{ display: "flex", flexDirection: "column", gap: 8, marginBottom: 16 }}>
              {eventoActivo.datos.proveedor && (
                <div style={{ fontSize: 11, color: "var(--text-secondary)" }}>
                  Proveedor: <strong style={{ color: "var(--text-primary)" }}>{String(eventoActivo.datos.proveedor)}</strong>
                </div>
              )}
              {eventoActivo.datos.numero_oc && (
                <div style={{ fontSize: 11, color: "var(--text-secondary)" }}>
                  OC: <strong style={{ color: "var(--text-primary)" }}>{String(eventoActivo.datos.numero_oc)}</strong>
                </div>
              )}
              {eventoActivo.datos.monto != null && (
                <div style={{ fontSize: 11, color: "var(--text-secondary)" }}>
                  Monto: <strong style={{ color: "var(--text-primary)" }}>${Number(eventoActivo.datos.monto).toLocaleString("es-CL")}</strong>
                </div>
              )}
              {eventoActivo.datos.frecuencia && (
                <div style={{ fontSize: 11, color: "var(--text-secondary)" }}>
                  Frecuencia: <strong style={{ color: "var(--text-primary)" }}>{String(eventoActivo.datos.frecuencia)}</strong>
                </div>
              )}
            </div>

            <div style={{ display: "flex", gap: 8 }}>
              {eventoActivo.tipo === "entrega_estimada" && (
                <button
                  onClick={() => { setLlegadaModal(eventoActivo); setFechaLlegada(fmtDate(hoy)); }}
                  className="btn-swiss-primary"
                  style={{ flex: 1 }}
                >
                  Marcar llegada efectiva
                </button>
              )}
              {eventoActivo.datos.proveedor_id && (
                <Link href={`/proveedores/${eventoActivo.datos.proveedor_id}`} className="btn-swiss-secondary" style={{ flex: 1, textAlign: "center", textDecoration: "none" }}>
                  Ver proveedor
                </Link>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Modal llegada efectiva */}
      {llegadaModal && (
        <div style={{
          position: "fixed", inset: 0,
          background: "rgba(0,0,0,0.75)",
          display: "flex", alignItems: "center", justifyContent: "center",
          zIndex: 110, padding: 16,
        }}>
          <div style={{
            width: "100%", maxWidth: 360,
            background: "var(--bg-surface)",
            border: "1px solid var(--border-default)",
            padding: 24,
          }}>
            <h3 style={{ fontSize: 14, fontWeight: 700, color: "var(--text-primary)", marginBottom: 4, letterSpacing: "-0.01em" }}>
              Marcar llegada efectiva
            </h3>
            <div style={{ fontSize: 11, color: "var(--text-muted)", marginBottom: 16 }}>
              {String(llegadaModal.datos.numero_oc)} — {String(llegadaModal.datos.proveedor)}
            </div>
            <label className="label" style={{ color: "var(--text-muted)", display: "block", marginBottom: 6 }}>
              Fecha de llegada
            </label>
            <input
              type="date"
              value={fechaLlegada}
              onChange={e => setFechaLlegada(e.target.value)}
              style={{
                width: "100%",
                padding: "10px 12px",
                background: "var(--bg-base)",
                border: "1px solid var(--border-default)",
                color: "var(--text-primary)",
                fontSize: 12,
                outline: "none",
                boxSizing: "border-box",
                fontFamily: "var(--font-mono)",
              }}
            />
            <div style={{ display: "flex", gap: 8, marginTop: 16 }}>
              <button onClick={() => setLlegadaModal(null)} className="btn-swiss-secondary" style={{ flex: 1 }}>
                Cancelar
              </button>
              <button onClick={handleLlegada} disabled={guardando || !fechaLlegada} className="btn-swiss-primary" style={{ flex: 1 }}>
                {guardando ? "Guardando..." : "Confirmar llegada"}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
