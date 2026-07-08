"use client";
import { useState } from "react";

interface Destinatario {
  nombre: string;
  url: string;
  email: string;
}

interface Props {
  destinatarios: Destinatario[];
  subject: string;
  body: string;
  onSubjectChange: (v: string) => void;
  onBodyChange: (v: string) => void;
  onEmailChange: (url: string, email: string) => void;
  onEnviar: () => void;
  onCancelar: () => void;
  enviando: boolean;
  enviados: Set<string>;
}

export default function EmailPreviewModal({
  destinatarios, subject, body,
  onSubjectChange, onBodyChange, onEmailChange,
  onEnviar, onCancelar, enviando, enviados,
}: Props) {
  const [tabActiva, setTabActiva] = useState<"correo" | "destinatarios">("correo");
  const emailsValidos = destinatarios.filter(d => d.email.includes("@")).length;

  const inputStyle: React.CSSProperties = {
    width: "100%",
    padding: "10px 12px",
    background: "var(--bg-base)",
    border: "1px solid var(--border-default)",
    color: "var(--text-primary)",
    fontSize: 12,
    outline: "none",
    fontFamily: "var(--font-mono)",
    boxSizing: "border-box",
  };

  return (
    <div style={{
      position: "fixed", inset: 0,
      background: "rgba(0,0,0,0.6)",
      display: "flex", alignItems: "center", justifyContent: "center",
      zIndex: 1000, padding: 16,
    }}>
      <div style={{
        width: "100%", maxWidth: 640,
        background: "var(--bg-surface)",
        border: "1px solid var(--border-default)",
        overflow: "hidden",
        maxHeight: "90vh",
        display: "flex", flexDirection: "column",
      }}>

        {/* Header */}
        <div style={{ padding: "16px 20px", borderBottom: "1px solid var(--border-default)", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <div>
            <span className="label" style={{ color: "var(--accent)", display: "block", marginBottom: 2 }}>Email Agent</span>
            <h2 style={{ fontSize: 16, fontWeight: 700, color: "var(--text-primary)", margin: 0, letterSpacing: "-0.01em" }}>Preview del correo</h2>
          </div>
          <button onClick={onCancelar} style={{ background: "none", border: "none", color: "var(--text-muted)", cursor: "pointer", fontSize: 18 }}>✕</button>
        </div>

        {/* Tabs */}
        <div style={{ display: "flex", borderBottom: "1px solid var(--border-default)" }}>
          {[
            { key: "correo", label: "Correo" },
            { key: "destinatarios", label: `Destinatarios (${destinatarios.length})` },
          ].map(t => (
            <button
              key={t.key}
              onClick={() => setTabActiva(t.key as "correo" | "destinatarios")}
              className="label"
              style={{
                flex: 1, padding: "10px",
                cursor: "pointer", fontFamily: "var(--font-mono)",
                border: "none",
                background: tabActiva === t.key ? "var(--fill-error)" : "var(--bg-surface)",
                color: tabActiva === t.key ? "var(--accent)" : "var(--text-muted)",
                borderBottom: tabActiva === t.key ? "2px solid var(--accent)" : "2px solid transparent",
              }}
            >
              {t.label.toUpperCase()}
            </button>
          ))}
        </div>

        {/* Content */}
        <div style={{ flex: 1, overflow: "auto", padding: "16px 20px" }}>
          {tabActiva === "correo" && (
            <div>
              <div style={{
                background: "var(--bg-base)",
                border: "1px solid var(--border-default)",
                padding: "8px 12px",
                marginBottom: 12,
              }}>
                <span className="label" style={{ color: "var(--text-muted)" }}>De: </span>
                <span className="label" style={{ color: "var(--accent)" }}>hola@claria.cc</span>
              </div>

              <div style={{ marginBottom: 12 }}>
                <label className="label" style={{ color: "var(--text-muted)", display: "block", marginBottom: 6 }}>Asunto</label>
                <input value={subject} onChange={e => onSubjectChange(e.target.value)} style={inputStyle} />
              </div>

              <div>
                <label className="label" style={{ color: "var(--text-muted)", display: "block", marginBottom: 6 }}>Cuerpo del correo</label>
                <textarea
                  value={body}
                  onChange={e => onBodyChange(e.target.value)}
                  rows={10}
                  style={{ ...inputStyle, resize: "vertical", lineHeight: 1.6 }}
                />
              </div>
            </div>
          )}

          {tabActiva === "destinatarios" && (
            <div style={{ display: "flex", flexDirection: "column", gap: 1 }}>
              <div className="label" style={{ color: "var(--text-muted)", marginBottom: 8 }}>
                Ingresa el email de cada proveedor. El nombre se sustituye automaticamente en el correo.
              </div>
              {destinatarios.map((d) => (
                <div key={d.url} style={{
                  background: enviados.has(d.url) ? "var(--fill-success)" : "var(--bg-surface)",
                  border: `1px solid ${enviados.has(d.url) ? "var(--palette-green-500)" : "var(--border-default)"}`,
                  padding: "12px 14px",
                  marginBottom: 8,
                }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
                    <div style={{ fontSize: 12, fontWeight: 700, color: "var(--text-primary)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", flex: 1 }}>
                      {d.nombre}
                    </div>
                    {enviados.has(d.url) && (
                      <span className="label" style={{ color: "var(--text-success)", marginLeft: 8, whiteSpace: "nowrap" }}>
                        Enviado ✓
                      </span>
                    )}
                  </div>
                  <input
                    type="email"
                    value={d.email}
                    onChange={e => onEmailChange(d.url, e.target.value)}
                    placeholder="email@proveedor.com"
                    disabled={enviados.has(d.url)}
                    style={{ ...inputStyle, fontSize: 11, opacity: enviados.has(d.url) ? 0.5 : 1 }}
                  />
                </div>
              ))}
              {emailsValidos === 0 && (
                <div style={{
                  fontSize: 10,
                  color: "var(--text-error)",
                  background: "var(--fill-error)",
                  border: "1px solid var(--border-accent)",
                  padding: "8px 12px",
                }}>
                  Agrega al menos un email valido para poder enviar.
                </div>
              )}
            </div>
          )}
        </div>

        {/* Footer */}
        <div style={{ padding: "14px 20px", borderTop: "1px solid var(--border-default)", display: "flex", justifyContent: "space-between", alignItems: "center", background: "var(--bg-surface)" }}>
          <span className="label" style={{ color: "var(--text-muted)" }}>
            {emailsValidos} de {destinatarios.length} con email valido
          </span>
          <div style={{ display: "flex", gap: 8 }}>
            <button onClick={onCancelar} className="btn-swiss-secondary">Cancelar</button>
            <button
              onClick={onEnviar}
              disabled={enviando || emailsValidos === 0}
              className={enviando || emailsValidos === 0 ? "btn-swiss-secondary" : "btn-swiss-primary"}
            >
              {enviando ? "Enviando..." : `Enviar a ${emailsValidos} proveedor${emailsValidos !== 1 ? "es" : ""} →`}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
