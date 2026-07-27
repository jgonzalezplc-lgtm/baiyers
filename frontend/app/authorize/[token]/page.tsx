"use client";
import { useEffect, useState } from "react";
import { useParams, useSearchParams } from "next/navigation";
import { Check, ChevronDown, MessageSquare, X } from "lucide-react";
import { Badge, BtnPrimary, BtnSecondary, Card } from "@/components/ui";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface ResumenItem {
  cotizacion_id?: string;
  nombre: string;
  cantidad: number;
  proveedor: string;
  precio_clp: number | null;
  justificacion?: string;
  url?: string | null;
  alternativas?: { proveedor?: string | null; precio_clp?: number | null; moneda?: string; url?: string | null }[];
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
  const [modoComentario, setModoComentario] = useState<"observaciones" | "rechazo">("rechazo");
  const [decisionesItems, setDecisionesItems] = useState<Record<string, { estado: "aprobado" | "rechazado"; motivo?: string }>>({});
  const [alternativasAbiertas, setAlternativasAbiertas] = useState<Record<string, boolean>>({});

  useEffect(() => {
    fetch(`${API_URL}/api/aprobaciones/token/${token}`)
      .then(async (r) => {
        if (!r.ok) throw new Error((await r.json()).detail ?? "Error");
        return r.json();
      })
      .then((data) => { setSol(data); const previas = data.resumen?.decisiones_items || {}; setDecisionesItems(previas); })
      .catch((e) => setError(e.message));
  }, [token]);

  const decidir = async (decision: "aprobar" | "aprobar_con_observaciones" | "rechazar") => {
    setEnviando(true);
    try {
      const r = await fetch(`${API_URL}/api/aprobaciones/token/${token}/decidir`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ decision, comentario: comentario || undefined, item_decisions: decisionesItems }),
      });
      const d = await r.json();
      if (!r.ok) throw new Error(d.detail ?? "Error");
      setResultado(decision === "aprobar_con_observaciones" ? "aprobado_con_observaciones" : d.estado);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Error");
    } finally {
      setEnviando(false);
    }
  };

  const esLista = sol?.referencia?.startsWith("lista:");
  const items = sol?.resumen?.items ?? [];
  const total = sol?.resumen?.monto_total ?? 0;
  const rechazados = Object.values(decisionesItems).filter(d => d.estado === "rechazado").length;

  return (
    <div style={{ minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center", background: "var(--bg-base)", padding: 24 }}>
      <div style={{ width: 760, maxWidth: "100%", border: "1px solid var(--n-200)", borderRadius: "var(--r-lg)", background: "var(--surface)", padding: 28, boxShadow: "var(--shadow-card)" }}>
        <div className="label" style={{ color: "var(--accent)", fontWeight: 800, marginBottom: 4, letterSpacing: "0.06em" }}>Baiyer</div>
        <h1 style={{ fontSize: 18, fontWeight: 800, margin: "0 0 16px" }}>Autorización de compra</h1>

        {error && <div className="label" style={{ color: "var(--text-error)", padding: 12, background: "var(--fill-error)", marginBottom: 12 }}>{error}</div>}

        {!error && !sol && <div className="label" style={{ color: "var(--text-muted)" }}>Cargando…</div>}

        {sol && !resultado && (
          <>
            {/* Encabezado de la solicitud */}
            <Card padding={16} style={{ marginBottom: 16, background: "var(--surface-2)" }}>
              {sol.resumen.solicitante && (
                <div style={{ fontSize: 12, marginBottom: 4 }}>
                  <span className="label" style={{ color: "var(--text-muted)" }}>SOLICITANTE:</span>{" "}
                  <span style={{ fontWeight: 700 }}>{sol.resumen.solicitante}</span>
                  {sol.resumen.empresa && <span style={{ color: "var(--text-muted)" }}>, {sol.resumen.empresa}</span>}
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
            </Card>

            {/* Tabla de ítems */}
            {esLista && items.length > 0 && (
              <div style={{ border: "1px solid var(--border-default)", marginBottom: 16 }}>
                <div style={{
                  display: "grid", gridTemplateColumns: "1.35fr 1fr 100px 120px",
                  padding: "8px 14px", borderBottom: "1px solid var(--border-subtle)", background: "var(--bg-base)",
                }}>
                  <div className="label" style={{ fontWeight: 700, color: "var(--text-muted)" }}>Ítem</div>
                  <div className="label" style={{ fontWeight: 700, color: "var(--text-muted)" }}>Proveedor</div>
                  <div className="label" style={{ fontWeight: 700, color: "var(--text-muted)", textAlign: "right" }}>Precio</div>
                  <div className="label" style={{ fontWeight: 700, color: "var(--text-muted)" }}>Decisión</div>
                </div>
                {items.map((it, i) => (
                  <div key={i}>
                    <div style={{
                      display: "grid", gridTemplateColumns: "1.35fr 1fr 100px 120px",
                      padding: "10px 14px", alignItems: "center",
                      borderBottom: i < items.length - 1 || it.justificacion ? "1px solid var(--border-subtle)" : "none",
                    }}>
                      <div style={{ fontSize: 12, fontWeight: 700 }}>
                        {it.url ? <a href={it.url} target="_blank" rel="noreferrer" style={{ color: "inherit" }}>{it.nombre} ↗</a> : it.nombre}
                        <span className="label" style={{ color: "var(--text-muted)", fontWeight: 400, marginLeft: 4 }}>×{it.cantidad}</span>
                      </div>
                      <div style={{ fontSize: 12 }}>{it.proveedor}</div>
                      <div style={{ fontSize: 12, fontWeight: 700, textAlign: "right" }}>
                        {it.precio_clp != null ? fmtCLP(it.precio_clp * it.cantidad) : "—"}
                      </div>
                      <div style={{ display: "flex", gap: 6, flexWrap: "wrap", alignItems: "center" }}>
                        <BtnSecondary size="sm" icon={Check} onClick={() => setDecisionesItems(d => ({ ...d, [it.cotizacion_id || String(i)]: { estado: "aprobado" } }))} style={decisionesItems[it.cotizacion_id || String(i)]?.estado === "aprobado" ? { background: "var(--st-aprobada-bg)", color: "var(--st-aprobada-fg)", borderColor: "var(--st-aprobada-fg)" } : {}}>Aceptar</BtnSecondary>
                        <BtnSecondary size="sm" icon={X} onClick={() => setDecisionesItems(d => ({ ...d, [it.cotizacion_id || String(i)]: { estado: "rechazado", motivo: d[it.cotizacion_id || String(i)]?.motivo || "" } }))} style={decisionesItems[it.cotizacion_id || String(i)]?.estado === "rechazado" ? { background: "var(--st-rechazada-bg)", color: "var(--st-rechazada-fg)", borderColor: "var(--st-rechazada-fg)" } : {}}>Rechazar</BtnSecondary>
                        {decisionesItems[it.cotizacion_id || String(i)]?.estado === "aprobado" && <Badge status="aprobada">Aceptado</Badge>}
                        {decisionesItems[it.cotizacion_id || String(i)]?.estado === "rechazado" && <Badge status="rechazada">Rechazado</Badge>}
                      </div>
                    </div>
                    {it.justificacion && (
                      <div style={{ padding: "4px 14px 10px", fontSize: 11, color: "var(--text-secondary)", borderBottom: i < items.length - 1 ? "1px solid var(--border-subtle)" : "none" }}>
                        {it.justificacion}
                      </div>
                    )}
                    {(it.alternativas?.length || 0) > 0 && (
                      <div style={{ padding: "0 14px 10px", borderBottom: i < items.length - 1 ? "1px solid var(--border-subtle)" : "none" }}>
                        <BtnSecondary size="sm" icon={ChevronDown} onClick={() => setAlternativasAbiertas(a => ({ ...a, [it.cotizacion_id || String(i)]: !a[it.cotizacion_id || String(i)] }))}>{alternativasAbiertas[it.cotizacion_id || String(i)] ? "Ocultar" : "Ver"} alternativas ({it.alternativas!.length})</BtnSecondary>
                        {alternativasAbiertas[it.cotizacion_id || String(i)] && it.alternativas!.map((alt, ai) => <div key={ai} style={{ display: "flex", justifyContent: "space-between", gap: 8, fontSize: 11, padding: "4px 0" }}><span>{alt.url ? <a href={alt.url} target="_blank" rel="noreferrer">{alt.proveedor || "Proveedor"} ↗</a> : alt.proveedor || "Proveedor"}</span><span>{alt.precio_clp != null ? `${alt.moneda === "CLP" ? fmtCLP(alt.precio_clp) : `${alt.precio_clp} ${alt.moneda || ""}`}` : "—"}</span></div>)}
                      </div>
                    )}
                    {decisionesItems[it.cotizacion_id || String(i)]?.estado === "rechazado" && <div style={{ padding: "0 14px 10px" }}><input value={decisionesItems[it.cotizacion_id || String(i)]?.motivo || ""} onChange={e => setDecisionesItems(d => ({ ...d, [it.cotizacion_id || String(i)]: { estado: "rechazado", motivo: e.target.value } }))} placeholder="Motivo del rechazo (opcional)" style={{ width: "100%", boxSizing: "border-box", padding: "9px 10px", fontSize: 13, background: "var(--surface)", color: "var(--n-900)", border: "1px solid var(--n-300)", borderRadius: "var(--r-md)", fontFamily: "var(--font-sans)", outline: "none" }} /></div>}
                  </div>
                ))}
                {total > 0 && (
                  <div style={{ display: "flex", justifyContent: "space-between", padding: "10px 14px", background: "var(--bg-base)", borderTop: "1px solid var(--border-default)" }}>
                    <span style={{ fontSize: 12, fontWeight: 800 }}>Total</span>
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
                  <Card padding={16} style={{ borderColor: modoComentario === "rechazo" ? "var(--st-rechazada-fg)" : "var(--brand)", background: modoComentario === "rechazo" ? "var(--st-rechazada-bg)" : "var(--surface-2)", marginBottom: 12 }}>
                    <div style={{ color: modoComentario === "rechazo" ? "var(--st-rechazada-fg)" : "var(--n-800)", fontWeight: 700, marginBottom: 8 }}>{modoComentario === "rechazo" ? "Rechazar solicitud" : "Aprobar con observaciones"}</div>
                    <textarea
                      value={comentario}
                      onChange={e => setComentario(e.target.value)}
                      placeholder="Escribe la observación o el motivo del rechazo…"
                      rows={3}
                      style={{
                        width: "100%", background: "var(--bg-base)", border: "1px solid var(--border-default)",
                        padding: "8px 10px", fontSize: 12, color: "var(--text-primary)",
                        fontFamily: "var(--font-mono)", outline: "none", resize: "vertical", boxSizing: "border-box",
                      }}
                    />
                    <div style={{ display: "flex", gap: 10, marginTop: 12 }}>
                      <BtnPrimary style={{ flex: 1, background: modoComentario === "rechazo" ? "var(--st-rechazada-fg)" : undefined }} disabled={enviando} icon={modoComentario === "rechazo" ? X : Check} onClick={() => decidir(modoComentario === "rechazo" ? "rechazar" : "aprobar_con_observaciones")}>{modoComentario === "rechazo" ? "Rechazar solicitud" : "Aprobar con observaciones"}</BtnPrimary>
                      <BtnSecondary style={{ flex: 1 }} onClick={() => setMostrarRechazo(false)}>Cancelar</BtnSecondary>
                    </div>
                  </Card>
                ) : (
                  <div>
                    {rechazados > 0 && <div style={{ marginBottom: 10, fontSize: 13, color: "var(--st-encurso-fg)", background: "var(--st-encurso-bg)", padding: "9px 12px", borderRadius: "var(--r-md)" }}>{rechazados} ítem{rechazados === 1 ? " quedó rechazado" : "s quedaron rechazados"}. Envía la lista como aprobada con observaciones para que se corrijan y reenvíen.</div>}
                    <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
                    <BtnPrimary style={{ flex: 1 }} disabled={enviando || rechazados > 0} icon={Check} onClick={() => decidir("aprobar")}>Aprobar todo</BtnPrimary>
                    <BtnSecondary style={{ flex: 1 }} disabled={enviando || rechazados === 0} icon={MessageSquare} onClick={() => { setModoComentario("observaciones"); setMostrarRechazo(true); }}>Aprobar con observaciones</BtnSecondary>
                    <BtnSecondary style={{ flex: 1, color: "var(--st-rechazada-fg)", borderColor: "var(--st-rechazada-fg)" }} disabled={enviando} icon={X} onClick={() => { setModoComentario("rechazo"); setMostrarRechazo(true); }}>Rechazar</BtnSecondary>
                    </div>
                  </div>
                )}
                {decisionAuto && (
                  <div className="label" style={{ color: "var(--text-muted)", marginTop: 10 }}>
                    Llegaste desde el enlace de {decisionAuto === "aprobar" ? "aprobación" : "rechazo"}, confirma con el botón.
                  </div>
                )}
              </>
            )}
          </>
        )}

        {resultado && (
          <Card padding={20} style={{ textAlign: "center", background: resultado !== "rechazado" ? "var(--st-aprobada-bg)" : "var(--st-rechazada-bg)", borderColor: resultado !== "rechazado" ? "var(--st-aprobada-fg)" : "var(--st-rechazada-fg)" }}>
            <div style={{ fontSize: 14, fontWeight: 800, marginBottom: 4 }}>
              Solicitud {resultado === "aprobado_con_observaciones" ? "aprobada con observaciones" : resultado === "aprobado" ? "registrada como aprobada" : "registrada como rechazada"}
            </div>
            <div className="label" style={{ color: "var(--text-muted)" }}>
              El solicitante será notificado. Ya puedes cerrar esta ventana.
            </div>
          </Card>
        )}
      </div>
    </div>
  );
}
