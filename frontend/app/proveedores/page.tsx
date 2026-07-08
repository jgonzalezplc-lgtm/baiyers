"use client";
import { useState, useEffect } from "react";
import { createClient } from "@/lib/supabase/client";
import Link from "next/link";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface Proveedor {
  id: string;
  nombre: string;
  email?: string;
  score: number;
  categoria_score: string;
  total_solicitudes: number;
  total_oc_enviadas: number;
  total_oc_confirmadas: number;
  total_respuestas: number;
  tasa_respuesta: number;
  bloqueado: boolean;
  created_at: string;
}

const CATEGORIAS: Record<string, { label: string; color: string }> = {
  preferido:      { label: "Preferido",    color: "#b45309" },
  confiable:      { label: "Confiable",    color: "var(--text-success)" },
  con_reparos:    { label: "Con reparos",  color: "var(--text-secondary)" },
  problematico:   { label: "Problematico", color: "var(--text-error)" },
  bloqueado_auto: { label: "Bloqueado",    color: "var(--text-muted)" },
};

function ScoreBadge({ score, categoria }: { score: number; categoria: string }) {
  const cat = CATEGORIAS[categoria] ?? CATEGORIAS.con_reparos;
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
      <div style={{
        width: 36,
        height: 36,
        background: "var(--bg-base)",
        border: "2px solid var(--border-default)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
      }}>
        <span style={{ fontSize: 13, fontWeight: 700, color: cat.color }}>{score}</span>
      </div>
      <span className="label" style={{ color: cat.color }}>{cat.label}</span>
    </div>
  );
}

export default function ProveedoresPage() {
  const [proveedores, setProveedores] = useState<Proveedor[]>([]);
  const [loading, setLoading] = useState(true);
  const [userId, setUserId] = useState<string | null>(null);
  const [toast, setToast] = useState("");
  const [filtroBloqueados, setFiltroBloqueados] = useState(false);

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
      const res = await fetch(`${API_URL}/api/suppliers?user_id=${uid}`);
      if (!res.ok) throw new Error();
      setProveedores(await res.json());
    } catch {
      showToast("Error cargando proveedores");
    } finally {
      setLoading(false);
    }
  };

  const showToast = (msg: string) => { setToast(msg); setTimeout(() => setToast(""), 3000); };

  const toggleBloquear = async (p: Proveedor) => {
    if (!userId) return;
    const endpoint = p.bloqueado
      ? `/api/suppliers/${p.id}/desbloquear?user_id=${userId}`
      : `/api/suppliers/${p.id}/bloquear?user_id=${userId}`;
    try {
      await fetch(`${API_URL}${endpoint}`, { method: "POST" });
      setProveedores(prev =>
        prev.map(x => x.id === p.id ? { ...x, bloqueado: !x.bloqueado, categoria_score: !x.bloqueado ? "bloqueado_auto" : x.categoria_score } : x)
      );
      showToast(p.bloqueado ? "Proveedor desbloqueado" : "Proveedor bloqueado");
    } catch {
      showToast("Error actualizando proveedor");
    }
  };

  const filtrados = filtroBloqueados
    ? proveedores.filter(p => p.bloqueado)
    : proveedores.filter(p => !p.bloqueado);

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
          zIndex: 100,
          fontFamily: "var(--font-mono)",
        }}>{toast}</div>
      )}

      {/* Page header */}
      <div style={{ marginBottom: 28 }}>
        <div className="section-rule" style={{ marginBottom: 16 }} />
        <span style={{ fontSize: 10, fontWeight: 700, color: "var(--text-muted)", letterSpacing: "0.06em", display: "block", marginBottom: 6 }}>
          RED
        </span>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end" }}>
          <div>
            <h1 style={{ fontSize: 26, fontWeight: 700, color: "var(--text-primary)", margin: "0 0 6px", letterSpacing: "-0.02em" }}>
              Proveedores
            </h1>
            <p style={{ fontSize: 12, color: "var(--text-secondary)", margin: 0 }}>Red de proveedores calificados.</p>
          </div>
          <div style={{ display: "flex", gap: 8 }}>
            <Link href="/proveedores/importar" className="btn-swiss-secondary" style={{ textDecoration: "none" }}>
              Importar Excel
            </Link>
            <button
              onClick={() => setFiltroBloqueados(false)}
              style={{
                fontSize: 10,
                padding: "6px 14px",
                border: "none",
                cursor: "pointer",
                fontFamily: "var(--font-mono)",
                letterSpacing: "0.05em",
                fontWeight: 700,
                background: filtroBloqueados ? "var(--bg-surface)" : "var(--accent)",
                color: filtroBloqueados ? "var(--text-muted)" : "#fff",
              }}
            >
              ACTIVOS
            </button>
            <button
              onClick={() => setFiltroBloqueados(true)}
              style={{
                fontSize: 10,
                padding: "6px 14px",
                border: "1px solid var(--border-default)",
                cursor: "pointer",
                fontFamily: "var(--font-mono)",
                letterSpacing: "0.05em",
                fontWeight: filtroBloqueados ? 700 : 400,
                background: filtroBloqueados ? "var(--fill-error)" : "var(--bg-surface)",
                color: filtroBloqueados ? "var(--text-error)" : "var(--text-muted)",
              }}
            >
              BLOQUEADOS
            </button>
          </div>
        </div>
      </div>

      {/* Leyenda scores */}
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 20 }}>
        {Object.entries(CATEGORIAS).map(([key, val]) => (
          <span key={key} className="label" style={{
            color: val.color,
            border: "1px solid var(--border-default)",
            padding: "3px 10px",
          }}>
            {val.label}
          </span>
        ))}
        <span className="label" style={{ color: "var(--text-muted)", alignSelf: "center", marginLeft: 4 }}>Score 0–100</span>
      </div>

      {loading ? (
        <div style={{ display: "flex", flexDirection: "column", gap: 1 }}>
          {[1, 2, 3].map(i => (
            <div key={i} style={{
              background: "var(--bg-surface)",
              border: "1px solid var(--border-default)",
              height: 80,
              opacity: 0.5,
            }} />
          ))}
        </div>
      ) : filtrados.length === 0 ? (
        <div style={{
          background: "var(--bg-surface)",
          border: "1px solid var(--border-default)",
          padding: "40px 20px",
          textAlign: "center",
        }}>
          <div className="section-rule" style={{ margin: "0 auto 16px" }} />
          <div style={{ fontSize: 13, color: "var(--text-primary)", fontWeight: 700, marginBottom: 8 }}>
            {filtroBloqueados ? "Sin proveedores bloqueados" : "Sin proveedores aun"}
          </div>
          <div style={{ fontSize: 11, color: "var(--text-muted)", marginBottom: 20 }}>
            {filtroBloqueados
              ? "No tienes proveedores bloqueados."
              : "Los proveedores aparecen aqui cuando envias solicitudes o emites OCs."}
          </div>
          {!filtroBloqueados && (
            <Link href="/cotizar" className="btn-swiss-primary" style={{ textDecoration: "none", display: "inline-block" }}>
              Nueva cotizacion
            </Link>
          )}
        </div>
      ) : (
        <div style={{ border: "1px solid var(--border-default)" }}>
          {filtrados.map((p, idx) => (
            <div key={p.id} style={{
              background: "var(--bg-surface)",
              borderBottom: idx < filtrados.length - 1 ? "1px solid var(--border-default)" : "none",
              padding: "16px 20px",
              opacity: p.bloqueado ? 0.7 : 1,
            }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
                <div style={{ flex: 1 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 10 }}>
                    <ScoreBadge score={p.score} categoria={p.bloqueado ? "bloqueado_auto" : p.categoria_score} />
                    <div>
                      <div style={{ fontSize: 13, fontWeight: 700, color: "var(--text-primary)" }}>{p.nombre}</div>
                      {p.email && <div style={{ fontSize: 10, color: "var(--text-muted)", marginTop: 2 }}>{p.email}</div>}
                    </div>
                  </div>

                  <div style={{ display: "flex", gap: 16, flexWrap: "wrap" }}>
                    {[
                      { label: "Solicitudes", val: p.total_solicitudes || 0 },
                      { label: "Tasa resp.", val: `${p.tasa_respuesta || 0}%` },
                      { label: "OCs enviadas", val: p.total_oc_enviadas || 0 },
                      { label: "OCs confirmadas", val: p.total_oc_confirmadas || 0 },
                    ].map(m => (
                      <div key={m.label}>
                        <div className="label" style={{ color: "var(--text-muted)" }}>{m.label}</div>
                        <div style={{ fontSize: 14, fontWeight: 700, color: "var(--text-secondary)" }}>{m.val}</div>
                      </div>
                    ))}
                  </div>
                </div>

                <div style={{ display: "flex", flexDirection: "column", gap: 6, marginLeft: 16 }}>
                  <Link href={`/proveedores/${p.id}`} className="btn-swiss-secondary" style={{ textDecoration: "none", fontSize: 10, padding: "4px 10px" }}>
                    Ver historial
                  </Link>
                  <button
                    onClick={() => toggleBloquear(p)}
                    style={{
                      fontSize: 10,
                      cursor: "pointer",
                      fontFamily: "var(--font-mono)",
                      letterSpacing: "0.05em",
                      background: "none",
                      border: `1px solid ${p.bloqueado ? "var(--palette-green-500)" : "var(--border-accent)"}`,
                      padding: "4px 10px",
                      color: p.bloqueado ? "var(--text-success)" : "var(--text-error)",
                      whiteSpace: "nowrap",
                    }}
                  >
                    {p.bloqueado ? "DESBLOQUEAR" : "BLOQUEAR"}
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </>
  );
}
