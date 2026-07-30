"use client";
import { useState } from "react";
import { pdf } from "@react-pdf/renderer";
import { FileText, X } from "lucide-react";
import OCPDFTemplate, { type OCData } from "./OCPDFTemplate";
import type { Resultado } from "@/app/cotizar/components/CardProveedor";

interface Props {
  resultado: Resultado;
  nombreItem: string;
  cotizacionId: string;
  userId: string;
  plan: string;
  /** Cantidad pre-cargada — la OC se envía por ese número de unidades. */
  cantidadInicial?: number;
  onClose: () => void;
  onEnviada: (numeroOc: string) => void;
}

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

function fmt(n: number, moneda: string) {
  if (moneda === "CLP") return `$${Math.round(n).toLocaleString("es-CL")}`;
  return `${moneda} ${n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

const labelStyle: React.CSSProperties = {
  fontSize: 13, fontWeight: 500, color: "var(--n-700)",
  display: "block", marginBottom: 6,
};

const inputStyle: React.CSSProperties = {
  width: "100%",
  padding: "10px 12px",
  background: "var(--surface)",
  border: "1px solid var(--n-300)",
  borderRadius: "var(--r-md)",
  color: "var(--n-900)",
  fontSize: 14,
  outline: "none",
  fontFamily: "var(--font-sans)",
  boxSizing: "border-box",
};

export default function OCModal({ resultado, nombreItem, cotizacionId, userId, plan, cantidadInicial, onClose, onEnviada }: Props) {
  const proveedorNombre = resultado.proveedor || resultado.titulo;
  const [cantidad, setCantidad] = useState(cantidadInicial ?? 1);
  const [precioUnitario, setPrecioUnitario] = useState(resultado.precio ?? 0);
  const [moneda, setMoneda] = useState(resultado.moneda || "CLP");
  const [condicionesPago, setCondicionesPago] = useState("30 dias");
  // Precargados desde la cotización/respuesta del proveedor: si ya sabemos el
  // plazo y el email (contacto scrapeado o registrado al cotizar), no hacer
  // que el usuario los vuelva a escribir a mano.
  const [plazoEntrega, setPlazoEntrega] = useState(
    resultado.plazo_entrega || resultado.plazo_entrega_estimado || ""
  );
  const [notas, setNotas] = useState("");
  const [email, setEmail] = useState(
    resultado.proveedor_email || (resultado as unknown as { contacto?: string }).contacto || ""
  );

  const [paso, setPaso] = useState<"form" | "preview" | "enviado">("form");
  const [ocData, setOcData] = useState<OCData | null>(null);
  const [ocId, setOcId] = useState("");
  const [pdfBlob, setPdfBlob] = useState<Blob | null>(null);
  const [pdfUrl, setPdfUrl] = useState("");
  const [generando, setGenerando] = useState(false);
  const [enviando, setEnviando] = useState(false);
  const [error, setError] = useState("");

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
    <div style={{
      position: "fixed", inset: 0, background: "rgba(33,29,24,.4)", backdropFilter: "blur(2px)",
      display: "flex", alignItems: "center", justifyContent: "center", zIndex: 1000, padding: 16,
    }}>
      <div style={{
        width: "100%", maxWidth: 560, background: "var(--surface)",
        borderRadius: "var(--r-xl)", boxShadow: "var(--shadow-modal)",
        overflow: "hidden", maxHeight: "90vh", display: "flex", flexDirection: "column",
      }}>

        {/* Header */}
        <div style={{ padding: "18px 22px", borderBottom: "1px solid var(--n-200)", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <span style={{
              width: 40, height: 40, borderRadius: "var(--r-md)", flexShrink: 0,
              background: "var(--brand-50)", color: "var(--brand)",
              display: "inline-flex", alignItems: "center", justifyContent: "center",
            }}>
              <FileText size={20} strokeWidth={1.75} />
            </span>
            <div>
              <span style={{ fontSize: 12.5, fontWeight: 500, color: "var(--brand)", display: "block" }}>Orden de compra</span>
              <h2 style={{ fontSize: 18, fontWeight: 600, color: "var(--n-900)", margin: 0 }}>
                {paso === "form" ? "Emitir OC" : paso === "preview" ? `Preview · ${ocData?.numero_oc}` : "OC enviada"}
              </h2>
            </div>
          </div>
          <button onClick={onClose} aria-label="Cerrar" style={{ background: "none", border: "none", color: "var(--n-500)", cursor: "pointer", display: "inline-flex", padding: 4 }}>
            <X size={18} strokeWidth={1.75} />
          </button>
        </div>

        <div style={{ flex: 1, overflow: "auto", padding: "18px 22px" }}>

          {/* PASO: FORM */}
          {paso === "form" && (
            <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
              <div style={{
                background: "var(--surface-2)", border: "1px solid var(--n-200)", borderRadius: "var(--r-md)",
                padding: "10px 14px", fontSize: 14,
              }}>
                <span style={{ color: "var(--n-600)" }}>Proveedor: </span>
                <strong style={{ color: "var(--n-900)" }}>{proveedorNombre}</strong>
                {resultado.precio && <span style={{ marginLeft: 12, color: "var(--success)", fontWeight: 600 }}>{fmt(resultado.precio, moneda)}</span>}
              </div>

              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 90px", gap: 12 }}>
                <div>
                  <label style={labelStyle}>Cantidad</label>
                  <input
                    type="text"
                    inputMode="numeric"
                    value={cantidad === 0 ? "" : String(cantidad)}
                    onChange={e => {
                      const digits = e.target.value.replace(/\D/g, "");
                      setCantidad(digits === "" ? 0 : Number(digits));
                    }}
                    style={inputStyle}
                  />
                </div>
                <div>
                  <label style={labelStyle}>Precio unitario</label>
                  <input type="number" min={0} value={precioUnitario} onChange={e => setPrecioUnitario(Number(e.target.value))} style={inputStyle} />
                </div>
                <div>
                  <label style={labelStyle}>Moneda</label>
                  <select value={moneda} onChange={e => setMoneda(e.target.value)} style={{ ...inputStyle, cursor: "pointer" }}>
                    <option value="CLP">CLP</option>
                    <option value="USD">USD</option>
                    <option value="EUR">EUR</option>
                    <option value="CNY">CNY</option>
                  </select>
                </div>
              </div>

              <div>
                <label style={labelStyle}>Condiciones de pago</label>
                <select value={condicionesPago} onChange={e => setCondicionesPago(e.target.value)} style={{ ...inputStyle, cursor: "pointer" }}>
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
                <label style={labelStyle}>Email del proveedor (para envío)</label>
                <input type="email" placeholder="proveedor@empresa.com" value={email} onChange={e => setEmail(e.target.value)} style={inputStyle} />
              </div>

              <div>
                <label style={labelStyle}>Notas adicionales (opcional)</label>
                <textarea value={notas} onChange={e => setNotas(e.target.value)} rows={2} style={{ ...inputStyle, resize: "vertical" }} />
              </div>

              {/* Totales */}
              <div style={{ background: "var(--surface-2)", border: "1px solid var(--n-200)", borderRadius: "var(--r-md)", padding: 14 }}>
                <div style={{ display: "flex", justifyContent: "space-between", fontSize: 13, color: "var(--n-600)", marginBottom: 6 }}>
                  <span>Subtotal</span><span>{fmt(subtotal, moneda)}</span>
                </div>
                <div style={{ display: "flex", justifyContent: "space-between", fontSize: 13, color: "var(--n-600)", marginBottom: 10 }}>
                  <span>IVA 19%</span><span>{fmt(iva, moneda)}</span>
                </div>
                <div style={{ display: "flex", justifyContent: "space-between", fontSize: 15, fontWeight: 600, color: "var(--n-900)", borderTop: "1px solid var(--n-200)", paddingTop: 10 }}>
                  <span>Total</span><span style={{ color: "var(--brand)" }}>{fmt(total, moneda)}</span>
                </div>
              </div>

              {error && (
                <div style={{ fontSize: 13, color: "var(--danger)", background: "var(--st-rechazada-bg)", borderRadius: "var(--r-md)", padding: "10px 12px" }}>
                  {error}
                </div>
              )}
            </div>
          )}

          {/* PASO: PREVIEW */}
          {paso === "preview" && ocData && (
            <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
              <div style={{ background: "var(--surface-2)", border: "1px solid var(--n-200)", borderRadius: "var(--r-md)", padding: 14, fontSize: 14 }}>
                <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 8 }}>
                  <span style={{ color: "var(--n-500)" }}>Número OC</span>
                  <span style={{ color: "var(--n-900)", fontWeight: 600 }}>{ocData.numero_oc}</span>
                </div>
                <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 8 }}>
                  <span style={{ color: "var(--n-500)" }}>Total</span>
                  <span style={{ color: "var(--success)", fontWeight: 600, fontSize: 16 }}>{fmt(ocData.total, ocData.moneda)}</span>
                </div>
                <div style={{ display: "flex", justifyContent: "space-between" }}>
                  <span style={{ color: "var(--n-500)" }}>Proveedor</span>
                  <span style={{ color: "var(--n-900)" }}>{ocData.proveedor_nombre}</span>
                </div>
              </div>

              <a href={pdfUrl} download={`${ocData.numero_oc}.pdf`} className="btn-swiss-secondary" style={{ display: "block", textAlign: "center", textDecoration: "none" }}>
                Descargar PDF preview →
              </a>

              {!email && (
                <div style={{ fontSize: 13, color: "var(--brand-700)", background: "var(--st-cotizando-bg)", borderRadius: "var(--r-md)", padding: "10px 12px" }}>
                  No ingresaste email del proveedor, la OC se enviará solo a tu copia (hola@claria.cc).
                </div>
              )}

              {error && (
                <div style={{ fontSize: 13, color: "var(--danger)", background: "var(--st-rechazada-bg)", borderRadius: "var(--r-md)", padding: "10px 12px" }}>
                  {error}
                </div>
              )}
            </div>
          )}

          {/* PASO: ENVIADO */}
          {paso === "enviado" && ocData && (
            <div style={{ textAlign: "center", padding: "24px 0" }}>
              <div style={{ width: 48, height: 48, borderRadius: "50%", background: "var(--st-aprobada-bg)", color: "var(--success)", display: "inline-flex", alignItems: "center", justifyContent: "center", marginBottom: 16, fontSize: 22 }}>✓</div>
              <h3 style={{ fontSize: 18, fontWeight: 600, color: "var(--n-900)", marginBottom: 8 }}>
                OC enviada exitosamente
              </h3>
              <p style={{ fontSize: 13, color: "var(--n-500)", marginBottom: 4 }}>{ocData.numero_oc}</p>
              <p style={{ fontSize: 14, color: "var(--success)" }}>
                {email ? `Email enviado a ${email}` : "Copia enviada a hola@claria.cc"}
              </p>
            </div>
          )}
        </div>

        {/* Footer */}
        <div style={{ padding: "16px 22px", borderTop: "1px solid var(--n-200)", display: "flex", justifyContent: "flex-end", gap: 10 }}>
          {paso !== "enviado" && (
            <button onClick={onClose} className="btn-swiss-secondary">Cancelar</button>
          )}
          {paso === "form" && (
            <button onClick={handleGenerar} disabled={generando || precioUnitario <= 0} className="btn-swiss-primary">
              {generando ? "Generando PDF…" : "Generar OC →"}
            </button>
          )}
          {paso === "preview" && (
            <button onClick={handleEnviar} disabled={enviando} className="btn-swiss-primary">
              {enviando ? "Enviando…" : "Confirmar y enviar OC →"}
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
