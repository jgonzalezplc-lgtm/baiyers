"use client";
import { useState, useEffect, useRef } from "react";
import { createClient } from "@/lib/supabase/client";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts";
import ReactMarkdown from "react-markdown";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface Conversacion {
  id: string;
  titulo: string;
  updated_at: string;
}

interface Mensaje {
  id?: string;
  rol: "user" | "assistant";
  contenido: string;
  datos_visuales?: {
    formato_visual?: string;
    datos_tabla?: Record<string, unknown>[];
    datos_grafico?: { label: string; valor: number }[];
    datos_cards?: { titulo: string; valor: string; color: string }[];
    links?: { texto: string; href: string }[];
  };
}

const SUGERENCIAS = [
  "Cuanto gaste el mes pasado?",
  "Cual es mi mejor proveedor?",
  "Que items compro mas frecuentemente?",
  "Estoy pagando precios justos?",
  "Muestrame mis facturas pendientes",
  "Que proveedores tienen mejor score?",
];

export default function ChatPage() {
  const [userId, setUserId] = useState<string | null>(null);
  const [conversaciones, setConversaciones] = useState<Conversacion[]>([]);
  const [convActiva, setConvActiva] = useState<string | null>(null);
  const [mensajes, setMensajes] = useState<Mensaje[]>([]);
  const [input, setInput] = useState("");
  const [enviando, setEnviando] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const bottomRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    createClient().auth.getUser().then(({ data }) => {
      if (data.user) {
        setUserId(data.user.id);
        cargarConversaciones(data.user.id);
      }
    });
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [mensajes]);

  const cargarConversaciones = async (uid: string) => {
    const res = await fetch(`${API_URL}/api/chat/conversaciones?user_id=${uid}`);
    if (res.ok) setConversaciones(await res.json());
  };

  const cargarMensajes = async (convId: string) => {
    const res = await fetch(`${API_URL}/api/chat/conversaciones/${convId}/mensajes`);
    if (res.ok) {
      const data = await res.json();
      setMensajes(data.map((m: Record<string, unknown>) => ({
        rol: m.rol as "user" | "assistant",
        contenido: m.contenido as string,
        datos_visuales: m.datos_visuales as Mensaje["datos_visuales"],
      })));
    }
  };

  const seleccionarConversacion = (conv: Conversacion) => {
    setConvActiva(conv.id);
    cargarMensajes(conv.id);
  };

  const nuevaConversacion = () => {
    setConvActiva(null);
    setMensajes([]);
  };

  const enviarMensaje = async (texto?: string) => {
    const msg = (texto || input).trim();
    if (!msg || !userId || enviando) return;

    setInput("");
    setEnviando(true);
    setMensajes(prev => [...prev, { rol: "user", contenido: msg }]);

    try {
      const res = await fetch(`${API_URL}/api/chat/mensaje`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mensaje: msg, conversacion_id: convActiva, user_id: userId }),
      });
      if (!res.ok) throw new Error();
      const data = await res.json();

      setMensajes(prev => [...prev, {
        rol: "assistant",
        contenido: data.respuesta || "",
        datos_visuales: {
          formato_visual: data.formato_visual,
          datos_tabla: data.datos_tabla,
          datos_grafico: data.datos_grafico,
          datos_cards: data.datos_cards,
          links: data.links,
        },
      }]);

      if (!convActiva && data.conversacion_id) {
        setConvActiva(data.conversacion_id);
        if (userId) cargarConversaciones(userId);
      }
    } catch {
      setMensajes(prev => [...prev, { rol: "assistant", contenido: "Lo siento, tuve un error al procesar tu consulta. Intenta de nuevo." }]);
    } finally {
      setEnviando(false);
      textareaRef.current?.focus();
    }
  };

  const eliminarConversacion = async (convId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    await fetch(`${API_URL}/api/chat/conversaciones/${convId}?user_id=${userId}`, { method: "DELETE" });
    if (convActiva === convId) nuevaConversacion();
    if (userId) cargarConversaciones(userId);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      enviarMensaje();
    }
  };

  const autoResize = () => {
    const ta = textareaRef.current;
    if (ta) { ta.style.height = "auto"; ta.style.height = Math.min(ta.scrollHeight, 160) + "px"; }
  };

  const tooltipStyle = {
    background: "var(--bg-inverse)",
    border: "none",
    fontSize: 11,
    color: "var(--text-inverse)",
    fontFamily: "var(--font-mono)",
  };

  return (
    <div style={{ display: "flex", height: "calc(100vh - 60px)", margin: "-24px -20px" }}>

      {/* Sidebar */}
      {sidebarOpen && (
        <div style={{
          width: 240,
          flexShrink: 0,
          background: "var(--bg-surface)",
          borderRight: "1px solid var(--border-default)",
          display: "flex",
          flexDirection: "column",
        }}>
          <div style={{ padding: "16px 12px", borderBottom: "1px solid var(--border-default)" }}>
            <button onClick={nuevaConversacion} className="btn-swiss-primary" style={{ width: "100%" }}>
              + Nueva conversacion
            </button>
          </div>

          <div style={{ flex: 1, overflowY: "auto", padding: "8px 6px" }}>
            {conversaciones.length === 0 && (
              <div className="label" style={{ color: "var(--text-muted)", textAlign: "center", padding: "24px 8px" }}>
                Sin conversaciones aun
              </div>
            )}
            {conversaciones.map(conv => (
              <div
                key={conv.id}
                onClick={() => seleccionarConversacion(conv)}
                style={{
                  padding: "8px 10px",
                  cursor: "pointer",
                  background: convActiva === conv.id ? "var(--fill-error)" : "none",
                  borderLeft: convActiva === conv.id ? "2px solid var(--accent)" : "2px solid transparent",
                  marginBottom: 2,
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "flex-start",
                  gap: 4,
                }}
              >
                <div style={{ overflow: "hidden" }}>
                  <div style={{ fontSize: 11, color: "var(--text-secondary)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    {conv.titulo || "Conversacion"}
                  </div>
                  <div className="label" style={{ color: "var(--text-muted)", marginTop: 2 }}>
                    {new Date(conv.updated_at).toLocaleDateString("es-CL")}
                  </div>
                </div>
                <button
                  onClick={e => eliminarConversacion(conv.id, e)}
                  style={{ background: "none", border: "none", color: "var(--text-muted)", cursor: "pointer", fontSize: 12, padding: "0 2px", flexShrink: 0 }}
                >×</button>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Main */}
      <div style={{ flex: 1, display: "flex", flexDirection: "column", minWidth: 0 }}>

        {/* Header */}
        <div style={{ padding: "12px 20px", borderBottom: "1px solid var(--border-default)", display: "flex", alignItems: "center", gap: 10, background: "var(--bg-surface)" }}>
          <button onClick={() => setSidebarOpen(v => !v)} style={{ background: "none", border: "none", color: "var(--text-muted)", cursor: "pointer", fontSize: 16, padding: 4 }}>
            ☰
          </button>
          <div style={{ fontSize: 13, fontWeight: 700, color: "var(--text-primary)", letterSpacing: "-0.01em" }}>Claria</div>
          <div className="label" style={{ color: "var(--text-muted)" }}>Asistente de compras</div>
        </div>

        {/* Messages */}
        <div style={{ flex: 1, overflowY: "auto", padding: "20px", background: "var(--bg-base)" }}>
          {mensajes.length === 0 && (
            <div style={{ maxWidth: 560, margin: "40px auto", textAlign: "center" }}>
              <div className="section-rule" style={{ margin: "0 auto 16px" }} />
              <div style={{ fontSize: 16, fontWeight: 700, color: "var(--text-primary)", marginBottom: 6, letterSpacing: "-0.01em" }}>
                Hola, soy Claria
              </div>
              <div style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 28 }}>
                Tu asistente de compras. Preguntame sobre tus gastos, proveedores y cotizaciones.
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 1, border: "1px solid var(--border-default)" }}>
                {SUGERENCIAS.map((s, idx) => (
                  <button
                    key={s}
                    onClick={() => enviarMensaje(s)}
                    style={{
                      padding: "10px 12px",
                      background: "var(--bg-surface)",
                      borderRight: idx % 2 === 0 ? "1px solid var(--border-default)" : "none",
                      borderBottom: idx < 4 ? "1px solid var(--border-default)" : "none",
                      border: "none",
                      cursor: "pointer",
                      fontFamily: "var(--font-mono)",
                      fontSize: 11,
                      color: "var(--text-secondary)",
                      textAlign: "left",
                      lineHeight: 1.5,
                    }}
                  >
                    {s}
                  </button>
                ))}
              </div>
            </div>
          )}

          {mensajes.map((msg, i) => (
            <div key={i} style={{ marginBottom: 20, display: "flex", justifyContent: msg.rol === "user" ? "flex-end" : "flex-start" }}>
              {msg.rol === "assistant" && (
                <div style={{
                  width: 28, height: 28,
                  background: "var(--accent)",
                  display: "flex", alignItems: "center", justifyContent: "center",
                  fontSize: 11, color: "#fff",
                  marginRight: 10, flexShrink: 0,
                  fontFamily: "var(--font-mono)",
                }}>C</div>
              )}
              <div style={{ maxWidth: "72%", minWidth: 80 }}>
                <div style={{
                  padding: "10px 14px",
                  background: msg.rol === "user" ? "var(--bg-inverse)" : "var(--bg-surface)",
                  border: msg.rol === "user" ? "none" : "1px solid var(--border-default)",
                  fontSize: 13,
                  color: msg.rol === "user" ? "var(--text-inverse)" : "var(--text-primary)",
                  lineHeight: 1.6,
                }}>
                  <ReactMarkdown>{msg.contenido}</ReactMarkdown>
                </div>

                {msg.datos_visuales && (
                  <div style={{ marginTop: 10 }}>
                    {/* Cards */}
                    {msg.datos_visuales.formato_visual === "cards" && msg.datos_visuales.datos_cards && (
                      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(120px, 1fr))", gap: 1, border: "1px solid var(--border-default)" }}>
                        {msg.datos_visuales.datos_cards.map((c, ci) => (
                          <div key={ci} style={{ background: "var(--bg-surface)", border: "1px solid var(--border-default)", padding: "10px 12px" }}>
                            <div style={{ fontSize: 16, fontWeight: 700, color: c.color || "var(--accent)" }}>{c.valor}</div>
                            <div className="label" style={{ color: "var(--text-muted)", marginTop: 2 }}>{c.titulo}</div>
                          </div>
                        ))}
                      </div>
                    )}

                    {/* Bar chart */}
                    {msg.datos_visuales.formato_visual === "grafico_barras" && msg.datos_visuales.datos_grafico && (
                      <div style={{ background: "var(--bg-surface)", border: "1px solid var(--border-default)", padding: "12px 8px", marginTop: 8 }}>
                        <ResponsiveContainer width="100%" height={180}>
                          <BarChart data={msg.datos_visuales.datos_grafico}>
                            <XAxis dataKey="label" tick={{ fontSize: 9, fill: "var(--text-muted)" as string }} axisLine={false} tickLine={false} />
                            <YAxis tick={{ fontSize: 9, fill: "var(--text-muted)" as string }} axisLine={false} tickLine={false} />
                            <Tooltip contentStyle={tooltipStyle} />
                            <Bar dataKey="valor" fill="var(--accent)" />
                          </BarChart>
                        </ResponsiveContainer>
                      </div>
                    )}

                    {/* Table */}
                    {msg.datos_visuales.formato_visual === "tabla" && msg.datos_visuales.datos_tabla && msg.datos_visuales.datos_tabla.length > 0 && (
                      <div style={{ border: "1px solid var(--border-default)", overflow: "auto", marginTop: 8 }}>
                        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 11 }}>
                          <thead>
                            <tr style={{ background: "var(--bg-surface)" }}>
                              {Object.keys(msg.datos_visuales.datos_tabla[0]).map(col => (
                                <th key={col} className="label" style={{ padding: "7px 10px", borderBottom: "1px solid var(--border-default)", textAlign: "left", color: "var(--text-muted)" }}>{col}</th>
                              ))}
                            </tr>
                          </thead>
                          <tbody>
                            {msg.datos_visuales.datos_tabla.map((row, ri) => (
                              <tr key={ri}>
                                {Object.values(row).map((val, vi) => (
                                  <td key={vi} style={{ padding: "6px 10px", color: "var(--text-secondary)", borderBottom: "1px solid var(--border-default)" }}>
                                    {String(val ?? "—")}
                                  </td>
                                ))}
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    )}

                    {/* Links */}
                    {msg.datos_visuales.links && msg.datos_visuales.links.length > 0 && (
                      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 8 }}>
                        {msg.datos_visuales.links.map((link, li) => (
                          <a key={li} href={link.href} className="btn-swiss-secondary" style={{ textDecoration: "none", fontSize: 10 }}>
                            {link.texto} →
                          </a>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </div>
            </div>
          ))}

          {enviando && (
            <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 20 }}>
              <div style={{ width: 28, height: 28, background: "var(--accent)", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 11, color: "#fff", fontFamily: "var(--font-mono)" }}>C</div>
              <div style={{ padding: "10px 14px", background: "var(--bg-surface)", border: "1px solid var(--border-default)" }}>
                <div style={{ display: "flex", gap: 4 }}>
                  {[0, 1, 2].map(d => (
                    <div key={d} style={{ width: 6, height: 6, background: "var(--accent)", opacity: 0.3 + d * 0.35 }} />
                  ))}
                </div>
              </div>
            </div>
          )}
          <div ref={bottomRef} />
        </div>

        {/* Input */}
        <div style={{ padding: "12px 20px", borderTop: "1px solid var(--border-default)", background: "var(--bg-surface)" }}>
          <div style={{ display: "flex", gap: 8, alignItems: "flex-end", background: "var(--bg-base)", border: "1px solid var(--border-default)", padding: "8px 12px" }}>
            <textarea
              ref={textareaRef}
              value={input}
              onChange={e => { setInput(e.target.value); autoResize(); }}
              onKeyDown={handleKeyDown}
              placeholder="Preguntame algo sobre tus compras..."
              rows={1}
              style={{
                flex: 1,
                background: "none",
                border: "none",
                color: "var(--text-primary)",
                fontSize: 13,
                outline: "none",
                resize: "none",
                fontFamily: "var(--font-mono)",
                lineHeight: 1.5,
                maxHeight: 160,
                overflowY: "auto",
              }}
            />
            <button
              onClick={() => enviarMensaje()}
              disabled={!input.trim() || enviando}
              style={{
                padding: "7px 14px",
                background: !input.trim() || enviando ? "var(--border-default)" : "var(--accent)",
                color: !input.trim() || enviando ? "var(--text-muted)" : "#fff",
                border: "none",
                cursor: !input.trim() || enviando ? "not-allowed" : "pointer",
                fontSize: 13,
                fontFamily: "inherit",
                flexShrink: 0,
              }}
            >
              ↑
            </button>
          </div>
          <div className="label" style={{ color: "var(--text-muted)", textAlign: "center", marginTop: 6 }}>
            Enter para enviar · Shift+Enter para nueva linea
          </div>
        </div>
      </div>
    </div>
  );
}
