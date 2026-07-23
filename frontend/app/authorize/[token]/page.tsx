"use client";
import { useEffect, useState } from "react";
import { useParams, useSearchParams } from "next/navigation";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface ResumenItem {
  nombre: string;
  cantidad: number;
  proveedor: string;
  precio_clp: number | null;
  justificacion?: string;
}

interface Solicitud {
  id: string;
  referencia: string;
  resumen: {
    lista_nombre?: string;
    solicitante?: string;
    empresa?: string;
    items?: ResumenItem[];
    monto_total?: number;
  };
  estado: string;
  aprobador_email: string | null;
  expira_at: string | null;
  created_at: string;
}

const fmtCLP = (n: number) => `$${Math.round(n).toLocaleString("es-CL")}`;

export default function AuthorizePage() {
  const params = useParams();
  const searchParams = useSearchParams();
  const token = params.token as string;
  const decisionAuto = searchParams.get("decision");

  const [sol, setSol] = useState<Solicitud | null>(null);
  const [error, setError] = useState("");
  const [resultado, setResultado] = useState("");
  const [enviando, setEnviando] = useState(false);
  const [comentario, setComentario] = useState("");
  const [mostrarRechazo, setMostrarRechazo] = useState(false);

  useEffect(() => {
    fetch(`${API_URL}/api/aprobaciones/token/${token}`)
      .then(async (r) => {
        if (!r.ok) throw new Error((await r.json()).detail ?? "Error");
        return r.json();
      })
      .then(setSol)
      .catch((e) => setError(e.message));
  }, [token]);

  const decidir = async (decision: "aprobar" | "rechazar") => {
    setEnviando(true);
    try {
      const r = await fetch(`${API_URL}/api/aprobaciones/token/${token}/decidir`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ decision, comentario: decision === "rechazar" ? comentario : undefined }),
      });
      const d = await r.json();
      if (!r.ok) throw new Error(d.detail ?? "Error");
      setResultado(d.estado);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Error");
    } finally {
      setEnviando(false);
    }
  };

  const esLista = sol?.referencia?.startsWith("lista:");
  const items = sol?.resumen?.items ?? [];
  const total = sol?.resumen?.monto_total ?? 0;

  return (
    <div style={{ minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center", background: "var(--bg-base)", padding: 24 }}>
      <div style={{ width: 560, maxWidth: "100%", border: "1px solid var(--border-strong)", background: "var(--bg-elevated)", padding: 32 }}>
        <div className="label" style={{ color: "var(--accent)", fontWeight: 800, marginBottom: 4, letterSpacing: "0.06em" }}>BAIYER</div>
        <h1 style={{ fontSize: 18, fontWeight: 800, margin: "0 0 16px" }}>Autorización de compra</h1>

        {error && <div className="label" style={{ color: "var(--text-error)", padding: 12, background: "var(--fill-error)", marginBottom: 12 }}>{error}</div>}

        {!error && !sol && <div className="label" style={{ color: "var(--text-muted)" }}>Cargando…</div>}

        {sol && !resultado && (
          <>
            {/* Encabezado de la solicitud */}
            <div style={{ border: "1px solid var(--border-default)", padding: 14, marginBottom: 16, background: "var(--bg-surface)" }}>
              {sol.resumen.solicitante && (
                <div style={{ fontSize: 12, marginBottom: 4 }}>
                  <span className="label" style={{ color: "var(--text-muted)" }}>SOLICITANTE:</span>{" "}
                  <span style={{ fontWeight: 700 }}>{sol.resumen.solicitante}</span>
                  {sol.resumen.empresa && <span style={{ color: "var(--text-muted)" }}> — {sol.resumen.empresa}</span>}
                </div>
              )}
              {sol.resumen.lista_nombre && (
                <div style={{ fontSize: 12, marginBottom: 4 }}>
                  <span className="label" style={{ color: "var(--text-muted)" }}>LISTA:</span>{" "}
                  <span style={{ fontWeight: 700 }}>{sol.resumen.lista_nombre}</span>
                </div>
              )}
              {sol.expira_at && (
                <div className="label" style={{ color: "var(--text-muted)", marginTop: 4 }}>
                  Expira: {new Date(sol.expira_at).toLocaleDateString("es-CL", { day: "numeric", month: "long", year: "numeric" })}
                </div>
              )}
            </div>

            {/* Tabla de ítems */}
            {esLista && items.length > 0 && (
              <div style={{ border: "1px solid var(--border-default)", marginBottom: 16 }}>
                <div style={{
                  display: "grid", gridTemplateColumns: "1.5fr 1fr 100px",
                  padding: "8px 14px", borderBottom: "1px solid var(--border-subtle)", background: "var(--bg-base)",
                }}>
                  <div className="label" style={{ fontWeight: 700, color: "var(--text-muted)" }}>ÍTEM</div>
                  <div className="label" style={{ fontWeight: 700, color: "var(--text-muted)" }}>PROVEEDOR</div>
                  <div className="label" style={{ fontWeight: 700, color: "var(--text-muted)", textAlign: "right" }}>PRECIO</div>
                </div>
                {items.map((it, i) => (
                  <div key={i}>
                    <div style={{
                      display: "grid", gridTemplateColumns: "1.5fr 1fr 100px",
                      padding: "10px 14px", alignItems: "center",
                      borderBottom: i < items.length - 1 || it.justificacion ? "1px solid var(--border-subtle)" : "none",
                    }}>
                      <div style={{ fontSize: 12, fontWeight: 700 }}>
                        {it.nombre}
                        <span className="label" style={{ color: "var(--text-muted)", fontWeight: 400, marginLeft: 4 }}>×{it.cantidad}</span>
                      </div>
                      <div style={{ fontSize: 12 }}>{it.proveedor}</div>
                      <div style={{ fontSize: 12, fontWeight: 700, textAlign: "right" }}>
                        {it.precio_clp != null ? fmtCLP(it.precio_clp * it.cantidad) : "—"}
                      </div>
                    </div>
                    {it.justificacion && (
                      <div style={{ padding: "4px 14px 10px", fontSize: 11, color: "var(--text-secondary)", borderBottom: i < items.length - 1 ? "1px solid var(--border-subtle)" : "none" }}>
                        {it.justificacion}
                      </div>
                    )}
                  </div>
                ))}
                {total > 0 && (
                  <div style={{ display: "flex", justifyContent: "space-between", padding: "10px 14px", background: "var(--bg-base)", borderTop: "1px solid var(--border-default)" }}>
                    <span style={{ fontSize: 12, fontWeight: 800 }}>TOTAL</span>
                    <span style={{ fontSize: 14, fontWeight: 800 }}>{fmtCLP(total)}</span>
                  </div>
                )}
              </div>
            )}

            {/* Resumen genérico para solicitudes no-lista */}
            {!esLista && Object.entries(sol.resumen ?? {}).length > 0 && (
              <div style={{ border: "1px solid var(--border-default)", padding: 14, marginBottom: 16 }}>
                {Object.entries(sol.resumen).map(([k, v]) => (
                  <div key={k} style={{ display: "flex", justifyContent: "space-between", padding: "3px 0", fontSize: 12 }}>
                    <span className="label" style={{ color: "var(--text-muted)" }}>{k.replace(/_/g, " ")}</span>
                    <span style={{ fontWeight: 700, textAlign: "right" }}>{String(v)}</span>
                  </div>
                ))}
              </div>
            )}

            {sol.estado !== "pendiente" ? (
              <div className="label" style={{ padding: 12, background: "var(--bg-surface)", border: "1px solid var(--border-default)" }}>
                Esta solicitud ya fue <strong>{sol.estado === "aprobado" ? "aprobada" : sol.estado}</strong>.
              </div>
            ) : (
              <>
                {mostrarRechazo ? (
                  <div style={{ border: "1px solid var(--border-accent)", padding: 16, marginBottom: 12 }}>
                    <div className="label" style={{ color: "var(--text-error)", fontWeight: 700, marginBottom: 8 }}>RECHAZAR SOLICITUD</div>
                    <textarea
                      value={comentario}
                      onChange={e => setComentario(e.target.value)}
                      placeholder="Comentario para el solicitante (opcional): motivo del rechazo, qué cambiar…"
                      rows={3}
                      style={{
                        width: "100%", background: "var(--bg-base)", border: "1px solid var(--border-default)",
                        padding: "8px 10px", fontSize: 12, color: "var(--text-primary)",
                        fontFamily: "var(--font-mono)", outline: "none", resize: "vertical", boxSizing: "border-box",
                      }}
                    />
                    <div style={{ display: "flex", gap: 10, marginTop: 12 }}>
                      <button className="btn-swiss-primary" style={{ flex: 1, padding: "10px 0", fontSize: 12, background: "var(--accent)" }}
                        disabled={enviando} onClick={() => decidir("rechazar")}>
                        Confirmar rechazo
                      </button>
                      <button className="btn-swiss-secondary" style={{ flex: 1, padding: "10px 0", fontSize: 12 }}
                        onClick={() => setMostrarRechazo(false)}>
                        Cancelar
                      </button>
                    </div>
                  </div>
                ) : (
                  <div style={{ display: "flex", gap: 10 }}>
                    <button className="btn-swiss-primary" style={{ flex: 1, padding: "12px 0", fontSize: 13 }}
                      disabled={enviando} onClick={() => decidir("aprobar")}>
                      Aprobar
                    </button>
                    <button className="btn-swiss-secondary" style={{ flex: 1, padding: "12px 0", fontSize: 13 }}
                      disabled={enviando} onClick={() => setMostrarRechazo(true)}>
                      Rechazar
                    </button>
                  </div>
                )}
                {decisionAuto && (
                  <div className="label" style={{ color: "var(--text-muted)", marginTop: 10 }}>
                    Llegaste desde el enlace de {decisionAuto === "aprobar" ? "aprobación" : "rechazo"} — confirma con el botón.
                  </div>
                )}
              </>
            )}
          </>
        )}

        {resultado && (
          <div style={{ padding: 20, textAlign: "center", background: resultado === "aprobado" ? "var(--fill-success)" : "var(--fill-error)", border: `1px solid ${resultado === "aprobado" ? "var(--palette-green-500)" : "var(--border-accent)"}` }}>
            <div style={{ fontSize: 14, fontWeight: 800, marginBottom: 4 }}>
              Solicitud {resultado === "aprobado" ? "aprobada" : "rechazada"}
            </div>
            <div className="label" style={{ color: "var(--text-muted)" }}>
              El solicitante será notificado. Ya puedes cerrar esta ventana.
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
