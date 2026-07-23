"use client";
import { useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import dynamic from "next/dynamic";
import { createClient } from "@/lib/supabase/client";

const InformeLista = dynamic(() => import("@/components/InformeLista"), { ssr: false });

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export interface ComparadoLista {
  resultado_id: string;
  proveedor: string | null;
  fuente: string | null;
  precio: number | null;
  moneda: string;
  precio_cotizado: number | null;
  plazo_entrega: string | null;
  ubicacion: string | null;
  contacto: string | null;
  url: string;
  descripcion: string | null;
}

export interface Definitivo {
  resultado_id: string | null;
  proveedor: string | null;
  precio: number | null;
  moneda: string;
  url: string | null;
  fuente: string | null;
  precio_clp: number | null;
}

export interface ItemLista {
  cotizacion_id: string;
  nombre: string;
  cantidad: number;
  comparado: boolean;
  comparados: ComparadoLista[];
  definitivo: Definitivo | null;
}

interface Aprobacion {
  estado: "pendiente" | "aprobado" | "rechazado";
  aprobador_email?: string;
  token?: string;
  comentario_rechazo?: string;
  decidido_at?: string;
}

export interface DetalleLista {
  id: string;
  nombre: string;
  created_at: string | null;
  monto_total: number;
  items: ItemLista[];
  aprobacion?: Aprobacion;
  justificaciones?: Record<string, string>;
}

const FUENTE_LABEL: Record<string, string> = {
  mercadolibre: "MercadoLibre", google: "Google Shopping",
  mouser: "Mouser", digikey: "DigiKey", tme: "TME", manual: "Manual",
  sodimac: "Sodimac", easy: "Easy", lasierra: "La Sierra", construmart: "Construmart",
  vitel: "Vitel", dartel: "Dartel", ferrelectrica: "Ferrelectrica", gobantes: "Gobantes", rhona: "Rhona",
  clcsa: "CLC Maderas", wmaderas: "W Maderas", ferramenta: "Ferramenta", maderas_dir: "Aserraderos CL",
};

const fmtCLP = (n: number) => `$${Math.round(n).toLocaleString("es-CL")}`;
const fmtPrecio = (n: number, m: string) =>
  m === "CLP" ? fmtCLP(n) : `${n.toLocaleString("en-US", { minimumFractionDigits: 2 })} ${m}`;

export default function ListaDetallePage() {
  const { id } = useParams<{ id: string }>();
  const [userId, setUserId] = useState<string | null>(null);
  const [lista, setLista] = useState<DetalleLista | null>(null);
  const [loading, setLoading] = useState(true);
  const [toast, setToast] = useState("");
  const [tasas, setTasas] = useState<Record<string, number>>({});
  const [guardandoDef, setGuardandoDef] = useState<string | null>(null);
  const [justificaciones, setJustificaciones] = useState<Record<string, string>>({});
  const [aprobadorEmail, setAprobadorEmail] = useState("");
  const [solicitando, setSolicitando] = useState(false);
  const [mostrarAprobacion, setMostrarAprobacion] = useState(false);
  const [userMeta, setUserMeta] = useState<Record<string, string>>({});

  const aCLP = useCallback((valor: number, moneda: string | null | undefined): number => {
    const m = moneda || "CLP";
    if (m === "CLP") return valor;
    return (valor / (tasas[m] ?? 1)) * (tasas.CLP ?? 950);
  }, [tasas]);

  const cargar = useCallback(async (uid: string) => {
    try {
      const res = await fetch(`${API_URL}/api/listas/${id}?user_id=${uid}`);
      if (res.ok) {
        const data = await res.json();
        setLista(data);
        if (data.justificaciones) setJustificaciones(data.justificaciones);
      }
    } catch { /* silent */ }
    setLoading(false);
  }, [id]);

  useEffect(() => {
    fetch("https://open.er-api.com/v6/latest/USD")
      .then(r => r.json())
      .then(d => { if (d.rates) setTasas(d.rates); })
      .catch(() => setTasas({ CLP: 950, EUR: 0.92, CNY: 7.25, GBP: 0.79 }));
    createClient().auth.getUser().then(({ data }) => {
      const uid = data.user?.id ?? null;
      setUserId(uid);
      if (uid) cargar(uid); else setLoading(false);
      const m = data.user?.user_metadata ?? {};
      setUserMeta(m);
      if (m.autorizador_email) setAprobadorEmail(m.autorizador_email);
    });
  }, [cargar]);

  const elegirDefinitivo = async (item: ItemLista, c: ComparadoLista) => {
    if (!userId) return;
    const precio = c.precio_cotizado ?? c.precio;
    const moneda = c.precio_cotizado != null ? "CLP" : c.moneda;
    setGuardandoDef(item.cotizacion_id);
    try {
      await fetch(`${API_URL}/api/listas/${id}/definitivo`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          user_id: userId,
          cotizacion_id: item.cotizacion_id,
          resultado_id: c.resultado_id,
          proveedor: c.proveedor,
          precio, moneda,
          url: c.url, fuente: c.fuente,
          precio_clp: precio != null ? aCLP(precio, moneda) : null,
        }),
      });
      setToast(`Definitivo para ${item.nombre}: ${c.proveedor}`);
      setTimeout(() => setToast(""), 3000);
      await cargar(userId);
    } catch {
      setToast("No se pudo guardar el definitivo");
      setTimeout(() => setToast(""), 3000);
    } finally {
      setGuardandoDef(null);
    }
  };

  const actualizarCantidad = async (item: ItemLista, cantidad: number) => {
    if (!userId || cantidad <= 0 || cantidad === item.cantidad) return;
    // Optimista: refleja al tiro en la UI
    setLista(prev => prev ? {
      ...prev,
      items: prev.items.map(it => it.cotizacion_id === item.cotizacion_id ? { ...it, cantidad } : it),
    } : prev);
    try {
      await fetch(`${API_URL}/api/listas/${id}/cantidad`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user_id: userId, cotizacion_id: item.cotizacion_id, cantidad }),
      });
    } catch {
      setToast("No se pudo guardar la cantidad");
      setTimeout(() => setToast(""), 3000);
    }
  };

  const quitarDefinitivo = async (item: ItemLista) => {
    if (!userId) return;
    setGuardandoDef(item.cotizacion_id);
    try {
      await fetch(`${API_URL}/api/listas/${id}/definitivo`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user_id: userId, cotizacion_id: item.cotizacion_id, quitar: true }),
      });
      await cargar(userId);
    } catch { /* silent */ } finally { setGuardandoDef(null); }
  };

  const autoSeleccionarBaratos = async () => {
    if (!userId || !lista) return;
    for (const it of lista.items) {
      if (it.definitivo) continue;
      const comparados = it.comparados.filter(c => (c.precio_cotizado ?? c.precio) != null);
      if (!comparados.length) continue;
      comparados.sort((a, b) => {
        const pa = aCLP(a.precio_cotizado ?? a.precio!, a.precio_cotizado != null ? "CLP" : a.moneda);
        const pb = aCLP(b.precio_cotizado ?? b.precio!, b.precio_cotizado != null ? "CLP" : b.moneda);
        return pa - pb;
      });
      await elegirDefinitivo(it, comparados[0]);
    }
  };

  const solicitarAprobacion = async () => {
    if (!userId || !lista || !aprobadorEmail.trim()) return;
    setSolicitando(true);
    try {
      const res = await fetch(`${API_URL}/api/listas/${id}/solicitar-aprobacion`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          user_id: userId,
          aprobador_email: aprobadorEmail.trim(),
          justificaciones,
          nombre_solicitante: userMeta.nombre_usuario ?? "",
          empresa: userMeta.empresa ?? "",
        }),
      });
      if (!res.ok) {
        const d = await res.json().catch(() => ({}));
        throw new Error(d.detail ?? "Error al solicitar");
      }
      const data = await res.json();

      const defItems = lista.items.filter(it => it.definitivo);
      const totalStr = fmtCLP(defItems.reduce((s, it) => s + (it.definitivo!.precio_clp ?? 0) * (it.cantidad || 1), 0));
      const itemLines = defItems.map(it =>
        `- ${it.nombre} ×${it.cantidad || 1}: ${it.definitivo!.proveedor} (${it.definitivo!.precio_clp != null ? fmtCLP(it.definitivo!.precio_clp * (it.cantidad || 1)) : "—"})${justificaciones[it.cotizacion_id] ? ` — ${justificaciones[it.cotizacion_id]}` : ""}`
      ).join("\n");

      const subject = encodeURIComponent(`Solicitud de aprobación: ${lista.nombre}`);
      const body = encodeURIComponent(
        `Hola,\n\n${userMeta.nombre_usuario ?? "Un usuario"} de ${userMeta.empresa ?? "la empresa"} solicita tu aprobación para la siguiente lista de compra:\n\n` +
        `Lista: ${lista.nombre}\nTotal: ${totalStr}\n\n${itemLines}\n\n` +
        `Para aprobar:\n${data.magic_link_aprobar}\n\n` +
        `Para rechazar (puedes agregar comentarios):\n${data.magic_link_rechazar}\n\n` +
        `Este enlace expira el ${new Date(data.expira_at).toLocaleDateString("es-CL")}.\n\nBaiyer — Procurement Inteligente`
      );

      window.open(`mailto:${aprobadorEmail.trim()}?subject=${subject}&body=${body}`, "_self");
      setToast("Solicitud creada — se abrió tu correo para enviar");
      setTimeout(() => setToast(""), 4000);
      setMostrarAprobacion(false);
      await cargar(userId);
    } catch (e) {
      setToast(e instanceof Error ? e.message : "Error al solicitar aprobación");
      setTimeout(() => setToast(""), 3500);
    } finally {
      setSolicitando(false);
    }
  };

  const reiniciarAprobacion = async () => {
    if (!userId) return;
    try {
      await fetch(`${API_URL}/api/listas/${id}/reenviar-aprobacion`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user_id: userId }),
      });
      setToast("Lista desbloqueada — puedes modificarla y re-solicitar");
      setTimeout(() => setToast(""), 3500);
      await cargar(userId);
    } catch {
      setToast("Error al reiniciar aprobación");
      setTimeout(() => setToast(""), 3000);
    }
  };

  if (loading) return <div style={{ padding: "60px 0", textAlign: "center", fontSize: 12, color: "var(--text-muted)" }}>Cargando…</div>;
  if (!lista) return <div style={{ padding: "60px 0", textAlign: "center", fontSize: 12, color: "var(--text-muted)" }}>Lista no encontrada.</div>;

  const definitivos = lista.items.filter(it => it.definitivo);
  const totalCLP = definitivos.reduce((a, it) => a + (it.definitivo?.precio_clp ?? 0) * (it.cantidad || 1), 0);
  const completa = definitivos.length === lista.items.length;

  return (
    <>
      {toast && (
        <div style={{
          position: "fixed", top: 20, right: 20, zIndex: 999,
          background: "var(--bg-inverse)", color: "var(--text-inverse)",
          padding: "12px 20px", fontSize: 11, fontWeight: 700, border: "1px solid var(--border-strong)",
        }}>{toast}</div>
      )}

      {/* Header */}
      <div style={{ marginBottom: 20 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12 }}>
          <Link href="/listas" style={{ fontSize: 10, color: "var(--text-muted)", textDecoration: "none", fontFamily: "var(--font-mono)" }}>
            ← Listas de cotización
          </Link>
        </div>
        <div className="section-rule" style={{ marginBottom: 14 }} />
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 16, flexWrap: "wrap" }}>
          <div>
            <h1 style={{ fontSize: 22, fontWeight: 700, color: "var(--text-primary)", margin: "0 0 6px", letterSpacing: "-0.02em" }}>
              {lista.nombre}
            </h1>
            <div className="label" style={{ color: "var(--text-muted)" }}>
              {lista.items.length} ítems · {lista.items.filter(i => i.comparado).length} comparados · {definitivos.length} definitivos
            </div>
          </div>
          <InformeLista listaId={lista.id} userId={userId ?? ""} nombreLista={lista.nombre} />
        </div>
      </div>

      {/* Resumen */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", border: "1px solid var(--border-default)", marginBottom: 24 }}>
        {[
          { label: "DEFINITIVOS ELEGIDOS", val: `${definitivos.length}/${lista.items.length}`, color: completa ? "var(--text-success)" : undefined },
          { label: "TOTAL SELECCIONADOS (CLP)", val: totalCLP ? fmtCLP(totalCLP) : "—" },
          { label: "PROVEEDORES DISTINTOS", val: new Set(definitivos.map(it => it.definitivo?.proveedor)).size || "—" },
        ].map((s, i) => (
          <div key={i} style={{ background: "var(--bg-surface)", borderRight: i < 2 ? "1px solid var(--border-default)" : "none", padding: "16px 20px" }}>
            <div style={{ fontSize: 9, fontWeight: 700, color: "var(--text-muted)", letterSpacing: "0.06em", marginBottom: 8 }}>{s.label}</div>
            <div style={{ fontSize: 24, fontWeight: 700, color: s.color ?? "var(--text-primary)", letterSpacing: "-0.02em" }}>{s.val}</div>
          </div>
        ))}
      </div>

      {/* Banner de estado de aprobación */}
      {lista.aprobacion && (
        <div style={{
          border: `1px solid ${lista.aprobacion.estado === "aprobado" ? "var(--palette-green-500)" : lista.aprobacion.estado === "rechazado" ? "var(--border-accent)" : "var(--border-default)"}`,
          background: lista.aprobacion.estado === "aprobado" ? "var(--fill-success)" : lista.aprobacion.estado === "rechazado" ? "var(--fill-error)" : "var(--bg-surface)",
          padding: "14px 18px", marginBottom: 20,
        }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12 }}>
            <div>
              <span className="label" style={{
                fontWeight: 800,
                color: lista.aprobacion.estado === "aprobado" ? "var(--text-success)" : lista.aprobacion.estado === "rechazado" ? "var(--text-error)" : "var(--text-primary)",
              }}>
                {lista.aprobacion.estado === "aprobado" ? "AUTORIZADO" : lista.aprobacion.estado === "rechazado" ? "RECHAZADA" : "ESPERANDO AUTORIZACIÓN"}
              </span>
              {lista.aprobacion.aprobador_email && (
                <span className="label" style={{ color: "var(--text-muted)", marginLeft: 8 }}>
                  — {lista.aprobacion.aprobador_email}
                </span>
              )}
            </div>
            {lista.aprobacion.estado === "rechazado" && (
              <button onClick={reiniciarAprobacion} className="label" style={{
                color: "var(--accent)", background: "none", cursor: "pointer",
                border: "1px solid var(--border-accent)", padding: "4px 12px", fontFamily: "var(--font-mono)",
              }}>
                Modificar y re-solicitar
              </button>
            )}
          </div>
          {lista.aprobacion.estado === "rechazado" && lista.aprobacion.comentario_rechazo && (
            <div style={{ marginTop: 10, padding: "10px 12px", background: "var(--bg-base)", border: "1px solid var(--border-default)", fontSize: 12, color: "var(--text-primary)", lineHeight: 1.5 }}>
              <span className="label" style={{ color: "var(--text-muted)", fontWeight: 700 }}>COMENTARIO:</span>{" "}
              {lista.aprobacion.comentario_rechazo}
            </div>
          )}
        </div>
      )}

      {/* Ítems con sus comparados */}
      {lista.items.map((it, idx) => (
        <div key={it.cotizacion_id} style={{ border: "1px solid var(--border-default)", background: "var(--bg-surface)", marginBottom: 18 }}>
          <div style={{
            display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 8,
            padding: "10px 16px", borderBottom: "1px solid var(--border-default)", background: "var(--bg-base)",
          }}>
            <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
              <span className="label" style={{ fontWeight: 800 }}>{idx + 1}. {it.nombre.toUpperCase()}</span>
              <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
                <span className="label" style={{ color: "var(--text-muted)" }}>CANT.</span>
                <input
                  type="number"
                  min={1}
                  defaultValue={it.cantidad || 1}
                  key={`${it.cotizacion_id}-${it.cantidad}`}
                  onBlur={e => actualizarCantidad(it, parseFloat(e.target.value) || 1)}
                  onKeyDown={e => { if (e.key === "Enter") (e.target as HTMLInputElement).blur(); }}
                  style={{
                    width: 58, background: "var(--bg-base)", border: "1px solid var(--border-default)",
                    padding: "3px 6px", fontSize: 11, color: "var(--text-primary)",
                    fontFamily: "var(--font-mono)", outline: "none", textAlign: "right",
                  }}
                />
              </span>
              {it.definitivo && (
                <span className="label" style={{ color: "var(--text-success)", border: "1px solid var(--palette-green-500)", background: "var(--fill-success)", padding: "2px 8px" }}>
                  ✓ DEFINITIVO: {it.definitivo.proveedor}
                  {it.definitivo.precio_clp != null && (it.cantidad || 1) > 1 &&
                    ` · ${it.cantidad} × ${fmtCLP(it.definitivo.precio_clp)} = ${fmtCLP(it.definitivo.precio_clp * it.cantidad)}`}
                </span>
              )}
            </div>
            <Link href={`/cotizar/${it.cotizacion_id}/resultados?lista=${lista.id}`}
              className="label" style={{ color: "var(--accent)", textDecoration: "none" }}>
              {it.comparado ? "Cambiar selección →" : "Buscar proveedores →"}
            </Link>
          </div>

          {it.comparados.length === 0 ? (
            <div style={{ padding: "22px 16px", fontSize: 11, color: "var(--text-muted)", textAlign: "center" }}>
              Aún sin proveedores comparados para este ítem.
            </div>
          ) : (
            <div>
              <div style={{
                display: "grid", gridTemplateColumns: "1.4fr 110px 100px 120px 90px 110px",
                padding: "7px 16px", borderBottom: "1px solid var(--border-subtle)",
              }}>
                {["PROVEEDOR / PÁGINA", "PRECIO", "ENTREGA", "UBICACIÓN", "ORIGEN", ""].map((h, hi) => (
                  <div key={hi} style={{ fontSize: 9, fontWeight: 700, color: "var(--text-muted)", letterSpacing: "0.06em" }}>{h}</div>
                ))}
              </div>
              {it.comparados.map((c, ci) => {
                const esDef = it.definitivo?.resultado_id === c.resultado_id;
                const precio = c.precio_cotizado ?? c.precio;
                const moneda = c.precio_cotizado != null ? "CLP" : c.moneda;
                return (
                  <div key={c.resultado_id} style={{
                    display: "grid", gridTemplateColumns: "1.4fr 110px 100px 120px 90px 110px",
                    padding: "10px 16px", alignItems: "center",
                    borderBottom: ci < it.comparados.length - 1 ? "1px solid var(--border-subtle)" : "none",
                    background: esDef ? "var(--fill-success)" : undefined,
                  }}>
                    <div style={{ paddingRight: 10 }}>
                      {c.url ? (
                        <a href={c.url} target="_blank" rel="noopener noreferrer"
                          style={{ fontSize: 11, fontWeight: 700, color: "var(--text-primary)", textDecoration: "none" }}>
                          {c.proveedor} ↗
                        </a>
                      ) : (
                        <span style={{ fontSize: 11, fontWeight: 700 }}>{c.proveedor}</span>
                      )}
                      <div className="label" style={{ color: "var(--accent)" }}>
                        {FUENTE_LABEL[c.fuente ?? ""] ?? c.fuente ?? "—"}
                      </div>
                    </div>
                    <div style={{ fontSize: 11, fontWeight: 700 }}>
                      {precio != null ? fmtPrecio(precio, moneda) : "—"}
                      {precio != null && moneda !== "CLP" && (
                        <div className="label" style={{ color: "var(--text-muted)", fontWeight: 400 }}>≈ {fmtCLP(aCLP(precio, moneda))}</div>
                      )}
                    </div>
                    <div style={{ fontSize: 10, color: "var(--text-secondary)" }}>{c.plazo_entrega ?? "—"}</div>
                    <div style={{ fontSize: 10, color: "var(--text-secondary)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{c.ubicacion ?? "—"}</div>
                    <div className="label" style={{ color: "var(--text-muted)" }}>{c.contacto ? "email" : "vía web"}</div>
                    <div style={{ textAlign: "right" }}>
                      {esDef ? (
                        <button
                          onClick={() => quitarDefinitivo(it)}
                          disabled={guardandoDef === it.cotizacion_id}
                          className="label"
                          style={{
                            color: "var(--text-success)", background: "none", cursor: "pointer",
                            border: "1px solid var(--text-success)", padding: "4px 10px", fontFamily: "var(--font-mono)",
                          }}
                        >
                          ✓ ELEGIDO
                        </button>
                      ) : (
                        <button
                          onClick={() => elegirDefinitivo(it, c)}
                          disabled={guardandoDef === it.cotizacion_id || precio == null}
                          className="label"
                          style={{
                            color: precio == null ? "var(--text-muted)" : "var(--accent)",
                            background: "none", cursor: precio == null ? "default" : "pointer",
                            border: `1px solid ${precio == null ? "var(--border-default)" : "var(--border-accent)"}`,
                            padding: "4px 10px", fontFamily: "var(--font-mono)",
                          }}
                        >
                          Definitivo
                        </button>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      ))}

      {/* Ruta de compra final */}
      {definitivos.length > 0 && (
        <div style={{ border: "1px solid var(--border-strong)", marginBottom: 40 }}>
          <div style={{ background: "var(--bg-inverse)", padding: "10px 16px", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <span className="label" style={{ color: "var(--text-inverse)", fontWeight: 800 }}>
              RUTA DE COMPRA FINAL {completa ? "" : `(${definitivos.length}/${lista.items.length} ítems definidos)`}
            </span>
            <span className="label" style={{ color: "var(--text-inverse)", fontWeight: 800 }}>
              TOTAL: {fmtCLP(totalCLP)}
            </span>
          </div>
          {definitivos.map((it, i) => {
            const d = it.definitivo!;
            const cant = it.cantidad || 1;
            return (
              <div key={it.cotizacion_id} style={{
                display: "grid", gridTemplateColumns: "1fr 1fr 160px",
                padding: "11px 16px", alignItems: "center", background: "var(--bg-surface)",
                borderBottom: i < definitivos.length - 1 ? "1px solid var(--border-subtle)" : "none",
              }}>
                <div style={{ fontSize: 11, fontWeight: 700 }}>
                  {it.nombre}
                  <span className="label" style={{ color: "var(--text-muted)", fontWeight: 400, marginLeft: 6 }}>× {cant}</span>
                </div>
                <div>
                  {d.url ? (
                    <a href={d.url} target="_blank" rel="noopener noreferrer" style={{ fontSize: 11, color: "var(--accent)", textDecoration: "none" }}>
                      {d.proveedor} — comprar aquí ↗
                    </a>
                  ) : (
                    <span style={{ fontSize: 11 }}>{d.proveedor}</span>
                  )}
                  <div className="label" style={{ color: "var(--text-muted)" }}>{FUENTE_LABEL[d.fuente ?? ""] ?? d.fuente ?? ""}</div>
                </div>
                <div style={{ textAlign: "right" }}>
                  <div style={{ fontSize: 12, fontWeight: 700 }}>
                    {d.precio_clp != null ? fmtCLP(d.precio_clp * cant) : d.precio != null ? fmtPrecio(d.precio * cant, d.moneda) : "—"}
                  </div>
                  {cant > 1 && d.precio_clp != null && (
                    <div className="label" style={{ color: "var(--text-muted)" }}>{cant} × {fmtCLP(d.precio_clp)}</div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Acciones de aprobación */}
      {definitivos.length > 0 && !lista.aprobacion && (
        <div style={{ display: "flex", gap: 10, marginBottom: 12 }}>
          <button onClick={() => setMostrarAprobacion(true)} className="btn-swiss-primary">
            Solicitar autorización
          </button>
          {!completa && lista.items.some(it => !it.definitivo && it.comparados.some(c => (c.precio_cotizado ?? c.precio) != null)) && (
            <button onClick={autoSeleccionarBaratos} className="btn-swiss-secondary">
              Auto: usar más baratos
            </button>
          )}
        </div>
      )}

      {/* Panel de solicitud de aprobación */}
      {mostrarAprobacion && !lista.aprobacion && (
        <div style={{ border: "1px solid var(--border-accent)", background: "var(--bg-surface)", padding: 20, marginBottom: 30 }}>
          <div className="label" style={{ fontWeight: 800, color: "var(--accent)", marginBottom: 16, letterSpacing: "0.06em" }}>
            SOLICITAR AUTORIZACIÓN
          </div>

          <div style={{ marginBottom: 16 }}>
            <div className="label" style={{ color: "var(--text-muted)", marginBottom: 6 }}>EMAIL DEL AUTORIZADOR</div>
            <input
              value={aprobadorEmail}
              onChange={e => setAprobadorEmail(e.target.value)}
              placeholder="jefe@empresa.cl"
              type="email"
              style={{
                width: "100%", background: "var(--bg-base)", border: "1px solid var(--border-default)",
                padding: "8px 12px", fontSize: 12, color: "var(--text-primary)",
                fontFamily: "var(--font-mono)", outline: "none", boxSizing: "border-box",
              }}
            />
          </div>

          <div className="label" style={{ color: "var(--text-muted)", marginBottom: 10 }}>
            JUSTIFICACIÓN POR ÍTEM (opcional)
          </div>
          {definitivos.map(it => (
            <div key={it.cotizacion_id} style={{ marginBottom: 10 }}>
              <div style={{ fontSize: 11, fontWeight: 700, color: "var(--text-primary)", marginBottom: 4 }}>
                {it.nombre} — {it.definitivo?.proveedor}
                {it.definitivo?.precio_clp != null && (
                  <span className="label" style={{ color: "var(--text-muted)", fontWeight: 400, marginLeft: 6 }}>
                    {fmtCLP(it.definitivo.precio_clp * (it.cantidad || 1))}
                  </span>
                )}
              </div>
              <input
                value={justificaciones[it.cotizacion_id] ?? ""}
                onChange={e => setJustificaciones(j => ({ ...j, [it.cotizacion_id]: e.target.value }))}
                placeholder="Ej: mejor precio, entrega rápida, proveedor conocido…"
                style={{
                  width: "100%", background: "var(--bg-base)", border: "1px solid var(--border-default)",
                  padding: "6px 10px", fontSize: 11, color: "var(--text-primary)",
                  fontFamily: "var(--font-mono)", outline: "none", boxSizing: "border-box",
                }}
              />
            </div>
          ))}

          <div style={{ display: "flex", gap: 10, marginTop: 16 }}>
            <button
              onClick={solicitarAprobacion}
              disabled={solicitando || !aprobadorEmail.trim()}
              className="btn-swiss-primary"
            >
              {solicitando ? "Enviando…" : "Enviar solicitud por correo"}
            </button>
            <button onClick={() => setMostrarAprobacion(false)} className="btn-swiss-secondary">
              Cancelar
            </button>
          </div>
        </div>
      )}
    </>
  );
}
