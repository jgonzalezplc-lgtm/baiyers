"use client";
import { useCallback, useEffect, useState } from "react";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { ArrowLeft, ChevronDown, ChevronRight, ExternalLink, Paperclip, Check, X, RefreshCw } from "lucide-react";
import { createClient } from "@/lib/supabase/client";
import { authFetch } from "@/lib/authFetch";
import { Card, Badge, BtnPrimary, BtnSecondary, SkeletonText, SkeletonChatBubble, SkeletonBox, CascadeWrapper } from "@/components/ui";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type Proveedor = "gmail" | "outlook";

interface Conversacion {
  id: string;
  proveedor_nombre: string | null;
  proveedor_email: string | null;
  subject: string | null;
  estado: string;
  gmail_url: string | null;
}
interface Mensaje {
  id: string;
  direction: "outbound" | "inbound";
  from_email: string;
  to_email: string;
  subject: string;
  body_text: string;
  received_at: string;
}
interface Adjunto {
  id: string;
  message_id: string;
  filename: string;
  mime_type: string | null;
}
interface Propuesta {
  id: string;
  entity_type: string;
  entity_id: string;
  field: string;
  previous_value: string | null;
  new_value: string;
  currency: string | null;
  confidence: number | null;
  estado: "propuesta" | "aplicado" | "descartado";
  source_id: string;
  // Presente sólo cuando el dato salió de un adjunto y no del cuerpo del correo.
  // Lo resuelve el backend para no tener que cruzar dos arreglos acá.
  source_filename?: string | null;
}

const CAMPO_LABEL: Record<string, string> = {
  precio_unitario: "Precio unitario", moneda: "Moneda", iva_incluido: "IVA incluido",
  descuento: "Descuento", disponibilidad: "Disponibilidad", stock_disponible: "Stock disponible",
  fecha_disponibilidad: "Fecha de disponibilidad", plazo_entrega: "Plazo de entrega",
  fecha_despacho: "Fecha de despacho", lugar_entrega: "Lugar de entrega", costo_despacho: "Costo de despacho",
  condiciones_pago: "Condiciones de pago", porcentaje_anticipo: "% Anticipo", vigencia_oferta: "Vigencia de la oferta",
  marca: "Marca", modelo: "Modelo", sku: "SKU", descripcion_tecnica: "Descripción técnica",
  unidad_medida: "Unidad de medida", cantidad_ofrecida: "Cantidad ofrecida", producto_alternativo: "Producto alternativo",
  garantia: "Garantía", observaciones: "Observaciones", email: "Correo de contacto",
};

function parseVal(v: string | null): string {
  if (v === null || v === undefined) return "—";
  try {
    const p = JSON.parse(v);
    if (p === null) return "—";
    return typeof p === "string" ? p : JSON.stringify(p);
  } catch { return v; }
}

function fmtFechaHora(iso: string) {
  const d = new Date(iso);
  return d.toLocaleString("es-CL", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
}

export default function ConversacionDetallePage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const searchParams = useSearchParams();
  const proveedor: Proveedor = searchParams.get("proveedor") === "outlook" ? "outlook" : "gmail";
  const [userId, setUserId] = useState<string | null>(null);
  const [conv, setConv] = useState<Conversacion | null>(null);
  const [mensajes, setMensajes] = useState<Mensaje[]>([]);
  const [adjuntos, setAdjuntos] = useState<Adjunto[]>([]);
  const [propuestas, setPropuestas] = useState<Propuesta[]>([]);
  const [loading, setLoading] = useState(true);
  const [procesando, setProcesando] = useState<string | null>(null);
  const [colapsados, setColapsados] = useState<Set<string>>(new Set());
  const [reprocesando, setReprocesando] = useState<string | null>(null);

  const cargar = useCallback((uid: string) => {
    setLoading(true);
    authFetch(`${API_URL}/api/${proveedor}/conversaciones/${id}`)
      .then(r => r.json())
      .then(d => {
        setConv(d.conversacion);
        setMensajes(d.mensajes || []);
        setAdjuntos(d.adjuntos || []);
        setPropuestas(d.propuestas || []);
      })
      .finally(() => setLoading(false));
  }, [id, proveedor]);

  useEffect(() => {
    createClient().auth.getUser().then(({ data }) => {
      const uid = data.user?.id;
      if (!uid) { setLoading(false); return; }
      setUserId(uid);
      cargar(uid);
    });
  }, [cargar]);

  const toggleColapsado = (msgId: string) => {
    setColapsados(prev => {
      const next = new Set(prev);
      if (next.has(msgId)) next.delete(msgId); else next.add(msgId);
      return next;
    });
  };

  const reprocesar = async (msgId: string) => {
    if (!userId) return;
    setReprocesando(msgId);
    try {
      const res = await authFetch(`${API_URL}/api/${proveedor}/mensajes/${msgId}/reprocesar`, { method: "POST" });
      if (res.ok) cargar(userId);
    } finally {
      setReprocesando(null);
    }
  };

  const revisar = async (propuestaId: string, accion: "aplicar" | "rechazar") => {
    if (!userId) return;
    setProcesando(propuestaId);
    try {
      const res = await authFetch(`${API_URL}/api/${proveedor}/propuestas/${propuestaId}/${accion}`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      });
      if (res.ok) cargar(userId);
    } finally {
      setProcesando(null);
    }
  };

  if (loading) return (
    <div>
      <div style={{ marginBottom: 24 }}>
        <SkeletonBox height={22} width={260} style={{ marginBottom: 8 }} />
        <SkeletonBox height={13} width={180} />
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "1.4fr 1fr", gap: 20, alignItems: "start" }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <CascadeWrapper>
            <SkeletonChatBubble align="right" width="70%" />
            <SkeletonChatBubble align="left" width="60%" />
            <SkeletonChatBubble align="right" width="55%" />
          </CascadeWrapper>
        </div>
        <Card padding={16}>
          <SkeletonBox height={14} width={140} style={{ marginBottom: 12 }} />
          <SkeletonText lines={3} />
        </Card>
      </div>
    </div>
  );
  if (!conv) return <div style={{ color: "var(--n-600)" }}>Conversación no encontrada.</div>;

  const propuestasPendientes = propuestas.filter(p => p.estado === "propuesta");
  const propuestasDecididas = propuestas.filter(p => p.estado !== "propuesta");
  const adjuntosPorMensaje = (msgId: string) => adjuntos.filter(a => a.message_id === msgId);

  return (
    <div>
      <button
        onClick={() => router.push("/conversaciones")}
        style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: 13.5, color: "var(--n-600)", background: "none", border: "none", cursor: "pointer", marginBottom: 16, padding: 0 }}
      >
        <ArrowLeft size={15} strokeWidth={1.75} /> Conversaciones
      </button>

      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 16, marginBottom: 24, flexWrap: "wrap" }}>
        <div>
          <h1 style={{ fontSize: 22, fontWeight: 600, color: "var(--n-900)", margin: "0 0 4px", letterSpacing: "-0.015em" }}>
            {conv.subject || "Conversación"}
          </h1>
          <div style={{ fontSize: 13.5, color: "var(--n-600)" }}>
            {conv.proveedor_nombre || conv.proveedor_email} {conv.proveedor_email && conv.proveedor_nombre ? `· ${conv.proveedor_email}` : ""}
          </div>
        </div>
        {conv.gmail_url && (
          <a href={conv.gmail_url} target="_blank" rel="noreferrer" className="btn-swiss-secondary" style={{ textDecoration: "none", display: "inline-flex", alignItems: "center", gap: 6 }}>
            <ExternalLink size={15} strokeWidth={1.75} /> Abrir en Gmail
          </a>
        )}
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1.4fr 1fr", gap: 20, alignItems: "start" }}>
        {/* Timeline de mensajes */}
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          {mensajes.map(m => {
            const abierto = !colapsados.has(m.id);
            // Una propuesta sacada de un adjunto apunta al adjunto, no al
            // mensaje: sin mirar también sus adjuntos, un correo que sólo trae
            // el PDF con los precios se vería como si no hubiera aportado nada.
            const idsDelMensaje = new Set([m.id, ...adjuntosPorMensaje(m.id).map(a => a.id)]);
            const tienePropuesta = propuestas.some(p => idsDelMensaje.has(p.source_id));
            return (
              <Card key={m.id} padding={16} style={{ background: m.direction === "outbound" ? "var(--brand-50)" : "var(--surface)" }}>
                <button
                  onClick={() => toggleColapsado(m.id)}
                  style={{ display: "flex", width: "100%", justifyContent: "space-between", alignItems: "center", gap: 10, background: "none", border: "none", cursor: "pointer", padding: 0, marginBottom: abierto ? 8 : 0, textAlign: "left" }}
                >
                  <span style={{ display: "flex", alignItems: "center", gap: 6, minWidth: 0 }}>
                    {abierto ? <ChevronDown size={14} strokeWidth={1.75} color="var(--n-500)" /> : <ChevronRight size={14} strokeWidth={1.75} color="var(--n-500)" />}
                    <span style={{ fontSize: 12.5, fontWeight: 600, color: m.direction === "outbound" ? "var(--brand-700)" : "var(--n-700)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                      {m.subject || (m.direction === "outbound" ? "Baiyer → proveedor" : "Proveedor")}
                    </span>
                  </span>
                  <span style={{ fontSize: 12, color: "var(--n-500)", flexShrink: 0 }}>{fmtFechaHora(m.received_at)}</span>
                </button>
                {abierto && (
                  <>
                    <div style={{ fontSize: 13.5, color: "var(--n-800)", whiteSpace: "pre-wrap", lineHeight: 1.6 }}>{m.body_text || "(sin contenido de texto)"}</div>
                    {adjuntosPorMensaje(m.id).length > 0 && (
                      <div style={{ marginTop: 10, display: "flex", flexWrap: "wrap", gap: 6 }}>
                        {adjuntosPorMensaje(m.id).map(a => (
                          <span key={a.id} style={{ display: "inline-flex", alignItems: "center", gap: 4, fontSize: 12, color: "var(--n-600)", background: "var(--canvas)", border: "1px solid var(--n-200)", borderRadius: "var(--r-pill)", padding: "3px 10px" }}>
                            <Paperclip size={12} strokeWidth={1.75} /> {a.filename}
                          </span>
                        ))}
                      </div>
                    )}
                    {/* Antes esto era `!tienePropuesta`, así que el botón se
                        escondía justo cuando más hacía falta: un correo mal
                        interpretado SÍ genera propuestas, sólo que equivocadas.
                        Pasó con la ampolleta del 2026-08-26, donde una segunda
                        propuesta pisó $19.990 con $25.000 y no había forma de
                        reprocesar desde la UI. */}
                    {m.direction === "inbound" && (
                      <button
                        onClick={() => reprocesar(m.id)}
                        disabled={reprocesando === m.id}
                        style={{ display: "inline-flex", alignItems: "center", gap: 5, marginTop: 10, fontSize: 12, color: "var(--brand)", background: "none", border: "none", cursor: "pointer", padding: 0 }}
                      >
                        <RefreshCw size={12} strokeWidth={1.75} />
                        {reprocesando === m.id
                          ? "Reprocesando…"
                          : tienePropuesta ? "Volver a interpretar este correo" : "Reprocesar este correo"}
                      </button>
                    )}
                  </>
                )}
              </Card>
            );
          })}
          {mensajes.length === 0 && <div style={{ color: "var(--n-500)", fontSize: 13.5 }}>Sin mensajes registrados todavía.</div>}
        </div>

        {/* Propuestas */}
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          <div>
            <div style={{ fontSize: 14, fontWeight: 600, color: "var(--n-900)", marginBottom: 10 }}>
              Propuestas pendientes {propuestasPendientes.length > 0 && `(${propuestasPendientes.length})`}
            </div>
            {propuestasPendientes.length === 0 ? (
              <div style={{ fontSize: 13, color: "var(--n-500)" }}>Nada pendiente de revisión.</div>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                {propuestasPendientes.map(p => (
                  <Card key={p.id} padding={14}>
                    <div style={{ fontSize: 13, fontWeight: 600, color: "var(--n-900)", marginBottom: 4 }}>
                      {CAMPO_LABEL[p.field] || p.field}
                    </div>
                    <div style={{ fontSize: 13, color: "var(--n-700)", marginBottom: 2 }}>
                      <span style={{ color: "var(--n-500)" }}>Antes: </span>{parseVal(p.previous_value)}
                    </div>
                    <div style={{ fontSize: 13, color: "var(--n-900)", fontWeight: 500, marginBottom: 8 }}>
                      <span style={{ color: "var(--n-500)", fontWeight: 400 }}>Nuevo: </span>
                      {parseVal(p.new_value)}{p.currency ? ` ${p.currency}` : ""}
                    </div>
                    {/* De dónde salió el dato. Sin esto no hay forma de juzgar
                        la propuesta: no es lo mismo un precio leído de la prosa
                        del correo que uno sacado de una tabla en un PDF. */}
                    {p.source_filename && (
                      <div style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 12, color: "var(--n-500)", marginBottom: 8 }}>
                        <Paperclip size={12} strokeWidth={1.75} />
                        <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                          Leído de {p.source_filename}
                        </span>
                      </div>
                    )}
                    {typeof p.confidence === "number" && (
                      <div style={{ marginBottom: 10 }}>
                        <Badge tipo={p.confidence >= 0.85 ? "success" : p.confidence >= 0.5 ? "warning" : "error"}>
                          Confianza {Math.round(p.confidence * 100)}%
                        </Badge>
                      </div>
                    )}
                    <div style={{ display: "flex", gap: 8 }}>
                      <BtnPrimary onClick={() => revisar(p.id, "aplicar")} disabled={procesando === p.id} style={{ flex: 1, fontSize: 13, padding: "6px 10px" }}>
                        <Check size={14} strokeWidth={2} style={{ marginRight: 4 }} /> Aplicar
                      </BtnPrimary>
                      <BtnSecondary onClick={() => revisar(p.id, "rechazar")} disabled={procesando === p.id} style={{ fontSize: 13, padding: "6px 10px" }}>
                        <X size={14} strokeWidth={2} />
                      </BtnSecondary>
                    </div>
                  </Card>
                ))}
              </div>
            )}
          </div>

          {propuestasDecididas.length > 0 && (
            <div>
              <div style={{ fontSize: 13, fontWeight: 600, color: "var(--n-600)", marginBottom: 8 }}>Ya revisadas</div>
              <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                {propuestasDecididas.map(p => (
                  <div key={p.id} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", fontSize: 12.5, color: "var(--n-600)", padding: "6px 10px", background: "var(--canvas)", borderRadius: "var(--r-md)" }}>
                    <span>
                      {CAMPO_LABEL[p.field] || p.field}: {parseVal(p.new_value)}
                      {p.source_filename && ` · ${p.source_filename}`}
                    </span>
                    <Badge tipo={p.estado === "aplicado" ? "success" : "default"}>{p.estado === "aplicado" ? "Aplicada" : "Descartada"}</Badge>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
