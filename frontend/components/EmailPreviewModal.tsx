"use client";
import { useState } from "react";
import { X, Mail } from "lucide-react";

interface Destinatario {
  _uid?: string;
  nombre: string;
  url: string;
  email: string;
}

interface Props {
  fromEmail?: string;
  destinatarios: Destinatario[];
  subject: string;
  body: string;
  onSubjectChange: (v: string) => void;
  onBodyChange: (v: string) => void;
  onEmailChange: (uid: string, email: string) => void;
  onEnviar: () => void;
  onCancelar: () => void;
  enviando: boolean;
  enviados: Set<string>;
}

export default function EmailPreviewModal({
  fromEmail, destinatarios, subject, body,
  onSubjectChange, onBodyChange, onEmailChange,
  onEnviar, onCancelar, enviando, enviados,
}: Props) {
  const [tabActiva, setTabActiva] = useState<"correo" | "destinatarios">("correo");
  const emailsValidos = destinatarios.filter(d => d.email.includes("@")).length;

  // Vista previa personalizada con el primer destinatario
  const ejemploNombre = destinatarios[0]?.nombre || "el proveedor";
  const tienePlaceholder = body.includes("{proveedor_nombre}") || subject.includes("{proveedor_nombre}");
  const rellenar = (t: string) => t.replace(/\{proveedor_nombre\}/g, ejemploNombre);

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

  return (
    <div style={{
      position: "fixed", inset: 0,
      background: "rgba(33,29,24,.4)", backdropFilter: "blur(2px)",
      display: "flex", alignItems: "center", justifyContent: "center",
      zIndex: 1000, padding: 16,
    }}>
      <div style={{
        width: "100%", maxWidth: 640,
        background: "var(--surface)",
        borderRadius: "var(--r-xl)",
        boxShadow: "var(--shadow-modal)",
        overflow: "hidden",
        maxHeight: "90vh",
        display: "flex", flexDirection: "column",
      }}>

        {/* Header */}
        <div style={{ padding: "18px 22px", borderBottom: "1px solid var(--n-200)", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <span style={{
              width: 40, height: 40, borderRadius: "var(--r-md)", flexShrink: 0,
              background: "var(--brand-50)", color: "var(--brand)",
              display: "inline-flex", alignItems: "center", justifyContent: "center",
            }}>
              <Mail size={20} strokeWidth={1.75} />
            </span>
            <div>
              <span style={{ fontSize: 12.5, fontWeight: 500, color: "var(--brand)", display: "block" }}>Asistente de correo</span>
              <h2 style={{ fontSize: 18, fontWeight: 600, color: "var(--n-900)", margin: 0 }}>Vista previa del correo</h2>
            </div>
          </div>
          <button onClick={onCancelar} aria-label="Cerrar" style={{ background: "none", border: "none", color: "var(--n-500)", cursor: "pointer", display: "inline-flex", padding: 4 }}>
            <X size={18} strokeWidth={1.75} />
          </button>
        </div>

        {/* Tabs */}
        <div style={{ display: "flex", gap: 2, padding: "12px 22px 0" }}>
          {[
            { key: "correo", label: "Correo" },
            { key: "destinatarios", label: `Destinatarios (${destinatarios.length})` },
          ].map(t => {
            const activa = tabActiva === t.key;
            return (
              <button
                key={t.key}
                onClick={() => setTabActiva(t.key as "correo" | "destinatarios")}
                style={{
                  padding: "8px 14px", cursor: "pointer", fontFamily: "var(--font-sans)",
                  border: "none", background: "none",
                  fontSize: 14, fontWeight: activa ? 600 : 500,
                  color: activa ? "var(--brand)" : "var(--n-500)",
                  borderBottom: `2px solid ${activa ? "var(--brand)" : "transparent"}`,
                }}
              >
                {t.label}
              </button>
            );
          })}
        </div>
        <div style={{ borderBottom: "1px solid var(--n-200)" }} />

        {/* Content */}
        <div style={{ flex: 1, overflow: "auto", padding: "18px 22px" }}>
          {tabActiva === "correo" && (
            <div>
              <div style={{
                background: "var(--surface-2)",
                border: "1px solid var(--n-200)",
                borderRadius: "var(--r-md)",
                padding: "10px 12px",
                marginBottom: 14,
                fontSize: 13.5,
              }}>
                <span style={{ color: "var(--n-500)" }}>De: </span>
                <span style={{ color: "var(--brand)", fontWeight: 500 }}>{fromEmail || "tu correo conectado"}</span>
                <span style={{ color: "var(--n-500)", marginLeft: 8, fontSize: 12.5 }}>
                  · se envía desde tu Gmail para que te respondan a ti
                </span>
              </div>

              <div style={{ marginBottom: 14 }}>
                <label style={{ fontSize: 13, fontWeight: 500, color: "var(--n-700)", display: "block", marginBottom: 6 }}>Asunto</label>
                <input value={subject} onChange={e => onSubjectChange(e.target.value)} style={inputStyle} />
              </div>

              <div>
                <label style={{ fontSize: 13, fontWeight: 500, color: "var(--n-700)", display: "block", marginBottom: 6 }}>
                  Cuerpo del correo <span style={{ color: "var(--n-500)", fontWeight: 400 }}>(plantilla)</span>
                </label>
                <textarea
                  value={body}
                  onChange={e => onBodyChange(e.target.value)}
                  rows={9}
                  style={{ ...inputStyle, resize: "vertical", lineHeight: 1.6 }}
                />
                {tienePlaceholder && (
                  <div style={{ marginTop: 10 }}>
                    <div style={{ fontSize: 12.5, color: "var(--n-500)", marginBottom: 6 }}>
                      Así lo verá <strong style={{ color: "var(--n-700)" }}>{ejemploNombre}</strong> (cada proveedor recibe el suyo):
                    </div>
                    <div style={{
                      background: "var(--surface-2)", border: "1px solid var(--n-200)",
                      borderRadius: "var(--r-md)", padding: "12px 14px",
                    }}>
                      <div style={{ fontSize: 13, fontWeight: 600, color: "var(--n-900)", marginBottom: 6 }}>
                        {rellenar(subject)}
                      </div>
                      <div style={{ fontSize: 13, color: "var(--n-700)", lineHeight: 1.6, whiteSpace: "pre-wrap" }}>
                        {rellenar(body)}
                      </div>
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}

          {tabActiva === "destinatarios" && (
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              <div style={{ fontSize: 13, color: "var(--n-500)", marginBottom: 4 }}>
                Ingresa el email de cada proveedor. El nombre se sustituye automáticamente en el correo.
              </div>
              {destinatarios.map((d) => {
                const enviado = enviados.has(d._uid!);
                return (
                  <div key={d._uid ?? d.url} style={{
                    background: enviado ? "var(--st-aprobada-bg)" : "var(--surface)",
                    border: `1px solid ${enviado ? "transparent" : "var(--n-200)"}`,
                    borderRadius: "var(--r-md)",
                    padding: "12px 14px",
                  }}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
                      <div style={{ fontSize: 14, fontWeight: 600, color: "var(--n-900)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", flex: 1 }}>
                        {d.nombre}
                      </div>
                      {enviado && (
                        <span style={{ fontSize: 12.5, fontWeight: 500, color: "var(--success)", marginLeft: 8, whiteSpace: "nowrap" }}>
                          Enviado ✓
                        </span>
                      )}
                    </div>
                    <input
                      type="email"
                      value={d.email}
                      onChange={e => onEmailChange(d._uid!, e.target.value)}
                      placeholder="email@proveedor.com"
                      disabled={enviado}
                      style={{ ...inputStyle, opacity: enviado ? 0.5 : 1 }}
                    />
                  </div>
                );
              })}
              {emailsValidos === 0 && (
                <div style={{
                  fontSize: 13,
                  color: "var(--danger)",
                  background: "var(--st-rechazada-bg)",
                  borderRadius: "var(--r-md)",
                  padding: "10px 12px",
                }}>
                  Agrega al menos un email válido para poder enviar.
                </div>
              )}
            </div>
          )}
        </div>

        {/* Footer */}
        <div style={{ padding: "16px 22px", borderTop: "1px solid var(--n-200)", display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
          <span style={{ fontSize: 13, color: "var(--n-500)" }}>
            {emailsValidos} de {destinatarios.length} con email válido
          </span>
          <div style={{ display: "flex", gap: 8 }}>
            <button onClick={onCancelar} className="btn-swiss-secondary">Cancelar</button>
            <button
              onClick={onEnviar}
              disabled={enviando || emailsValidos === 0}
              className="btn-swiss-primary"
            >
              {enviando ? "Enviando…" : `Enviar a ${emailsValidos} proveedor${emailsValidos !== 1 ? "es" : ""} →`}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
