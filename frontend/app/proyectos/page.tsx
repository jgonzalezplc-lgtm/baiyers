"use client";
import { useState, useEffect } from "react";
import { createClient } from "@/lib/supabase/client";
import Link from "next/link";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const ESTADO_CONFIG: Record<string, { label: string; color: string }> = {
  borrador:     { label: "Borrador",     color: "var(--text-muted)" },
  cotizando:    { label: "Cotizando",    color: "var(--text-warning)" },
  en_ejecucion: { label: "En ejecucion", color: "var(--accent)" },
  completado:   { label: "Completado",   color: "var(--text-success)" },
};

interface Proyecto {
  id: string;
  nombre: string;
  cliente: string | null;
  estado: string;
  monto_total: number;
  fecha_inicio: string | null;
  created_at: string;
}

export default function ProyectosPage() {
  const [proyectos, setProyectos] = useState<Proyecto[]>([]);
  const [loading, setLoading] = useState(true);
  const [userId, setUserId] = useState<string | null>(null);
  const [filtroEstado, setFiltroEstado] = useState("todos");

  useEffect(() => {
    createClient().auth.getUser().then(({ data }) => {
      if (data.user) {
        setUserId(data.user.id);
        cargar(data.user.id);
      }
    });
  }, []);

  const cargar = async (uid: string) => {
    setLoading(true);
    try {
      const res = await fetch(`${API_URL}/api/proyectos?user_id=${uid}`);
      if (res.ok) setProyectos(await res.json());
    } catch { /* silent */ } finally { setLoading(false); }
  };

  const filtrados = filtroEstado === "todos" ? proyectos : proyectos.filter(p => p.estado === filtroEstado);

  return (
    <>
      {/* Page header */}
      <div style={{ marginBottom: 24 }}>
        <div className="section-rule" style={{ marginBottom: 16 }} />
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end" }}>
          <div>
            <span style={{ fontSize: 10, fontWeight: 700, color: "var(--text-muted)", letterSpacing: "0.06em", display: "block", marginBottom: 6 }}>
              PROYECTOS
            </span>
            <h1 style={{ fontSize: 26, fontWeight: 700, color: "var(--text-primary)", margin: "0 0 6px", letterSpacing: "-0.02em" }}>
              Proyectos
            </h1>
            <p style={{ fontSize: 12, color: "var(--text-secondary)", margin: 0 }}>Gestión de proyectos y cotizaciones agrupadas.</p>
          </div>
          <Link href="/proyectos/nuevo" className="btn-swiss-primary" style={{ textDecoration: "none" }}>
            + Nuevo proyecto
          </Link>
        </div>
      </div>

      {/* Filtros */}
      <div style={{ display: "flex", gap: 1, marginBottom: 20, border: "1px solid var(--border-default)", width: "fit-content" }}>
        {["todos", "borrador", "cotizando", "en_ejecucion", "completado"].map(e => (
          <button
            key={e}
            onClick={() => setFiltroEstado(e)}
            className="label"
            style={{
              padding: "6px 14px",
              border: "none",
              borderRight: e !== "completado" ? "1px solid var(--border-default)" : "none",
              cursor: "pointer",
              fontFamily: "var(--font-mono)",
              background: filtroEstado === e ? "var(--bg-inverse)" : "var(--bg-surface)",
              color: filtroEstado === e ? "var(--text-inverse)" : "var(--text-muted)",
            }}
          >
            {e === "todos" ? "TODOS" : (ESTADO_CONFIG[e]?.label || e).toUpperCase()}
          </button>
        ))}
      </div>

      {loading ? (
        <div style={{ display: "flex", flexDirection: "column", gap: 1 }}>
          {[1, 2, 3].map(i => (
            <div key={i} style={{ background: "var(--bg-surface)", border: "1px solid var(--border-default)", height: 100, opacity: 0.5 }} />
          ))}
        </div>
      ) : filtrados.length === 0 ? (
        <div style={{
          background: "var(--bg-surface)",
          border: "1px solid var(--border-default)",
          padding: "48px 20px",
          textAlign: "center",
        }}>
          <div className="section-rule" style={{ margin: "0 auto 16px" }} />
          <div style={{ fontSize: 13, color: "var(--text-primary)", fontWeight: 700, marginBottom: 8 }}>Sin proyectos aun</div>
          <div style={{ fontSize: 11, color: "var(--text-muted)", marginBottom: 20 }}>
            Crea un proyecto, sube la cubicacion y cotiza todos los materiales automaticamente.
          </div>
          <Link href="/proyectos/nuevo" className="btn-swiss-primary" style={{ textDecoration: "none", display: "inline-block" }}>
            Crear primer proyecto
          </Link>
        </div>
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))", gap: 1, border: "1px solid var(--border-default)" }}>
          {filtrados.map((p, idx) => {
            const cfg = ESTADO_CONFIG[p.estado] ?? ESTADO_CONFIG.borrador;
            return (
              <Link key={p.id} href={`/proyectos/${p.id}`} style={{ textDecoration: "none" }}>
                <div style={{
                  background: "var(--bg-surface)",
                  borderRight: "1px solid var(--border-default)",
                  borderBottom: "1px solid var(--border-default)",
                  padding: "18px 20px",
                  cursor: "pointer",
                  height: "100%",
                }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 10 }}>
                    <span className="label" style={{ color: cfg.color }}>{cfg.label.toUpperCase()}</span>
                    <span className="label" style={{ color: "var(--text-muted)" }}>
                      {new Date(p.created_at).toLocaleDateString("es-CL")}
                    </span>
                  </div>
                  <div style={{ fontSize: 14, fontWeight: 700, color: "var(--text-primary)", marginBottom: 4, letterSpacing: "-0.01em" }}>
                    {p.nombre}
                  </div>
                  {p.cliente && (
                    <div style={{ fontSize: 11, color: "var(--text-muted)", marginBottom: 10 }}>{p.cliente}</div>
                  )}
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                    <div style={{ fontSize: 18, fontWeight: 700, color: p.monto_total > 0 ? "var(--accent)" : "var(--text-muted)" }}>
                      {p.monto_total > 0 ? `$${Math.round(p.monto_total).toLocaleString("es-CL")}` : "Sin cotizar"}
                    </div>
                    {p.fecha_inicio && (
                      <div className="label" style={{ color: "var(--text-muted)" }}>
                        Inicio: {new Date(p.fecha_inicio + "T12:00:00").toLocaleDateString("es-CL")}
                      </div>
                    )}
                  </div>
                </div>
              </Link>
            );
          })}
        </div>
      )}
    </>
  );
}
