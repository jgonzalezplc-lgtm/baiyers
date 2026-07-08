"use client";
import { useState, useEffect } from "react";
import { useParams } from "next/navigation";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface OCInfo {
  numero_oc: string;
  estado: string;
  precio_total: number;
  moneda: string;
  nombre_item: string;
  proveedor_nombre: string;
  cantidad: number;
  condiciones_pago: string;
  plazo_entrega: string;
}

function fmt(n: number, moneda: string) {
  if (moneda === "CLP") return `$${Math.round(n).toLocaleString("es-CL")}`;
  return `${moneda} ${n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

export default function ConfirmarOCPage() {
  const params = useParams();
  const token = params.token as string;

  const [oc, setOc] = useState<OCInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [confirmando, setConfirmando] = useState(false);
  const [confirmado, setConfirmado] = useState(false);
  const [yaConfirmada, setYaConfirmada] = useState(false);
  const [mostrarConsulta, setMostrarConsulta] = useState(false);

  useEffect(() => {
    fetch(`${API_URL}/api/oc/info/${token}`)
      .then(r => r.ok ? r.json() : Promise.reject(r.statusText))
      .then(data => {
        setOc(data);
        if (data.estado === "confirmada") setYaConfirmada(true);
      })
      .catch(() => setError("Orden de compra no encontrada o enlace invalido."))
      .finally(() => setLoading(false));
  }, [token]);

  const handleConfirmar = async () => {
    setConfirmando(true);
    try {
      const res = await fetch(`${API_URL}/api/oc/confirmar/${token}`, { method: "POST" });
      if (!res.ok) throw new Error();
      const data = await res.json();
      setConfirmado(true);
      if (data.ya_confirmada) setYaConfirmada(true);
    } catch {
      setError("Error al confirmar. Intenta de nuevo o escribenos a hola@claria.cc");
    } finally {
      setConfirmando(false);
    }
  };

  return (
    <div style={{
      minHeight: "100vh",
      background: "var(--bg-base)",
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      padding: 20,
    }}>
      <div style={{
        width: "100%",
        maxWidth: 480,
        background: "var(--bg-surface)",
        border: "1px solid var(--border-default)",
        overflow: "hidden",
      }}>

        {/* Header */}
        <div style={{ background: "var(--bg-inverse)", padding: "20px 24px" }}>
          <span className="label" style={{ color: "var(--text-inverse)", opacity: 0.7, display: "block", marginBottom: 4 }}>
            CLARIA · Procurement
          </span>
          <h1 style={{ fontSize: 18, fontWeight: 700, color: "var(--text-inverse)", margin: 0, letterSpacing: "-0.01em" }}>
            Orden de Compra
          </h1>
        </div>

        <div style={{ padding: "24px" }}>
          {loading && (
            <div style={{ textAlign: "center", color: "var(--text-muted)", fontSize: 12, padding: "24px 0" }}>
              Cargando...
            </div>
          )}

          {error && (
            <div style={{
              background: "var(--fill-error)",
              border: "1px solid var(--border-accent)",
              padding: 16,
              fontSize: 12,
              color: "var(--text-error)",
              textAlign: "center",
            }}>
              {error}
            </div>
          )}

          {oc && !loading && !error && (
            <>
              {/* OC Info */}
              <div style={{ marginBottom: 20 }}>
                <div style={{ fontSize: 22, fontWeight: 700, color: "var(--text-primary)", marginBottom: 4, letterSpacing: "-0.02em" }}>
                  {oc.numero_oc}
                </div>
                <div style={{ fontSize: 12, color: "var(--text-muted)" }}>Emitida por Claria Procurement</div>
              </div>

              <div style={{ border: "1px solid var(--border-default)", marginBottom: 20 }}>
                {[
                  { label: "Item", val: oc.nombre_item },
                  { label: "Cantidad", val: String(oc.cantidad) },
                  { label: "Total", val: fmt(oc.precio_total, oc.moneda) },
                  { label: "Condiciones de pago", val: oc.condiciones_pago },
                  { label: "Plazo de entrega", val: oc.plazo_entrega || "A convenir" },
                ].filter(({ val }) => val).map(({ label, val }, idx, arr) => (
                  <div key={label} style={{
                    display: "flex",
                    justifyContent: "space-between",
                    padding: "10px 14px",
                    borderBottom: idx < arr.length - 1 ? "1px solid var(--border-default)" : "none",
                    background: "var(--bg-surface)",
                  }}>
                    <span className="label" style={{ color: "var(--text-muted)" }}>{label}</span>
                    <span style={{ fontSize: 11, color: "var(--text-primary)", fontWeight: 700 }}>{val}</span>
                  </div>
                ))}
              </div>

              {/* Estado / Accion */}
              {(confirmado || yaConfirmada) ? (
                <div style={{ textAlign: "center", padding: "20px 0" }}>
                  <div className="section-rule" style={{ margin: "0 auto 16px", background: "var(--text-success)" }} />
                  <div style={{ fontSize: 15, fontWeight: 700, color: "var(--text-success)", marginBottom: 8 }}>
                    {yaConfirmada && !confirmado ? "OC ya confirmada anteriormente" : "OC confirmada exitosamente"}
                  </div>
                  <div style={{ fontSize: 12, color: "var(--text-muted)" }}>El equipo de compras ha sido notificado.</div>
                </div>
              ) : (
                <button
                  onClick={handleConfirmar}
                  disabled={confirmando}
                  className={confirmando ? "btn-swiss-secondary" : "btn-swiss-primary"}
                  style={{ width: "100%", padding: "14px", fontSize: 14 }}
                >
                  {confirmando ? "Confirmando..." : "Confirmar recepcion de OC"}
                </button>
              )}

              {/* Consulta */}
              {!mostrarConsulta ? (
                <button
                  onClick={() => setMostrarConsulta(true)}
                  className="btn-swiss-secondary"
                  style={{ width: "100%", marginTop: 12, padding: "10px" }}
                >
                  Tengo una consulta
                </button>
              ) : (
                <div style={{
                  marginTop: 12,
                  background: "var(--bg-base)",
                  border: "1px solid var(--border-default)",
                  padding: 16,
                  fontSize: 12,
                  color: "var(--text-muted)",
                  textAlign: "center",
                }}>
                  Escribenos a <strong style={{ color: "var(--accent)" }}>hola@claria.cc</strong> con el numero de OC{" "}
                  <strong style={{ color: "var(--text-primary)" }}>{oc.numero_oc}</strong>
                </div>
              )}
            </>
          )}
        </div>

        <div style={{
          padding: "12px 24px",
          borderTop: "1px solid var(--border-default)",
          background: "var(--bg-surface)",
        }}>
          <span className="label" style={{ color: "var(--text-muted)" }}>Generado por Claria · claria.cc</span>
        </div>
      </div>
    </div>
  );
}
