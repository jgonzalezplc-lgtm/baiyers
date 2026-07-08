"use client";
import { useState } from "react";
import { pdf } from "@react-pdf/renderer";
import OCPDFTemplate, { type OCData } from "./OCPDFTemplate";
import type { Resultado } from "@/app/cotizar/components/CardProveedor";

interface Props {
  resultado: Resultado;
  nombreItem: string;
  cotizacionId: string;
  userId: string;
  plan: string;
  onClose: () => void;
  onEnviada: (numeroOc: string) => void;
}

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

function fmt(n: number, moneda: string) {
  if (moneda === "CLP") return `$${Math.round(n).toLocaleString("es-CL")}`;
  return `${moneda} ${n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

const labelStyle: React.CSSProperties = {
  display: "block",
  fontSize: 10,
  color: "var(--text-muted)",
  textTransform: "uppercase",
  letterSpacing: "0.1em",
  marginBottom: 6,
  fontFamily: "var(--font-mono)",
};

const inputStyle: React.CSSProperties = {
  width: "100%",
  padding: "9px 12px",
  background: "var(--bg-base)",
  border: "1px solid var(--border-default)",
  color: "var(--text-primary)",
  fontSize: 12,
  outline: "none",
  fontFamily: "var(--font-mono)",
  boxSizing: "border-box",
};

export default function OCModal({ resultado, nombreItem, cotizacionId, userId, plan, onClose, onEnviada }: Props) {
  const proveedorNombre = resultado.proveedor || resultado.titulo;
  const [cantidad, setCantidad] = useState(1);
  const [precioUnitario, setPrecioUnitario] = useState(resultado.precio ?? 0);
  const [moneda, setMoneda] = useState(resultado.moneda || "CLP");
  const [condicionesPago, setCondicionesPago] = useState("30 dias");
  const [plazoEntrega, setPlazoEntrega] = useState("");
  const [notas, setNotas] = useState("");
  const [email, setEmail] = useState("");

  const [paso, setPaso] = useState<"form" | "preview" | "enviado">("form");
  const [ocData, setOcData] = useState<OCData | null>(null);
  const [ocId, setOcId] = useState("");
  const [pdfBlob, setPdfBlob] = useState<Blob | null>(null);
  const [pdfUrl, setPdfUrl] = useState("");
  const [generando, setGenerando] = useState(false);
  const [enviando, setEnviando] = useState(false);
  const [error, setError] = useState("");

  // Bloqueo por plan
  if (plan === "free" || plan === "starter") {
    return (
      <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.6)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 1000, padding: 16 }}>
        <div style={{ background: "var(--bg-surface)", border: "1px solid var(--border-default)", padding: 32, maxWidth: 400, width: "100%", textAlign: "center" }}>
          <div className="section-rule" style={{ margin: "0 auto 16px" }} />
          <h2 style={{ fontSize: 16, fontWeight: 700, color: "var(--text-primary)", marginBottom: 8, letterSpacing: "-0.01em" }}>OC Automatica</h2>
          <p style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 24 }}>
            La emision de Ordenes de Compra esta disponible desde el plan <strong style={{ color: "var(--accent)" }}>Pro</strong>.
          </p>
          <div style={{ display: "flex", gap: 8 }}>
            <button onClick={onClose} className="btn-swiss-secondary" style={{ flex: 1 }}>Cancelar</button>
            <a href="/pricing" className="btn-swiss-primary" style={{ flex: 1, textDecoration: "none", textAlign: "center" }}>Ver planes</a>
          </div>
        </div>
      </div>
    );
  }

  const subtotal = cantidad * precioUnitario;
  const iva = Math.round(subtotal * 0.19);
  const total = subtotal + iva;

  const handleGenerar = async () => {
    setGenerando(true);
    setError("");
    try {
      const res = await fetch(`${API_URL}/api/oc/crear`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          cotizacion_id: cotizacionId,
          user_id: userId,
          nombre_item: nombreItem,
          proveedor_nombre: proveedorNombre,
          proveedor_email: email || null,
          cantidad,
          precio_unitario: precioUnitario,
          moneda,
          condiciones_pago: condicionesPago,
          plazo_entrega: plazoEntrega,
          notas: notas || null,
        }),
      });
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      setOcData(data);
      setOcId(data.id);

      const blob = await pdf(<OCPDFTemplate oc={data} />).toBlob();
      setPdfBlob(blob);
      setPdfUrl(URL.createObjectURL(blob));
      setPaso("preview");
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Error generando OC");
    } finally {
      setGenerando(false);
    }
  };

  const handleEnviar = async () => {
    if (!ocData || !pdfBlob) return;
    setEnviando(true);
    setError("");
    try {
      const arrayBuffer = await pdfBlob.arrayBuffer();
      const uint8 = new Uint8Array(arrayBuffer);
      let binary = "";
      uint8.forEach(b => binary += String.fromCharCode(b));
      const base64 = btoa(binary);

      const res = await fetch(`${API_URL}/api/oc/enviar`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          oc_id: ocId,
          pdf_base64: base64,
          user_id: userId,
          proveedor_nombre: proveedorNombre,
          proveedor_email: email || null,
          numero_oc: ocData.numero_oc,
          precio_total: ocData.total,
          moneda: ocData.moneda,
        }),
      });
      if (!res.ok) throw new Error(await res.text());
      setPaso("enviado");
      onEnviada(ocData.numero_oc);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Error enviando OC");
    } finally {
      setEnviando(false);
    }
  };

  return (
    <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.6)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 1000, padding: 16 }}>
      <div style={{ width: "100%", maxWidth: 560, background: "var(--bg-surface)", border: "1px solid var(--border-default)", overflow: "hidden", maxHeight: "90vh", display: "flex", flexDirection: "column" }}>

        {/* Header */}
        <div style={{ padding: "16px 20px", borderBottom: "1px solid var(--border-default)", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <div>
            <span className="label" style={{ color: "var(--accent)", display: "block", marginBottom: 2 }}>Orden de Compra</span>
            <h2 style={{ fontSize: 15, fontWeight: 700, color: "var(--text-primary)", margin: 0, letterSpacing: "-0.01em" }}>
              {paso === "form" ? "Emitir OC" : paso === "preview" ? `Preview — ${ocData?.numero_oc}` : "OC Enviada"}
            </h2>
          </div>
          <button onClick={onClose} style={{ background: "none", border: "none", color: "var(--text-muted)", cursor: "pointer", fontSize: 18 }}>✕</button>
        </div>

        <div style={{ flex: 1, overflow: "auto", padding: "16px 20px" }}>

          {/* PASO: FORM */}
          {paso === "form" && (
            <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
              <div style={{ background: "var(--bg-base)", border: "1px solid var(--border-default)", padding: "10px 14px", fontSize: 11, color: "var(--text-secondary)" }}>
                Proveedor: <strong style={{ color: "var(--text-primary)" }}>{proveedorNombre}</strong>
                {resultado.precio && <span style={{ marginLeft: 12, color: "var(--text-success)" }}>{fmt(resultado.precio, moneda)}</span>}
              </div>

              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 80px", gap: 12 }}>
                <div>
                  <label style={labelStyle}>Cantidad</label>
                  <input type="number" min={1} value={cantidad} onChange={e => setCantidad(Number(e.target.value))} style={inputStyle} />
                </div>
                <div>
                  <label style={labelStyle}>Precio unitario</label>
                  <input type="number" min={0} value={precioUnitario} onChange={e => setPrecioUnitario(Number(e.target.value))} style={inputStyle} />
                </div>
                <div>
                  <label style={labelStyle}>Moneda</label>
                  <select value={moneda} onChange={e => setMoneda(e.target.value)} style={inputStyle}>
                    <option value="CLP">CLP</option>
                    <option value="USD">USD</option>
                    <option value="EUR">EUR</option>
                    <option value="CNY">CNY</option>
                  </select>
                </div>
              </div>

              <div>
                <label style={labelStyle}>Condiciones de pago</label>
                <select value={condicionesPago} onChange={e => setCondicionesPago(e.target.value)} style={inputStyle}>
                  <option>Contado</option>
                  <option>30 dias</option>
                  <option>60 dias</option>
                  <option>90 dias</option>
                </select>
              </div>

              <div>
                <label style={labelStyle}>Plazo de entrega</label>
                <input type="text" placeholder="Ej: 5 dias habiles" value={plazoEntrega} onChange={e => setPlazoEntrega(e.target.value)} style={inputStyle} />
              </div>

              <div>
                <label style={labelStyle}>Email del proveedor (para envio)</label>
                <input type="email" placeholder="proveedor@empresa.com" value={email} onChange={e => setEmail(e.target.value)} style={inputStyle} />
              </div>

              <div>
                <label style={labelStyle}>Notas adicionales (opcional)</label>
                <textarea value={notas} onChange={e => setNotas(e.target.value)} rows={2} style={{ ...inputStyle, resize: "vertical" }} />
              </div>

              {/* Totales */}
              <div style={{ background: "var(--bg-base)", border: "1px solid var(--border-default)", padding: 14 }}>
                <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11, color: "var(--text-muted)", marginBottom: 4 }}>
                  <span>Subtotal</span><span>{fmt(subtotal, moneda)}</span>
                </div>
                <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11, color: "var(--text-muted)", marginBottom: 8 }}>
                  <span>IVA 19%</span><span>{fmt(iva, moneda)}</span>
                </div>
                <div style={{ display: "flex", justifyContent: "space-between", fontSize: 14, fontWeight: 700, color: "var(--text-primary)", borderTop: "1px solid var(--border-default)", paddingTop: 8 }}>
                  <span>Total</span><span style={{ color: "var(--accent)" }}>{fmt(total, moneda)}</span>
                </div>
              </div>

              {error && (
                <div style={{ fontSize: 11, color: "var(--text-error)", background: "var(--fill-error)", border: "1px solid var(--border-accent)", padding: "8px 12px" }}>
                  {error}
                </div>
              )}
            </div>
          )}

          {/* PASO: PREVIEW */}
          {paso === "preview" && ocData && (
            <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
              <div style={{ background: "var(--bg-base)", border: "1px solid var(--border-default)", padding: 14, fontSize: 11 }}>
                <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 6 }}>
                  <span className="label" style={{ color: "var(--text-muted)" }}>Numero OC</span>
                  <span style={{ color: "var(--text-primary)", fontWeight: 700 }}>{ocData.numero_oc}</span>
                </div>
                <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 6 }}>
                  <span className="label" style={{ color: "var(--text-muted)" }}>Total</span>
                  <span style={{ color: "var(--text-success)", fontWeight: 700, fontSize: 14 }}>{fmt(ocData.total, ocData.moneda)}</span>
                </div>
                <div style={{ display: "flex", justifyContent: "space-between" }}>
                  <span className="label" style={{ color: "var(--text-muted)" }}>Proveedor</span>
                  <span style={{ color: "var(--text-primary)" }}>{ocData.proveedor_nombre}</span>
                </div>
              </div>

              <a href={pdfUrl} download={`${ocData.numero_oc}.pdf`} className="btn-swiss-secondary" style={{ display: "block", textAlign: "center", textDecoration: "none" }}>
                Descargar PDF preview →
              </a>

              {!email && (
                <div style={{ fontSize: 10, color: "var(--text-warning)", background: "var(--fill-warning)", border: "1px solid var(--palette-yellow-500, #ca8a04)", padding: "8px 12px" }}>
                  No ingresaste email del proveedor — la OC se enviara solo a tu copia (hola@claria.cc).
                </div>
              )}

              {error && (
                <div style={{ fontSize: 11, color: "var(--text-error)", background: "var(--fill-error)", border: "1px solid var(--border-accent)", padding: "8px 12px" }}>
                  {error}
                </div>
              )}
            </div>
          )}

          {/* PASO: ENVIADO */}
          {paso === "enviado" && ocData && (
            <div style={{ textAlign: "center", padding: "24px 0" }}>
              <div className="section-rule" style={{ margin: "0 auto 16px", background: "var(--text-success)" }} />
              <h3 style={{ fontSize: 16, fontWeight: 700, color: "var(--text-primary)", marginBottom: 8, letterSpacing: "-0.01em" }}>
                OC enviada exitosamente
              </h3>
              <p className="label" style={{ color: "var(--text-muted)", marginBottom: 4 }}>{ocData.numero_oc}</p>
              <p style={{ fontSize: 11, color: "var(--text-success)" }}>
                {email ? `Email enviado a ${email}` : "Copia enviada a hola@claria.cc"}
              </p>
            </div>
          )}
        </div>

        {/* Footer */}
        <div style={{ padding: "14px 20px", borderTop: "1px solid var(--border-default)", display: "flex", justifyContent: "flex-end", gap: 8, background: "var(--bg-surface)" }}>
          {paso !== "enviado" && (
            <button onClick={onClose} className="btn-swiss-secondary">Cancelar</button>
          )}
          {paso === "form" && (
            <button onClick={handleGenerar} disabled={generando || precioUnitario <= 0} className={generando ? "btn-swiss-secondary" : "btn-swiss-primary"}>
              {generando ? "Generando PDF..." : "Generar OC →"}
            </button>
          )}
          {paso === "preview" && (
            <button onClick={handleEnviar} disabled={enviando} className={enviando ? "btn-swiss-secondary" : "btn-swiss-primary"}>
              {enviando ? "Enviando..." : "Confirmar y enviar OC →"}
            </button>
          )}
          {paso === "enviado" && (
            <button onClick={onClose} className="btn-swiss-primary">Cerrar</button>
          )}
        </div>
      </div>
    </div>
  );
}
