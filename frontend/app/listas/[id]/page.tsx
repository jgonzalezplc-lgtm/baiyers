"use client";
import { useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import dynamic from "next/dynamic";
import { ArrowLeft, Check, Send, Wand2 } from "lucide-react";
import { createClient } from "@/lib/supabase/client";
import { Card, Badge, BtnPrimary, BtnSecondary, SummaryPanel, Input, Spinner } from "@/components/ui";

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
        `- ${it.nombre} ×${it.cantidad || 1}: ${it.definitivo!.proveedor} (${it.definitivo!.precio_clp != null ? fmtCLP(it.definitivo!.precio_clp * (it.cantidad || 1)) : "—"})${justificaciones[it.cotizacion_id] ? `, ${justificaciones[it.cotizacion_id]}` : ""}`
      ).join("\n");

      const subject = encodeURIComponent(`Solicitud de aprobación: ${lista.nombre}`);
      const body = encodeURIComponent(
        `Hola,\n\n${userMeta.nombre_usuario ?? "Un usuario"} de ${userMeta.empresa ?? "la empresa"} solicita tu aprobación para la siguiente lista de compra:\n\n` +
        `Lista: ${lista.nombre}\nTotal: ${totalStr}\n\n${itemLines}\n\n` +
        `Para aprobar:\n${data.magic_link_aprobar}\n\n` +
        `Para rechazar (puedes agregar comentarios):\n${data.magic_link_rechazar}\n\n` +
        `Este enlace expira el ${new Date(data.expira_at).toLocaleDateString("es-CL")}.\n\nBaiyer, Procurement Inteligente`
      );

      window.open(`mailto:${aprobadorEmail.trim()}?subject=${subject}&body=${body}`, "_self");
      setToast("Solicitud creada, se abrió tu correo para enviar");
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
      setToast("Lista desbloqueada, puedes modificarla y re-solicitar");
      setTimeout(() => setToast(""), 3500);
      await cargar(userId);
    } catch {
      setToast("Error al reiniciar aprobación");
      setTimeout(() => setToast(""), 3000);
    }
  };

  if (loading) return <Spinner />;
  if (!lista) return <Spinner label="Lista no encontrada." />;

  const definitivos = lista.items.filter(it => it.definitivo);
  const totalCLP = definitivos.reduce((a, it) => a + (it.definitivo?.precio_clp ?? 0) * (it.cantidad || 1), 0);
  const completa = definitivos.length === lista.items.length;

  return (
    <>
      {toast && (
        <div style={{
          position: "fixed", top: 20, right: 20, zIndex: 999,
          background: "var(--n-900)", color: "var(--canvas)",
          padding: "11px 16px", fontSize: 13.5, fontWeight: 500,
          borderRadius: "var(--r-md)", boxShadow: "var(--shadow-pop)",
        }}>{toast}</div>
      )}

      {/* Header */}
      <div style={{ marginBottom: 20 }}>
        <Link href="/listas" style={{
          display: "inline-flex", alignItems: "center", gap: 6, marginBottom: 12,
          fontSize: 13, color: "var(--n-500)", textDecoration: "none",
        }}>
          <ArrowLeft size={15} strokeWidth={1.75} /> Listas de cotización
        </Link>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 16, flexWrap: "wrap" }}>
          <div>
            <h1 style={{ fontSize: 26, lineHeight: 1.2, fontWeight: 600, color: "var(--n-900)", margin: "0 0 6px", letterSpacing: "-0.015em" }}>
              {lista.nombre}
            </h1>
            <div style={{ fontSize: 13.5, color: "var(--n-600)" }}>
              {lista.items.length} ítems · {lista.items.filter(i => i.comparado).length} comparados · {definitivos.length} definitivos
            </div>
          </div>
          <InformeLista listaId={lista.id} userId={userId ?? ""} nombreLista={lista.nombre} />
        </div>
      </div>

      {/* Resumen */}
      <div style={{
        display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))",
        gap: 12, marginBottom: 20,
      }}>
        {[
          { label: "Definitivos elegidos", val: `${definitivos.length}/${lista.items.length}`, color: completa ? "var(--success)" : undefined },
          { label: "Total seleccionados", val: totalCLP ? fmtCLP(totalCLP) : "—", mono: true },
          { label: "Proveedores distintos", val: String(new Set(definitivos.map(it => it.definitivo?.proveedor)).size || "—") },
        ].map((s, i) => (
          <Card key={i} padding={16}>
            <div style={{ fontSize: 12.5, color: "var(--n-500)", marginBottom: 6 }}>{s.label}</div>
            <div style={{
              fontSize: 24, fontWeight: 600, letterSpacing: "-0.015em",
              color: s.color ?? "var(--n-900)",
              fontFamily: s.mono ? "var(--font-mono)" : undefined,
              fontVariantNumeric: s.mono ? "tabular-nums" : undefined,
            }}>{s.val}</div>
          </Card>
        ))}
      </div>

      {/* Banner de estado de aprobación */}
      {lista.aprobacion && (() => {
        const est = lista.aprobacion.estado;
        const badge = est === "aprobado" ? "aprobada" : est === "rechazado" ? "rechazada" : "cotizando";
        const texto = est === "aprobado" ? "Autorizada" : est === "rechazado" ? "Rechazada" : "Esperando autorización";
        return (
          <Card padding={16} style={{ marginBottom: 20 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <Badge status={badge}>{texto}</Badge>
                {lista.aprobacion.aprobador_email && (
                  <span style={{ fontSize: 13.5, color: "var(--n-600)" }}>{lista.aprobacion.aprobador_email}</span>
                )}
              </div>
              {est === "rechazado" && (
                <BtnSecondary onClick={reiniciarAprobacion} size="sm">
                  Modificar y volver a solicitar
                </BtnSecondary>
              )}
            </div>
            {est === "rechazado" && lista.aprobacion.comentario_rechazo && (
              <SummaryPanel style={{ marginTop: 12 }}>
                <div style={{ fontSize: 12.5, color: "var(--n-500)", marginBottom: 4 }}>Comentario del autorizador</div>
                <div style={{ fontSize: 14, color: "var(--n-900)", lineHeight: 1.6 }}>
                  {lista.aprobacion.comentario_rechazo}
                </div>
              </SummaryPanel>
            )}
          </Card>
        );
      })()}

      {/* Ítems con sus comparados */}
      {lista.items.map((it, idx) => (
        <div key={it.cotizacion_id} style={{
          border: "1px solid var(--n-200)", background: "var(--surface)",
          borderRadius: "var(--r-lg)", marginBottom: 16, overflow: "hidden",
          boxShadow: "var(--shadow-card)",
        }}>
          <div style={{
            display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 10,
            padding: "12px 16px", borderBottom: "1px solid var(--n-200)", background: "var(--canvas)",
          }}>
            <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
              <span style={{ fontSize: 15, fontWeight: 600, color: "var(--n-900)" }}>{idx + 1}. {it.nombre}</span>
              <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
                <span style={{ fontSize: 12.5, color: "var(--n-500)" }}>Cant.</span>
                <input
                  type="number"
                  min={1}
                  defaultValue={it.cantidad || 1}
                  key={`${it.cotizacion_id}-${it.cantidad}`}
                  onBlur={e => actualizarCantidad(it, parseFloat(e.target.value) || 1)}
                  onKeyDown={e => { if (e.key === "Enter") (e.target as HTMLInputElement).blur(); }}
                  style={{
                    width: 62, background: "var(--surface)", border: "1px solid var(--n-300)",
                    borderRadius: "var(--r-sm)", padding: "5px 8px", fontSize: 13,
                    color: "var(--n-900)", fontFamily: "var(--font-mono)",
                    fontVariantNumeric: "tabular-nums", outline: "none", textAlign: "right",
                  }}
                />
              </span>
              {it.definitivo && (
                <Badge status="aprobada">
                  {it.definitivo.proveedor}
                  {it.definitivo.precio_clp != null && (it.cantidad || 1) > 1 &&
                    ` · ${it.cantidad} × ${fmtCLP(it.definitivo.precio_clp)}`}
                </Badge>
              )}
            </div>
            <Link href={`/cotizar/${it.cotizacion_id}/resultados?lista=${lista.id}`}
              style={{ fontSize: 13.5, fontWeight: 500, color: "var(--brand)", textDecoration: "none" }}>
              {it.comparado ? "Cambiar selección →" : "Buscar proveedores →"}
            </Link>
          </div>

          {it.comparados.length === 0 ? (
            <div style={{ padding: "24px 16px", fontSize: 13.5, color: "var(--n-500)", textAlign: "center" }}>
              Aún sin proveedores comparados para este ítem.
            </div>
          ) : (
            <div>
              <div style={{
                display: "grid", gridTemplateColumns: "1.4fr 120px 100px 120px 90px 110px", gap: 10,
                padding: "9px 16px", borderBottom: "1px solid var(--n-200)", background: "var(--canvas)",
              }}>
                {["Proveedor / página", "Precio", "Entrega", "Ubicación", "Origen", ""].map((h, hi) => (
                  <div key={hi} style={{ fontSize: 12, fontWeight: 600, color: "var(--n-600)" }}>{h}</div>
                ))}
              </div>
              {it.comparados.map((c, ci) => {
                const esDef = it.definitivo?.resultado_id === c.resultado_id;
                const precio = c.precio_cotizado ?? c.precio;
                const moneda = c.precio_cotizado != null ? "CLP" : c.moneda;
                return (
                  <div key={c.resultado_id} style={{
                    display: "grid", gridTemplateColumns: "1.4fr 120px 100px 120px 90px 110px", gap: 10,
                    padding: "12px 16px", alignItems: "center",
                    borderBottom: ci < it.comparados.length - 1 ? "1px solid var(--n-100)" : "none",
                    background: esDef ? "var(--st-aprobada-bg)" : ci % 2 ? "var(--canvas)" : undefined,
                  }}>
                    <div style={{ paddingRight: 8, minWidth: 0 }}>
                      {c.url ? (
                        <a href={c.url} target="_blank" rel="noopener noreferrer"
                          style={{ fontSize: 14, fontWeight: 600, color: "var(--n-900)", textDecoration: "none" }}>
                          {c.proveedor} ↗
                        </a>
                      ) : (
                        <span style={{ fontSize: 14, fontWeight: 600, color: "var(--n-900)" }}>{c.proveedor}</span>
                      )}
                      <div style={{ fontSize: 12.5, color: "var(--brand)" }}>
                        {FUENTE_LABEL[c.fuente ?? ""] ?? c.fuente ?? "—"}
                      </div>
                    </div>
                    <div style={{ fontSize: 14, fontWeight: 600, fontFamily: "var(--font-mono)", fontVariantNumeric: "tabular-nums" }}>
                      {precio != null ? fmtPrecio(precio, moneda) : "—"}
                      {precio != null && moneda !== "CLP" && (
                        <div style={{ fontSize: 12, color: "var(--n-500)", fontWeight: 400 }}>≈ {fmtCLP(aCLP(precio, moneda))}</div>
                      )}
                    </div>
                    <div style={{ fontSize: 13, color: "var(--n-600)" }}>{c.plazo_entrega ?? "—"}</div>
                    <div style={{ fontSize: 13, color: "var(--n-600)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{c.ubicacion ?? "—"}</div>
                    <div style={{ fontSize: 12.5, color: "var(--n-500)" }}>{c.contacto ? "Correo" : "Vía web"}</div>
                    <div style={{ textAlign: "right" }}>
                      {esDef ? (
                        <button
                          onClick={() => quitarDefinitivo(it)}
                          disabled={guardandoDef === it.cotizacion_id}
                          style={{
                            display: "inline-flex", alignItems: "center", gap: 5,
                            color: "var(--st-aprobada-fg)", background: "transparent", cursor: "pointer",
                            border: "1px solid var(--success)", borderRadius: "var(--r-md)",
                            padding: "6px 11px", fontSize: 13, fontWeight: 600, fontFamily: "var(--font-sans)",
                          }}
                        >
                          <Check size={14} strokeWidth={2} /> Elegido
                        </button>
                      ) : (
                        <button
                          onClick={() => elegirDefinitivo(it, c)}
                          disabled={guardandoDef === it.cotizacion_id || precio == null}
                          style={{
                            color: precio == null ? "var(--n-400)" : "var(--brand)",
                            background: "transparent", cursor: precio == null ? "not-allowed" : "pointer",
                            border: `1px solid ${precio == null ? "var(--n-200)" : "var(--n-300)"}`,
                            borderRadius: "var(--r-md)", padding: "6px 11px",
                            fontSize: 13, fontWeight: 600, fontFamily: "var(--font-sans)",
                          }}
                        >
                          Elegir
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
        <div style={{
          border: "1px solid var(--n-200)", borderRadius: "var(--r-lg)",
          overflow: "hidden", marginBottom: 24, boxShadow: "var(--shadow-card)",
        }}>
          <div style={{
            background: "var(--surface-2)", padding: "12px 16px",
            display: "flex", justifyContent: "space-between", alignItems: "center",
            gap: 10, flexWrap: "wrap", borderBottom: "1px solid var(--n-200)",
          }}>
            <span style={{ fontSize: 15, fontWeight: 600, color: "var(--n-900)" }}>
              Ruta de compra final
              {!completa && (
                <span style={{ fontWeight: 400, color: "var(--n-600)" }}>
                  {" "}({definitivos.length}/{lista.items.length} ítems definidos)
                </span>
              )}
            </span>
            <span style={{ fontSize: 16, fontWeight: 600, color: "var(--n-900)", fontFamily: "var(--font-mono)", fontVariantNumeric: "tabular-nums" }}>
              Total: {fmtCLP(totalCLP)}
            </span>
          </div>
          {definitivos.map((it, i) => {
            const d = it.definitivo!;
            const cant = it.cantidad || 1;
            return (
              <div key={it.cotizacion_id} style={{
                display: "grid", gridTemplateColumns: "1fr 1fr 160px", gap: 12,
                padding: "12px 16px", alignItems: "center", background: "var(--surface)",
                borderBottom: i < definitivos.length - 1 ? "1px solid var(--n-100)" : "none",
              }}>
                <div style={{ fontSize: 14, fontWeight: 600, color: "var(--n-900)" }}>
                  {it.nombre}
                  <span style={{ color: "var(--n-500)", fontWeight: 400, marginLeft: 6 }}>× {cant}</span>
                </div>
                <div style={{ minWidth: 0 }}>
                  {d.url ? (
                    <a href={d.url} target="_blank" rel="noopener noreferrer" style={{ fontSize: 14, color: "var(--brand)", textDecoration: "none", fontWeight: 500 }}>
                      {d.proveedor}, comprar aquí ↗
                    </a>
                  ) : (
                    <span style={{ fontSize: 14 }}>{d.proveedor}</span>
                  )}
                  <div style={{ fontSize: 12.5, color: "var(--n-500)" }}>{FUENTE_LABEL[d.fuente ?? ""] ?? d.fuente ?? ""}</div>
                </div>
                <div style={{ textAlign: "right" }}>
                  <div style={{ fontSize: 15, fontWeight: 600, fontFamily: "var(--font-mono)", fontVariantNumeric: "tabular-nums" }}>
                    {d.precio_clp != null ? fmtCLP(d.precio_clp * cant) : d.precio != null ? fmtPrecio(d.precio * cant, d.moneda) : "—"}
                  </div>
                  {cant > 1 && d.precio_clp != null && (
                    <div style={{ fontSize: 12, color: "var(--n-500)" }}>{cant} × {fmtCLP(d.precio_clp)}</div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Acciones de aprobación */}
      {definitivos.length > 0 && !lista.aprobacion && (
        <div style={{ display: "flex", gap: 10, marginBottom: 16, flexWrap: "wrap" }}>
          <BtnPrimary onClick={() => setMostrarAprobacion(true)} icon={Send}>
            Solicitar autorización
          </BtnPrimary>
          {!completa && lista.items.some(it => !it.definitivo && it.comparados.some(c => (c.precio_cotizado ?? c.precio) != null)) && (
            <BtnSecondary onClick={autoSeleccionarBaratos} icon={Wand2}>
              Usar los más baratos
            </BtnSecondary>
          )}
        </div>
      )}

      {/* Panel de solicitud de aprobación */}
      {mostrarAprobacion && !lista.aprobacion && (
        <Card padding={20} style={{ marginBottom: 30, borderColor: "var(--brand-200)" }}>
          <h2 style={{ fontSize: 20, fontWeight: 600, color: "var(--n-900)", margin: "0 0 4px" }}>
            Solicitar autorización
          </h2>
          <p style={{ fontSize: 13.5, color: "var(--n-600)", margin: "0 0 18px", lineHeight: 1.6 }}>
            Le enviaremos un correo con el detalle y un enlace para aprobar o rechazar.
          </p>

          <div style={{ marginBottom: 18 }}>
            <Input
              label="Email del autorizador"
              value={aprobadorEmail}
              onChange={e => setAprobadorEmail(e.target.value)}
              placeholder="jefe@empresa.cl"
              type="email"
            />
          </div>

          <div style={{ fontSize: 13, fontWeight: 500, color: "var(--n-700)", marginBottom: 10 }}>
            Justificación por ítem <span style={{ color: "var(--n-500)", fontWeight: 400 }}>(opcional)</span>
          </div>
          {definitivos.map(it => (
            <div key={it.cotizacion_id} style={{ marginBottom: 12 }}>
              <div style={{ fontSize: 14, fontWeight: 600, color: "var(--n-900)", marginBottom: 5 }}>
                {it.nombre}, {it.definitivo?.proveedor}
                {it.definitivo?.precio_clp != null && (
                  <span style={{
                    color: "var(--n-500)", fontWeight: 400, marginLeft: 6,
                    fontFamily: "var(--font-mono)", fontVariantNumeric: "tabular-nums",
                  }}>
                    {fmtCLP(it.definitivo.precio_clp * (it.cantidad || 1))}
                  </span>
                )}
              </div>
              <input
                value={justificaciones[it.cotizacion_id] ?? ""}
                onChange={e => setJustificaciones(j => ({ ...j, [it.cotizacion_id]: e.target.value }))}
                placeholder="Ej: mejor precio, entrega rápida, proveedor conocido…"
                style={{
                  width: "100%", height: 38, background: "var(--surface)",
                  border: "1px solid var(--n-300)", borderRadius: "var(--r-md)",
                  padding: "0 12px", fontSize: 14, color: "var(--n-900)",
                  fontFamily: "var(--font-sans)", outline: "none", boxSizing: "border-box",
                }}
              />
            </div>
          ))}

          <div style={{ display: "flex", gap: 10, marginTop: 18 }}>
            <BtnPrimary
              onClick={solicitarAprobacion}
              disabled={solicitando || !aprobadorEmail.trim()}
              icon={Send}
            >
              {solicitando ? "Enviando…" : "Enviar solicitud por correo"}
            </BtnPrimary>
            <BtnSecondary onClick={() => setMostrarAprobacion(false)}>
              Cancelar
            </BtnSecondary>
          </div>
        </Card>
      )}
    </>
  );
}
