"use client";
import { useState, useEffect, useCallback } from "react";
import { useParams } from "next/navigation";
import { createClient } from "@/lib/supabase/client";
import Link from "next/link";
import dynamic from "next/dynamic";

// @react-pdf/renderer solo funciona en el cliente
const InformeCotizacion = dynamic(() => import("@/components/InformeCotizacion"), { ssr: false });

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface Resultado {
  id: string;
  proveedor_nombre: string;
  proveedor_email: string | null;
  precio: number | null;
  moneda: string;
  url: string;
  pais: string;
  fuente: string;
  tipo_proveedor: string;
  estado: string;
  solicitud_enviada_at: string | null;
  respuesta_recibida_at: string | null;
  precio_cotizado: number | null;
  plazo_entrega: string | null;
  condiciones_pago: string | null;
  notas_respuesta: string | null;
  ranking_score: number;
  compra_nacional: boolean;
  relevante: boolean;
  metadata?: string | null;
}

function parseMeta(r: Resultado): Record<string, unknown> {
  try { return r.metadata ? JSON.parse(r.metadata) : {}; } catch { return {}; }
}

interface Cotizacion {
  id: string;
  nombre_identificado: string;
  descripcion: string | null;
  marca: string | null;
  numero_parte: string | null;
  categoria: string | null;
  estado: string;
  confianza_ia: string | null;
  created_at: string;
}

const FUENTE_LABEL: Record<string, string> = {
  mercadolibre: "MercadoLibre", google: "Google Shopping",
  mouser: "Mouser", digikey: "DigiKey", tme: "TME", farnell: "Farnell", manual: "Manual",
  sodimac: "Sodimac", easy: "Easy", lasierra: "La Sierra", construmart: "Construmart",
  vitel: "Vitel", dartel: "Dartel", ferrelectrica: "Ferrelectrica", gobantes: "Gobantes", rhona: "Rhona",
  clcsa: "CLC Maderas", wmaderas: "W Maderas", ferramenta: "Ferramenta", maderas_dir: "Aserraderos CL",
};

const TIPO_PROVEEDOR_LABELS: Record<string, string> = {
  distribuidor: "Distribuidor", fabricante: "Fabricante",
  retail: "Retail", desconocido: "Desconocido",
};

function fmtFecha(iso: string) {
  const d = new Date(iso);
  return `${d.getDate()} ${["Ene","Feb","Mar","Abr","May","Jun","Jul","Ago","Sep","Oct","Nov","Dic"][d.getMonth()]} ${d.getFullYear()} ${d.getHours().toString().padStart(2,"0")}:${d.getMinutes().toString().padStart(2,"0")}`;
}

function fmtDia(iso: string) {
  const d = new Date(iso);
  return `${d.getDate()} ${["Ene","Feb","Mar","Abr","May","Jun","Jul","Ago","Sep","Oct","Nov","Dic"][d.getMonth()]}`;
}

function fmtMoney(n: number, moneda = "CLP") {
  return moneda === "CLP"
    ? `$${Math.round(n).toLocaleString("es-CL")}`
    : `${n.toLocaleString("en-US", { minimumFractionDigits: 2 })} ${moneda}`;
}

type Tab = "comparador" | "enviados" | "respondidos";

export default function CotizacionDetallePage() {
  const { id } = useParams<{ id: string }>();
  const [cotizacion, setCotizacion] = useState<Cotizacion | null>(null);
  const [resultados, setResultados] = useState<Resultado[]>([]);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState<Tab>("comparador");

  // Modal de respuesta
  const [modalResp, setModalResp] = useState<Resultado | null>(null);
  const [formResp, setFormResp] = useState({
    precio_cotizado: "", moneda_cotizada: "CLP",
    plazo_entrega: "", condiciones_pago: "",
    tipo_proveedor: "desconocido", notas_respuesta: "",
  });
  const [guardando, setGuardando] = useState(false);
  const [toast, setToast] = useState("");
  // Tasas de cambio (base USD) para comparar precios en distintas monedas
  const [tasas, setTasas] = useState<Record<string, number>>({});

  const cargar = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch(`${API_URL}/api/cotizaciones/${id}/detalle`);
      if (res.ok) {
        const data = await res.json();
        setCotizacion(data.cotizacion);
        setResultados(data.resultados);
      }
    } catch { /* silent */ }
    setLoading(false);
  }, [id]);

  useEffect(() => { cargar(); }, [cargar]);

  useEffect(() => {
    fetch("https://open.er-api.com/v6/latest/USD")
      .then(r => r.json())
      .then(d => { if (d.rates) setTasas(d.rates); })
      .catch(() => setTasas({ CLP: 950, EUR: 0.92, CNY: 7.25, GBP: 0.79 }));
  }, []);

  // Convierte cualquier moneda a CLP para poder comparar precios entre sí
  const aCLP = useCallback((valor: number, moneda: string | null | undefined): number => {
    const m = moneda || "CLP";
    if (m === "CLP") return valor;
    const porUSD = tasas[m] ?? 1;            // unidades de m por 1 USD
    const clpPorUSD = tasas.CLP ?? 950;
    return (valor / porUSD) * clpPorUSD;
  }, [tasas]);

  const handleGuardarRespuesta = async () => {
    if (!modalResp) return;
    setGuardando(true);
    try {
      const body: Record<string, unknown> = {
        tipo_proveedor: formResp.tipo_proveedor,
      };
      if (formResp.precio_cotizado) body.precio_cotizado = parseFloat(formResp.precio_cotizado);
      if (formResp.moneda_cotizada) body.moneda_cotizada = formResp.moneda_cotizada;
      if (formResp.plazo_entrega) body.plazo_entrega = formResp.plazo_entrega;
      if (formResp.condiciones_pago) body.condiciones_pago = formResp.condiciones_pago;
      if (formResp.notas_respuesta) body.notas_respuesta = formResp.notas_respuesta;

      const res = await fetch(`${API_URL}/api/resultados/${modalResp.id}/respuesta`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!res.ok) throw new Error();
      setToast("Respuesta registrada correctamente");
      setTimeout(() => setToast(""), 3000);
      setModalResp(null);
      await cargar();
    } catch {
      setToast("Error al guardar");
      setTimeout(() => setToast(""), 3000);
    } finally { setGuardando(false); }
  };

  const handleQuitar = async (r: Resultado) => {
    try {
      await fetch(`${API_URL}/api/resultados/${r.id}/descartar`, { method: "POST" });
      setToast(`${r.proveedor_nombre} quitado del comparador`);
      setTimeout(() => setToast(""), 3000);
      await cargar();
    } catch {
      setToast("No se pudo quitar");
      setTimeout(() => setToast(""), 3000);
    }
  };

  const abrirModalRespuesta = (r: Resultado) => {
    setFormResp({
      precio_cotizado: r.precio_cotizado?.toString() ?? "",
      moneda_cotizada: "CLP",
      plazo_entrega: r.plazo_entrega ?? "",
      condiciones_pago: r.condiciones_pago ?? "",
      tipo_proveedor: r.tipo_proveedor ?? "desconocido",
      notas_respuesta: r.notas_respuesta ?? "",
    });
    setModalResp(r);
  };

  const inputSt: React.CSSProperties = {
    background: "var(--bg-base)", border: "1px solid var(--border-default)",
    padding: "8px 12px", fontSize: 11, color: "var(--text-primary)",
    fontFamily: "var(--font-mono)", outline: "none", width: "100%",
  };

  const tabBtn = (t: Tab): React.CSSProperties => ({
    padding: "8px 16px", fontSize: 10, fontWeight: 700, letterSpacing: "0.04em",
    cursor: "pointer", fontFamily: "var(--font-mono)",
    background: tab === t ? "var(--bg-inverse)" : "var(--bg-surface)",
    color: tab === t ? "var(--text-inverse)" : "var(--text-muted)",
    border: "none", borderBottom: "none",
  });

  // Subsets
  const enviados = resultados.filter(r => r.solicitud_enviada_at);
  const respondidos = resultados.filter(r => r.respuesta_recibida_at);
  // Al comparador van solo los seleccionados/relevantes; los descartados quedan ocultos
  const descartados = resultados.filter(r => r.relevante === false && !r.solicitud_enviada_at);
  const comparador = resultados
    .filter(r => r.relevante !== false || r.solicitud_enviada_at)
    .sort((a, b) => b.ranking_score - a.ranking_score);

  if (loading) {
    return <div style={{ padding: "60px 0", textAlign: "center", fontSize: 12, color: "var(--text-muted)" }}>Cargando...</div>;
  }

  return (
    <>
      {toast && (
        <div style={{
          position: "fixed", top: 20, right: 20, zIndex: 999,
          background: "var(--bg-inverse)", color: "var(--text-inverse)",
          padding: "12px 20px", fontSize: 11, fontWeight: 700,
          border: "1px solid var(--border-strong)",
        }}>{toast}</div>
      )}

      {/* Modal respuesta */}
      {modalResp && (
        <div style={{
          position: "fixed", inset: 0, background: "rgba(0,0,0,0.55)", zIndex: 500,
          display: "flex", alignItems: "center", justifyContent: "center", padding: 20,
        }} onClick={() => setModalResp(null)}>
          <div style={{
            background: "var(--bg-surface)", border: "1px solid var(--border-default)",
            padding: 28, width: "100%", maxWidth: 440,
          }} onClick={e => e.stopPropagation()}>
            <div style={{ fontSize: 9, fontWeight: 700, color: "var(--text-muted)", letterSpacing: "0.06em", marginBottom: 4 }}>
              REGISTRAR / ACTUALIZAR RESPUESTA
            </div>
            <div style={{ fontSize: 14, fontWeight: 700, color: "var(--text-primary)", marginBottom: 4 }}>
              {modalResp.proveedor_nombre}
            </div>
            {modalResp.proveedor_email && (
              <div style={{ fontSize: 10, color: "var(--text-muted)", fontFamily: "var(--font-mono)", marginBottom: 20 }}>
                {modalResp.proveedor_email}
              </div>
            )}

            <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
              <div>
                <div style={{ fontSize: 9, fontWeight: 700, color: "var(--text-muted)", letterSpacing: "0.06em", marginBottom: 4 }}>PRECIO COTIZADO</div>
                <div style={{ display: "flex", gap: 8 }}>
                  <input type="number" placeholder="Ej: 45000" value={formResp.precio_cotizado}
                    onChange={e => setFormResp(p => ({ ...p, precio_cotizado: e.target.value }))}
                    style={{ ...inputSt, flex: 1 }} />
                  <select value={formResp.moneda_cotizada}
                    onChange={e => setFormResp(p => ({ ...p, moneda_cotizada: e.target.value }))}
                    style={{ ...inputSt, width: "auto" }}>
                    {["CLP", "USD", "EUR"].map(m => <option key={m}>{m}</option>)}
                  </select>
                </div>
              </div>

              <div>
                <div style={{ fontSize: 9, fontWeight: 700, color: "var(--text-muted)", letterSpacing: "0.06em", marginBottom: 4 }}>PLAZO DE ENTREGA</div>
                <input type="text" placeholder="Ej: 5 días hábiles, 2 semanas..." value={formResp.plazo_entrega}
                  onChange={e => setFormResp(p => ({ ...p, plazo_entrega: e.target.value }))} style={inputSt} />
              </div>

              <div>
                <div style={{ fontSize: 9, fontWeight: 700, color: "var(--text-muted)", letterSpacing: "0.06em", marginBottom: 4 }}>CONDICIONES DE PAGO</div>
                <input type="text" placeholder="Ej: 30 días neto, contado, transferencia..." value={formResp.condiciones_pago}
                  onChange={e => setFormResp(p => ({ ...p, condiciones_pago: e.target.value }))} style={inputSt} />
              </div>

              <div>
                <div style={{ fontSize: 9, fontWeight: 700, color: "var(--text-muted)", letterSpacing: "0.06em", marginBottom: 4 }}>TIPO DE PROVEEDOR</div>
                <select value={formResp.tipo_proveedor}
                  onChange={e => setFormResp(p => ({ ...p, tipo_proveedor: e.target.value }))}
                  style={inputSt}>
                  {Object.entries(TIPO_PROVEEDOR_LABELS).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                </select>
              </div>

              <div>
                <div style={{ fontSize: 9, fontWeight: 700, color: "var(--text-muted)", letterSpacing: "0.06em", marginBottom: 4 }}>NOTAS DE LA RESPUESTA</div>
                <textarea placeholder="Copia aquí lo que respondió el proveedor o añade notas..." value={formResp.notas_respuesta}
                  onChange={e => setFormResp(p => ({ ...p, notas_respuesta: e.target.value }))}
                  rows={3} style={{ ...inputSt, resize: "vertical" }} />
              </div>
            </div>

            <div style={{ display: "flex", gap: 8, marginTop: 20 }}>
              <button onClick={handleGuardarRespuesta} disabled={guardando} className="btn-swiss-primary" style={{ flex: 1 }}>
                {guardando ? "Guardando..." : "GUARDAR RESPUESTA"}
              </button>
              <button onClick={() => setModalResp(null)} className="btn-swiss-secondary">Cancelar</button>
            </div>
          </div>
        </div>
      )}

      {/* Header */}
      <div style={{ marginBottom: 24 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12 }}>
          <Link href="/cotizaciones" style={{ fontSize: 10, color: "var(--text-muted)", textDecoration: "none", fontFamily: "var(--font-mono)" }}>
            ← Cotizaciones
          </Link>
        </div>
        <div className="section-rule" style={{ marginBottom: 14 }} />
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 16 }}>
          <div>
            <h1 style={{ fontSize: 22, fontWeight: 700, color: "var(--text-primary)", margin: "0 0 6px", letterSpacing: "-0.02em" }}>
              {cotizacion?.nombre_identificado ?? "—"}
            </h1>
            <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
              {cotizacion?.categoria && (
                <span style={{ fontSize: 9, fontWeight: 700, color: "var(--text-muted)", border: "1px solid var(--border-default)", padding: "2px 8px" }}>
                  {cotizacion.categoria.toUpperCase()}
                </span>
              )}
              {cotizacion?.marca && (
                <span style={{ fontSize: 10, color: "var(--text-secondary)", fontFamily: "var(--font-mono)" }}>{cotizacion.marca}</span>
              )}
              {cotizacion?.numero_parte && (
                <span style={{ fontSize: 9, color: "var(--text-muted)", fontFamily: "var(--font-mono)" }}>N/P: {cotizacion.numero_parte}</span>
              )}
              {cotizacion?.created_at && (
                <span style={{ fontSize: 10, color: "var(--text-muted)" }}>{fmtDia(cotizacion.created_at)}</span>
              )}
            </div>
          </div>
          <div style={{ display: "flex", gap: 8, alignItems: "flex-start" }}>
            <InformeCotizacion cotizacionId={id} nombreItem={cotizacion?.nombre_identificado ?? ""} />
            <Link href={`/cotizar/${id}/resultados`} className="btn-swiss-secondary" style={{ textDecoration: "none", fontSize: 10, whiteSpace: "nowrap" }}>
              REBUSCAR PROVEEDORES →
            </Link>
          </div>
        </div>
      </div>

      {/* Stats */}
      <div style={{
        display: "grid", gridTemplateColumns: "repeat(4, 1fr)",
        border: "1px solid var(--border-default)", marginBottom: 0,
      }}>
        {([
          {
            label: "SELECCIONADOS",
            val: comparador.length as number | string,
            color: undefined as string | undefined,
            sub: descartados.length > 0 ? `de ${resultados.length} encontrados` : undefined,
          },
          { label: "CORREOS ENVIADOS", val: enviados.length, color: enviados.length > 0 ? "#2980b9" : undefined, sub: undefined },
          { label: "RESPONDIERON", val: respondidos.length, color: respondidos.length > 0 ? "var(--text-success)" : undefined, sub: undefined },
          {
            label: "MEJOR PRECIO",
            // solo sobre los seleccionados, todo convertido a CLP
            val: (() => {
              const ps = comparador
                .map(r => r.precio_cotizado != null ? r.precio_cotizado : (r.precio != null ? aCLP(r.precio, r.moneda) : null))
                .filter((p): p is number => p != null);
              return ps.length ? `$${Math.round(Math.min(...ps)).toLocaleString("es-CL")}` : "—";
            })(),
            color: undefined,
            sub: comparador.some(r => r.moneda && r.moneda !== "CLP" && r.precio != null && r.precio_cotizado == null)
              ? "convertido a CLP" : undefined,
          },
        ]).map((s, i) => (
          <div key={i} style={{
            background: "var(--bg-surface)",
            borderRight: i < 3 ? "1px solid var(--border-default)" : "none",
            padding: "16px 20px",
          }}>
            <div style={{ fontSize: 9, fontWeight: 700, color: "var(--text-muted)", letterSpacing: "0.06em", marginBottom: 8 }}>{s.label}</div>
            <div style={{ fontSize: 24, fontWeight: 700, color: s.color ?? "var(--text-primary)", letterSpacing: "-0.02em" }}>{s.val}</div>
            {s.sub && (
              <div style={{ fontSize: 9, color: "var(--text-muted)", marginTop: 4, fontFamily: "var(--font-mono)" }}>{s.sub}</div>
            )}
          </div>
        ))}
      </div>

      {/* Tabs */}
      <div style={{ display: "flex", borderBottom: "1px solid var(--border-default)", background: "var(--bg-surface)", marginBottom: 20 }}>
        <button style={tabBtn("comparador")} onClick={() => setTab("comparador")}>
          COMPARADOR ({comparador.length})
        </button>
        <button style={tabBtn("enviados")} onClick={() => setTab("enviados")}>
          CORREOS ENVIADOS ({enviados.length})
        </button>
        <button style={tabBtn("respondidos")} onClick={() => setTab("respondidos")}>
          RESPONDIDOS ({respondidos.length})
        </button>
      </div>

      {/* ── TAB COMPARADOR ───────────────────────────────────────────────────── */}
      {tab === "comparador" && (
        <>
        <div style={{ border: "1px solid var(--border-default)", background: "var(--bg-surface)" }}>
          {/* cabecera */}
          <div style={{
            display: "grid",
            gridTemplateColumns: "32px 1.3fr 105px 105px 100px 120px 150px 60px 34px",
            padding: "9px 16px",
            borderBottom: "1px solid var(--border-default)",
            background: "var(--bg-base)",
          }}>
            {["#", "PROVEEDOR / PÁGINA", "PRECIO BÚSQ.", "PRECIO COT.", "ENTREGA", "UBICACIÓN", "CONTACTO", "ORIGEN", ""].map((h, hi) => (
              <div key={hi} style={{ fontSize: 9, fontWeight: 700, color: "var(--text-muted)", letterSpacing: "0.06em" }}>{h}</div>
            ))}
          </div>

          {comparador.length === 0 ? (
            <div style={{ padding: "40px 0", textAlign: "center", fontSize: 12, color: "var(--text-muted)" }}>
              Sin resultados. <Link href={`/cotizar/${id}/resultados`} style={{ color: "var(--accent)" }}>Buscar proveedores →</Link>
            </div>
          ) : comparador.map((r, i) => {
            const meta = parseMeta(r);
            const ubicacion = (meta.ubicacion_vendedor as string)
              ?? (r.pais === "CL" ? "Chile" : r.pais || "—");
            const entrega = r.plazo_entrega ?? (meta.plazo_entrega_estimado as string) ?? "—";
            return (
            <div key={r.id} style={{
              display: "grid",
              gridTemplateColumns: "32px 1.3fr 105px 105px 100px 120px 150px 60px 34px",
              padding: "11px 16px",
              borderBottom: i < comparador.length - 1 ? "1px solid var(--border-subtle)" : "none",
              alignItems: "center",
              background: i === 0 && r.precio != null ? "var(--fill-success)" : undefined,
            }}>
              <div style={{ fontSize: 10, fontWeight: 700, color: i === 0 ? "var(--text-success)" : "var(--text-muted)" }}>
                #{i + 1}
              </div>
              <div>
                {r.url ? (
                  <a href={r.url} target="_blank" rel="noopener noreferrer"
                    title="Ver publicación del proveedor"
                    style={{ fontSize: 11, fontWeight: 700, color: "var(--text-primary)", textDecoration: "none" }}
                    onMouseEnter={e => (e.currentTarget.style.color = "var(--accent)")}
                    onMouseLeave={e => (e.currentTarget.style.color = "var(--text-primary)")}>
                    {r.proveedor_nombre} ↗
                  </a>
                ) : (
                  <div style={{ fontSize: 11, fontWeight: 700, color: "var(--text-primary)" }}>{r.proveedor_nombre}</div>
                )}
                <div>
                  {r.url && (
                    <a href={r.url} target="_blank" rel="noopener noreferrer"
                      style={{ fontSize: 9, color: "var(--accent)", textDecoration: "none" }}>
                      {FUENTE_LABEL[(meta.fuente_label as string) ?? r.fuente] ?? (meta.fuente_label as string) ?? r.fuente} →
                    </a>
                  )}
                  {r.respuesta_recibida_at && (
                    <span style={{ fontSize: 9, color: "var(--text-success)", marginLeft: 8 }}>● respondió</span>
                  )}
                </div>
              </div>
              <div style={{ fontSize: 11, color: "var(--text-secondary)" }}>
                {r.precio != null ? fmtMoney(r.precio, r.moneda) : "—"}
              </div>
              <div style={{ fontSize: 11, fontWeight: r.precio_cotizado != null ? 700 : 400, color: r.precio_cotizado != null ? "var(--text-primary)" : "var(--text-muted)" }}>
                {r.precio_cotizado != null ? fmtMoney(r.precio_cotizado, "CLP") : "—"}
              </div>
              <div style={{ fontSize: 10, color: "var(--text-secondary)" }}>{entrega}</div>
              <div style={{ fontSize: 10, color: "var(--text-secondary)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={ubicacion}>
                {ubicacion}
              </div>
              <div style={{ fontSize: 9, fontFamily: "var(--font-mono)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {r.proveedor_email ? (
                  <a href={`mailto:${r.proveedor_email}`} style={{ color: "var(--accent)", textDecoration: "none" }} title={r.proveedor_email}>
                    {r.proveedor_email}
                  </a>
                ) : r.url ? (
                  <span style={{ color: "var(--text-muted)" }}>vía web</span>
                ) : "—"}
              </div>
              <div>
                <span style={{
                  fontSize: 9, fontWeight: 700,
                  color: r.compra_nacional ? "var(--text-success)" : "#92400e",
                  border: `1px solid ${r.compra_nacional ? "var(--text-success)" : "#92400e"}`,
                  padding: "2px 5px",
                }}>
                  {r.compra_nacional ? "NAC." : "IMP."}
                </span>
              </div>
              <div style={{ textAlign: "right" }}>
                {!r.solicitud_enviada_at && (
                  <button
                    onClick={() => handleQuitar(r)}
                    title="Quitar del comparador"
                    style={{
                      background: "none", border: "1px solid var(--border-default)",
                      color: "var(--text-muted)", cursor: "pointer",
                      width: 22, height: 22, fontSize: 12, lineHeight: 1, padding: 0,
                      fontFamily: "var(--font-mono)",
                    }}
                    onMouseEnter={e => { e.currentTarget.style.color = "var(--accent)"; e.currentTarget.style.borderColor = "var(--accent)"; }}
                    onMouseLeave={e => { e.currentTarget.style.color = "var(--text-muted)"; e.currentTarget.style.borderColor = "var(--border-default)"; }}
                  >
                    ×
                  </button>
                )}
              </div>
            </div>
            );
          })}
        </div>

        {descartados.length > 0 && (
          <div className="label" style={{ color: "var(--text-muted)", marginTop: 10 }}>
            {descartados.length} resultado{descartados.length !== 1 ? "s" : ""} no seleccionado{descartados.length !== 1 ? "s" : ""} — {" "}
            <Link href={`/cotizar/${id}/resultados`} style={{ color: "var(--accent)" }}>
              volver a la búsqueda para cambiar la selección →
            </Link>
          </div>
        )}
        </>
      )}

      {/* ── TAB CORREOS ENVIADOS ─────────────────────────────────────────────── */}
      {tab === "enviados" && (
        <div>
          {enviados.length === 0 ? (
            <div style={{ padding: "40px 0", textAlign: "center" }}>
              <div style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 12 }}>No se han enviado correos para esta cotización.</div>
              <Link href={`/cotizar/${id}/resultados`} style={{ fontSize: 11, color: "var(--accent)" }}>
                Ir a resultados para enviar →
              </Link>
            </div>
          ) : (
            <div style={{ border: "1px solid var(--border-default)", background: "var(--bg-surface)" }}>
              {/* Cabecera */}
              <div style={{
                display: "grid", gridTemplateColumns: "1fr 180px 160px 120px",
                padding: "9px 16px", borderBottom: "1px solid var(--border-default)",
                background: "var(--bg-base)",
              }}>
                {["PROVEEDOR", "EMAIL ENVIADO A", "FECHA ENVÍO", "ESTADO"].map(h => (
                  <div key={h} style={{ fontSize: 9, fontWeight: 700, color: "var(--text-muted)", letterSpacing: "0.06em" }}>{h}</div>
                ))}
              </div>
              {enviados.map((r, i) => (
                <div key={r.id} style={{
                  display: "grid", gridTemplateColumns: "1fr 180px 160px 120px",
                  padding: "12px 16px",
                  borderBottom: i < enviados.length - 1 ? "1px solid var(--border-subtle)" : "none",
                  alignItems: "center",
                  background: r.respuesta_recibida_at ? "var(--fill-success)" : undefined,
                }}>
                  <div>
                    <div style={{ fontSize: 12, fontWeight: 700, color: "var(--text-primary)", marginBottom: 2 }}>{r.proveedor_nombre}</div>
                    {r.url && (
                      <a href={r.url} target="_blank" rel="noopener noreferrer"
                        style={{ fontSize: 9, color: "var(--accent)", textDecoration: "none" }}>
                        {FUENTE_LABEL[r.fuente] ?? r.fuente}
                      </a>
                    )}
                  </div>
                  <div style={{ fontSize: 11, color: "var(--text-secondary)", fontFamily: "var(--font-mono)", wordBreak: "break-all" }}>
                    {r.proveedor_email || "—"}
                  </div>
                  <div style={{ fontSize: 11, color: "var(--text-muted)" }}>
                    {r.solicitud_enviada_at ? fmtFecha(r.solicitud_enviada_at) : "—"}
                  </div>
                  <div>
                    {r.respuesta_recibida_at ? (
                      <span style={{ fontSize: 9, fontWeight: 700, color: "var(--text-success)", border: "1px solid var(--text-success)", padding: "2px 7px" }}>
                        RESPONDIÓ
                      </span>
                    ) : (
                      <span style={{ fontSize: 9, color: "#2980b9", border: "1px solid #2980b9", padding: "2px 7px" }}>
                        ENVIADO
                      </span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* ── TAB RESPONDIDOS ──────────────────────────────────────────────────── */}
      {tab === "respondidos" && (
        <div>
          {respondidos.length === 0 ? (
            <div style={{ padding: "40px 0", textAlign: "center" }}>
              <div style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 12 }}>
                {enviados.length > 0
                  ? `Se enviaron ${enviados.length} correos. Aquí aparecerán los que respondan.`
                  : "Aún no hay correos enviados."}
              </div>
              {enviados.length > 0 && (
                <p style={{ fontSize: 11, color: "var(--text-muted)", maxWidth: 380, margin: "0 auto" }}>
                  Cuando un proveedor responda, ingresa manualmente su respuesta con el botón de abajo, o haz clic en "Registrar respuesta" en la pestaña de Correos Enviados.
                </p>
              )}
            </div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
              {respondidos.map(r => (
                <div key={r.id} style={{
                  border: "1px solid var(--border-default)",
                  borderLeft: "3px solid var(--text-success)",
                  background: "var(--bg-surface)",
                  padding: "20px 24px",
                }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 16 }}>
                    <div>
                      <div style={{ fontSize: 13, fontWeight: 700, color: "var(--text-primary)", marginBottom: 2 }}>
                        {r.proveedor_nombre}
                      </div>
                      <div style={{ fontSize: 10, color: "var(--text-muted)", fontFamily: "var(--font-mono)" }}>
                        {r.proveedor_email} · Respondió {r.respuesta_recibida_at ? fmtFecha(r.respuesta_recibida_at) : ""}
                      </div>
                    </div>
                    <button
                      onClick={() => abrirModalRespuesta(r)}
                      className="btn-swiss-secondary"
                      style={{ fontSize: 10, padding: "5px 12px" }}
                    >
                      EDITAR RESPUESTA
                    </button>
                  </div>

                  <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 16, marginBottom: r.notas_respuesta ? 16 : 0 }}>
                    {[
                      { label: "PRECIO COTIZADO", val: r.precio_cotizado != null ? fmtMoney(r.precio_cotizado, "CLP") : "—", highlight: true },
                      { label: "PLAZO ENTREGA", val: r.plazo_entrega || "—" },
                      { label: "CONDICIONES PAGO", val: r.condiciones_pago || "—" },
                      { label: "TIPO PROVEEDOR", val: TIPO_PROVEEDOR_LABELS[r.tipo_proveedor] ?? r.tipo_proveedor },
                    ].map(s => (
                      <div key={s.label} style={{ background: "var(--bg-base)", border: "1px solid var(--border-default)", padding: "10px 14px" }}>
                        <div style={{ fontSize: 9, fontWeight: 700, color: "var(--text-muted)", letterSpacing: "0.06em", marginBottom: 4 }}>{s.label}</div>
                        <div style={{ fontSize: 13, fontWeight: s.highlight ? 700 : 400, color: s.highlight && r.precio_cotizado ? "var(--accent)" : "var(--text-primary)" }}>
                          {s.val}
                        </div>
                      </div>
                    ))}
                  </div>

                  {r.notas_respuesta && (
                    <div style={{ background: "var(--bg-base)", border: "1px solid var(--border-default)", padding: "12px 14px" }}>
                      <div style={{ fontSize: 9, fontWeight: 700, color: "var(--text-muted)", letterSpacing: "0.06em", marginBottom: 4 }}>NOTAS / RESPUESTA DEL PROVEEDOR</div>
                      <div style={{ fontSize: 11, color: "var(--text-secondary)", whiteSpace: "pre-wrap", lineHeight: 1.6 }}>{r.notas_respuesta}</div>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}

          {/* Botón para registrar respuesta de enviados aún pendientes */}
          {enviados.filter(r => !r.respuesta_recibida_at).length > 0 && (
            <div style={{ marginTop: 24, borderTop: "1px solid var(--border-default)", paddingTop: 16 }}>
              <div style={{ fontSize: 9, fontWeight: 700, color: "var(--text-muted)", letterSpacing: "0.06em", marginBottom: 12 }}>
                CORREOS AÚN SIN RESPUESTA — Registrar manualmente
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                {enviados.filter(r => !r.respuesta_recibida_at).map(r => (
                  <div key={r.id} style={{
                    display: "flex", justifyContent: "space-between", alignItems: "center",
                    background: "var(--bg-surface)", border: "1px solid var(--border-default)",
                    padding: "12px 16px",
                  }}>
                    <div>
                      <div style={{ fontSize: 12, fontWeight: 700, color: "var(--text-primary)" }}>{r.proveedor_nombre}</div>
                      <div style={{ fontSize: 10, color: "var(--text-muted)", fontFamily: "var(--font-mono)" }}>
                        {r.proveedor_email} · Enviado {r.solicitud_enviada_at ? fmtDia(r.solicitud_enviada_at) : ""}
                      </div>
                    </div>
                    <button
                      onClick={() => abrirModalRespuesta(r)}
                      style={{
                        fontSize: 10, fontWeight: 700, cursor: "pointer",
                        background: "none", border: "1px solid var(--accent)",
                        color: "var(--accent)", padding: "6px 14px",
                        fontFamily: "var(--font-mono)", letterSpacing: "0.04em",
                      }}
                    >
                      + REGISTRAR RESPUESTA
                    </button>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </>
  );
}
