"use client";
import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { createClient } from "@/lib/supabase/client";
import {
  API_URL, ESTADO_META, BADGE_META, EVENTO_ESTADO_META, TIMELINE_ICON,
  fmtPrecio, fmtFecha, fmtFechaHora, type EstadoProveedor, type Badge,
} from "../constants";
import AnalisisIA from "./AnalisisIA";

interface QuoteSupplier {
  id: string;
  proveedor_nombre: string;
  proveedor_email: string | null;
  fuente: string | null;
  url_referencia: string | null;
  precio_referencial: number | null;
  moneda_referencial: string;
  precio_cotizado: number | null;
  moneda_cotizada: string;
  plazo_entrega_estimado: string | null;
  plazo_entrega_dias: number | null;
  condiciones: string | null;
  estado: EstadoProveedor;
  badge: Badge | null;
  oc_numero: string | null;
  oc_emitida_at: string | null;
  despacho_recibido_at: string | null;
}

interface QuoteItem {
  id: string;
  nombre: string;
  descripcion: string | null;
  numero_parte: string | null;
  marca: string | null;
  cantidad: number;
  unidad: string;
  proveedores: QuoteSupplier[];
}

interface TimelineEntry {
  id: string;
  tipo: string;
  descripcion: string;
  created_at: string;
}

interface Detalle {
  evento: { id: string; nombre: string; descripcion: string | null; estado: string; created_at: string };
  items: QuoteItem[];
  timeline: TimelineEntry[];
}

const BADGE_ORDER: (Badge | null)[] = ["mas_conveniente", "mas_economico", "disponibilidad_inmediata", null];

function BadgeChip({ badge }: { badge: Badge }) {
  const m = BADGE_META[badge];
  return (
    <span className="label" style={{
      color: m.color, background: m.bg, border: `1px solid ${m.border}`,
      padding: "1px 6px", fontWeight: 700, whiteSpace: "nowrap",
    }}>{m.label}</span>
  );
}

export default function ProcurementDetailPage() {
  const params = useParams();
  const eventoId = params.id as string;
  const [userId, setUserId] = useState<string | null>(null);
  const [data, setData] = useState<Detalle | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);

  // Modales
  const [respModal, setRespModal] = useState<QuoteSupplier | null>(null);
  const [ocModal, setOcModal] = useState<{ qs: QuoteSupplier; item: QuoteItem } | null>(null);

  useEffect(() => {
    createClient().auth.getUser().then(({ data }) => setUserId(data.user?.id ?? null));
  }, []);

  const cargar = useCallback(async () => {
    if (!userId) return;
    const r = await fetch(`${API_URL}/api/procurement/eventos/${eventoId}?user_id=${userId}`);
    if (r.ok) setData(await r.json());
    setLoading(false);
  }, [userId, eventoId]);

  useEffect(() => { cargar(); }, [cargar]);

  const accion = async (url: string, body?: object, method = "POST") => {
    setBusy(url);
    try {
      await fetch(`${API_URL}${url}`, {
        method,
        headers: { "Content-Type": "application/json" },
        body: body ? JSON.stringify(body) : undefined,
      });
      await cargar();
    } finally {
      setBusy(null);
    }
  };

  const cotizar = (qsIds: string[]) =>
    accion(`/api/procurement/cotizar`, { user_id: userId, quote_supplier_ids: qsIds });

  const setBadge = (qsId: string, badge: Badge | null) =>
    accion(`/api/procurement/proveedores/${qsId}/badge`, { badge }, "PATCH");

  if (loading) return <div style={{ padding: 32 }} className="label">Cargando…</div>;
  if (!data) return <div style={{ padding: 32 }} className="label">Evento no encontrado.</div>;

  const em = EVENTO_ESTADO_META[data.evento.estado] ?? EVENTO_ESTADO_META.borrador;
  const pendientes = data.items.flatMap((i) => i.proveedores.filter((p) => p.estado === "pendiente_cotizar").map((p) => p.id));

  return (
    <div style={{ maxWidth: 1280, margin: "0 auto", padding: "24px 24px 64px" }}>
      {/* Header */}
      <Link href="/procurement" className="label" style={{ color: "var(--text-muted)", textDecoration: "none" }}>← Listas de cotización</Link>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", margin: "10px 0 20px" }}>
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <h1 style={{ fontSize: 22, fontWeight: 800, letterSpacing: "-0.02em", margin: 0 }}>{data.evento.nombre}</h1>
            <span className="label" style={{ color: em.color, background: em.bg, padding: "2px 8px", fontWeight: 700 }}>{em.label}</span>
          </div>
          {data.evento.descripcion && <p className="label" style={{ color: "var(--text-muted)", marginTop: 4 }}>{data.evento.descripcion}</p>}
        </div>
        {pendientes.length > 0 && (
          <button className="btn-swiss-primary" style={{ fontSize: 12, padding: "8px 14px" }}
            disabled={busy !== null} onClick={() => cotizar(pendientes)}>
            Cotizar todos ({pendientes.length})
          </button>
        )}
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 300px", gap: 20, alignItems: "start" }}>
        {/* ─── Lista de cotización (eje central) ─── */}
        <div>
          {data.items.map((item) => (
            <div key={item.id} style={{ marginBottom: 18, border: "1px solid var(--border-strong)" }}>
              {/* Cabecera del ítem */}
              <div style={{ padding: "10px 14px", background: "var(--bg-inverse)", color: "var(--text-inverse)", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <div>
                  <span style={{ fontSize: 13, fontWeight: 700 }}>{item.nombre}</span>
                  {item.marca && <span className="label" style={{ marginLeft: 8, opacity: 0.7 }}>{item.marca}</span>}
                  {item.numero_parte && <span className="label" style={{ marginLeft: 8, opacity: 0.7, fontFamily: "var(--font-mono)" }}>{item.numero_parte}</span>}
                </div>
                <span className="label" style={{ opacity: 0.8 }}>{item.cantidad} {item.unidad}</span>
              </div>

              {/* Cabecera de columnas */}
              <div style={{
                display: "grid", gridTemplateColumns: "1fr 110px 120px 100px 120px 200px",
                gap: 8, padding: "6px 14px", background: "var(--bg-surface)", borderBottom: "1px solid var(--border-default)",
              }}>
                {["PROVEEDOR", "PRECIO REF.", "PRECIO COTIZ.", "PLAZO", "ESTADO", "ACCIONES"].map((h) => (
                  <span key={h} className="label" style={{ fontWeight: 700 }}>{h}</span>
                ))}
              </div>

              {/* Filas de proveedores */}
              {item.proveedores.length === 0 && (
                <div className="label" style={{ padding: "12px 14px", color: "var(--text-muted)" }}>Sin proveedores. Agrega desde la búsqueda.</div>
              )}
              {item.proveedores.map((p) => {
                const sm = ESTADO_META[p.estado];
                return (
                  <div key={p.id} style={{
                    display: "grid", gridTemplateColumns: "1fr 110px 120px 100px 120px 200px",
                    gap: 8, padding: "10px 14px", borderBottom: "1px solid var(--border-subtle)",
                    alignItems: "center", opacity: sm.tachado ? 0.5 : 1,
                    borderLeft: p.badge === "mas_conveniente" ? "3px solid #c0392b" : "3px solid transparent",
                  }}>
                    {/* Proveedor + badge */}
                    <div style={{ minWidth: 0 }}>
                      <div style={{ fontSize: 12, fontWeight: 700, textDecoration: sm.tachado ? "line-through" : "none", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                        {p.url_referencia ? (
                          <a href={p.url_referencia} target="_blank" rel="noopener noreferrer" style={{ color: "inherit", textDecoration: "none" }}>{p.proveedor_nombre}</a>
                        ) : p.proveedor_nombre}
                      </div>
                      <div style={{ display: "flex", gap: 4, alignItems: "center", marginTop: 3, flexWrap: "wrap" }}>
                        {p.badge && <BadgeChip badge={p.badge} />}
                        {p.fuente && <span className="label" style={{ color: "var(--text-muted)" }}>{p.fuente}</span>}
                        {/* Selector de badge */}
                        <select value={p.badge ?? ""} disabled={busy !== null}
                          onChange={(e) => setBadge(p.id, (e.target.value || null) as Badge | null)}
                          className="label" style={{ border: "1px solid var(--border-default)", background: "var(--bg-base)", padding: "0 2px", fontSize: 9, cursor: "pointer" }}>
                          {BADGE_ORDER.map((b) => (
                            <option key={b ?? "none"} value={b ?? ""}>{b ? BADGE_META[b].label : "— sin badge"}</option>
                          ))}
                        </select>
                      </div>
                    </div>
                    <span className="label" style={{ fontFamily: "var(--font-mono)" }}>{fmtPrecio(p.precio_referencial, p.moneda_referencial)}</span>
                    <span className="label" style={{ fontFamily: "var(--font-mono)", fontWeight: p.precio_cotizado ? 700 : 400 }}>{fmtPrecio(p.precio_cotizado, p.moneda_cotizada)}</span>
                    <span className="label">{p.plazo_entrega_estimado || (p.plazo_entrega_dias != null ? `${p.plazo_entrega_dias}d` : "—")}</span>
                    <span className="label" style={{ color: sm.color, background: sm.bg, padding: "2px 6px", justifySelf: "start", fontWeight: 700, whiteSpace: "nowrap" }}>{sm.label}</span>

                    {/* Acciones según estado */}
                    <div style={{ display: "flex", gap: 4, flexWrap: "wrap", justifyContent: "flex-end" }}>
                      {p.estado === "pendiente_cotizar" && (
                        <button className="btn-swiss-primary" style={btnSm} disabled={busy !== null} onClick={() => cotizar([p.id])}>Cotizar</button>
                      )}
                      {(p.estado === "correo_enviado" || p.estado === "respuesta_recibida") && (
                        <button className="btn-swiss-secondary" style={btnSm} onClick={() => setRespModal(p)}>
                          {p.estado === "respuesta_recibida" ? "Editar resp." : "Registrar resp."}
                        </button>
                      )}
                      {p.estado === "respuesta_recibida" && (
                        <button className="btn-swiss-primary" style={btnSm} disabled={busy !== null}
                          onClick={() => accion(`/api/procurement/proveedores/${p.id}/seleccionar`)}>Seleccionar</button>
                      )}
                      {p.estado === "seleccionado" && (
                        <button className="btn-swiss-primary" style={btnSm} onClick={() => setOcModal({ qs: p, item })}>Emitir OC</button>
                      )}
                      {p.estado === "oc_emitida" && !p.despacho_recibido_at && (
                        <button className="btn-swiss-secondary" style={btnSm} disabled={busy !== null}
                          onClick={() => accion(`/api/procurement/proveedores/${p.id}/recibir`)}>Marcar recibido</button>
                      )}
                      {p.estado === "oc_emitida" && p.despacho_recibido_at && (
                        <span className="label" style={{ color: "var(--text-success)" }}>✓ Recibido</span>
                      )}
                      {p.estado !== "oc_emitida" && p.estado !== "descartado" && (
                        <button className="btn-swiss-secondary" style={{ ...btnSm, color: "var(--text-muted)" }} disabled={busy !== null}
                          onClick={() => accion(`/api/procurement/proveedores/${p.id}`, undefined, "DELETE")}>×</button>
                      )}
                    </div>
                  </div>
                );
              })}

              {/* Análisis comparativo IA (Claude) */}
              {userId && item.proveedores.filter(p => p.estado !== "descartado").length >= 2 && (
                <AnalisisIA
                  userId={userId}
                  itemNombre={item.nombre}
                  cantidad={item.cantidad}
                  opciones={item.proveedores.filter(p => p.estado !== "descartado").map(p => ({
                    proveedor_nombre: p.proveedor_nombre,
                    fuente: p.fuente,
                    precio: p.precio_referencial,
                    moneda: p.moneda_referencial,
                    precio_cotizado: p.precio_cotizado,
                    plazo_entrega_estimado: p.plazo_entrega_estimado,
                    plazo_entrega_dias: p.plazo_entrega_dias,
                    condiciones: p.condiciones,
                    url: p.url_referencia,
                  }))}
                />
              )}
            </div>
          ))}
        </div>

        {/* ─── Timeline lateral ─── */}
        <aside style={{ border: "1px solid var(--border-default)", position: "sticky", top: 16 }}>
          <div style={{ padding: "10px 14px", borderBottom: "1px solid var(--border-default)", background: "var(--bg-surface)" }}>
            <span className="label" style={{ fontWeight: 700 }}>TIMELINE</span>
          </div>
          <div style={{ maxHeight: "70vh", overflowY: "auto" }}>
            {data.timeline.length === 0 && <div className="label" style={{ padding: 14, color: "var(--text-muted)" }}>Sin eventos aún.</div>}
            {data.timeline.map((t) => (
              <div key={t.id} style={{ display: "flex", gap: 10, padding: "10px 14px", borderBottom: "1px solid var(--border-subtle)" }}>
                <span style={{ fontSize: 13, flexShrink: 0 }}>{TIMELINE_ICON[t.tipo] ?? "•"}</span>
                <div style={{ minWidth: 0 }}>
                  <div style={{ fontSize: 11, lineHeight: 1.4 }}>{t.descripcion}</div>
                  <div className="label" style={{ color: "var(--text-muted)", marginTop: 2 }}>{fmtFechaHora(t.created_at)}</div>
                </div>
              </div>
            ))}
          </div>
        </aside>
      </div>

      {respModal && (
        <RespuestaModal qs={respModal} onClose={() => setRespModal(null)}
          onSave={async (body) => { await accion(`/api/procurement/proveedores/${respModal.id}/respuesta`, body); setRespModal(null); }} />
      )}
      {ocModal && (
        <OCModal qs={ocModal.qs} item={ocModal.item} onClose={() => setOcModal(null)}
          onConfirm={async (body) => { await accion(`/api/procurement/proveedores/${ocModal.qs.id}/emitir-oc`, { user_id: userId, ...body }); setOcModal(null); }} />
      )}
    </div>
  );
}

const btnSm: React.CSSProperties = { fontSize: 10, padding: "4px 8px" };

// ─── Modal registrar respuesta ───
function RespuestaModal({ qs, onClose, onSave }: {
  qs: QuoteSupplier; onClose: () => void;
  onSave: (b: object) => void;
}) {
  const [precio, setPrecio] = useState(qs.precio_cotizado?.toString() ?? "");
  const [plazoDias, setPlazoDias] = useState(qs.plazo_entrega_dias?.toString() ?? "");
  const [plazoTxt, setPlazoTxt] = useState(qs.plazo_entrega_estimado ?? "");
  const [cond, setCond] = useState(qs.condiciones ?? "");
  return (
    <Overlay onClose={onClose}>
      <h2 style={modalTitle}>Registrar respuesta — {qs.proveedor_nombre}</h2>
      <Field label="Precio cotizado (CLP)"><input type="number" value={precio} onChange={(e) => setPrecio(e.target.value)} style={inputStyle} /></Field>
      <Field label="Plazo (texto, ej. 3-5 días)"><input value={plazoTxt} onChange={(e) => setPlazoTxt(e.target.value)} style={inputStyle} /></Field>
      <Field label="Plazo (días, para calendario)"><input type="number" value={plazoDias} onChange={(e) => setPlazoDias(e.target.value)} style={inputStyle} /></Field>
      <Field label="Condiciones"><textarea value={cond} onChange={(e) => setCond(e.target.value)} rows={2} style={inputStyle} /></Field>
      <ModalActions onClose={onClose} onConfirm={() => onSave({
        precio_cotizado: precio ? parseFloat(precio) : null,
        moneda_cotizada: "CLP",
        plazo_entrega_estimado: plazoTxt || null,
        plazo_entrega_dias: plazoDias ? parseInt(plazoDias) : null,
        condiciones: cond || null,
      })} confirmLabel="Guardar respuesta" />
    </Overlay>
  );
}

// ─── Modal emitir OC ───
function OCModal({ qs, item, onClose, onConfirm }: {
  qs: QuoteSupplier; item: QuoteItem; onClose: () => void;
  onConfirm: (b: object) => void;
}) {
  const [recurrente, setRecurrente] = useState(false);
  const [frecuencia, setFrecuencia] = useState("mensual");
  const precio = qs.precio_cotizado ?? qs.precio_referencial ?? 0;
  const total = precio * item.cantidad;
  return (
    <Overlay onClose={onClose}>
      <h2 style={modalTitle}>Emitir orden de compra</h2>
      <div style={{ border: "1px solid var(--border-default)", padding: 12, marginBottom: 14 }}>
        <Row k="Proveedor" v={qs.proveedor_nombre} />
        <Row k="Ítem" v={`${item.nombre} · ${item.cantidad} ${item.unidad}`} />
        <Row k="Precio unitario" v={fmtPrecio(precio)} />
        <Row k="Total" v={fmtPrecio(total)} bold />
      </div>
      <label style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer", marginBottom: 10 }}>
        <input type="checkbox" checked={recurrente} onChange={(e) => setRecurrente(e.target.checked)} />
        <span style={{ fontSize: 12, fontWeight: 700 }}>Compra recurrente</span>
      </label>
      {recurrente && (
        <Field label="Frecuencia">
          <select value={frecuencia} onChange={(e) => setFrecuencia(e.target.value)} style={inputStyle}>
            <option value="semanal">Semanal</option>
            <option value="mensual">Mensual</option>
            <option value="trimestral">Trimestral</option>
          </select>
        </Field>
      )}
      <ModalActions onClose={onClose} onConfirm={() => onConfirm({ recurrente, frecuencia: recurrente ? frecuencia : null })} confirmLabel="Confirmar OC" />
    </Overlay>
  );
}

// ─── Primitivas de modal ───
function Overlay({ children, onClose }: { children: React.ReactNode; onClose: () => void }) {
  return (
    <div onClick={onClose} style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.4)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 50 }}>
      <div onClick={(e) => e.stopPropagation()} style={{ background: "var(--bg-elevated)", border: "1px solid var(--border-strong)", padding: 24, width: 420, maxWidth: "90vw" }}>
        {children}
      </div>
    </div>
  );
}
const modalTitle: React.CSSProperties = { fontSize: 15, fontWeight: 800, margin: "0 0 16px" };
const inputStyle: React.CSSProperties = { width: "100%", border: "1px solid var(--border-default)", background: "var(--bg-base)", padding: "6px 8px", fontSize: 12, fontFamily: "inherit" };
function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return <div style={{ marginBottom: 10 }}><div className="label" style={{ marginBottom: 3 }}>{label}</div>{children}</div>;
}
function Row({ k, v, bold }: { k: string; v: string; bold?: boolean }) {
  return <div style={{ display: "flex", justifyContent: "space-between", padding: "3px 0", fontSize: 12, fontWeight: bold ? 800 : 400 }}><span className="label">{k}</span><span>{v}</span></div>;
}
function ModalActions({ onClose, onConfirm, confirmLabel }: { onClose: () => void; onConfirm: () => void; confirmLabel: string }) {
  return (
    <div style={{ display: "flex", gap: 8, justifyContent: "flex-end", marginTop: 16 }}>
      <button className="btn-swiss-secondary" style={{ fontSize: 12, padding: "8px 14px" }} onClick={onClose}>Cancelar</button>
      <button className="btn-swiss-primary" style={{ fontSize: 12, padding: "8px 14px" }} onClick={onConfirm}>{confirmLabel}</button>
    </div>
  );
}
