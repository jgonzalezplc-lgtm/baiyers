"use client";
import { useState, useEffect } from "react";
import { createClient } from "@/lib/supabase/client";
import Link from "next/link";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface Cotizacion {
  id: string;
  nombre_identificado: string;
  marca: string | null;
  categoria: string | null;
  estado: string;
  confianza_ia: string | null;
  created_at: string;
  n_encontrados: number;
  n_enviados: number;
  n_respondieron: number;
  precio_min: number | null;
  total_oc: number | null;
}

const ESTADO_CONFIG: Record<string, { label: string; color: string }> = {
  identificado: { label: "IDENTIFICADO", color: "#2980b9" },
  cotizando:    { label: "COTIZANDO",    color: "#f39c12" },
  oc_emitida:   { label: "OC EMITIDA",   color: "var(--text-success)" },
  pendiente:    { label: "PENDIENTE",    color: "var(--text-muted)" },
  cancelado:    { label: "CANCELADO",    color: "var(--text-error)" },
};

const CONFIANZA_COLORS: Record<string, string> = {
  alto: "var(--text-success)",
  medio: "#92400e",
  bajo: "var(--text-error)",
};

type Orden = "fecha" | "precio" | "respondieron";

function fmtFecha(iso: string) {
  const d = new Date(iso);
  return `${d.getDate()} ${["Ene","Feb","Mar","Abr","May","Jun","Jul","Ago","Sep","Oct","Nov","Dic"][d.getMonth()]}`;
}

export default function CotizacionesPage() {
  const [cotizaciones, setCotizaciones] = useState<Cotizacion[]>([]);
  const [loading, setLoading] = useState(true);
  const [userId, setUserId] = useState<string | null>(null);
  const [busqueda, setBusqueda] = useState("");
  const [filtroCategoria, setFiltroCategoria] = useState("todas");
  const [orden, setOrden] = useState<Orden>("fecha");

  useEffect(() => {
    createClient().auth.getUser().then(({ data }) => {
      if (data.user) { setUserId(data.user.id); cargar(data.user.id); }
    });
  }, []);

  const cargar = async (uid: string) => {
    setLoading(true);
    try {
      const res = await fetch(`${API_URL}/api/cotizaciones?user_id=${uid}&limit=100`);
      if (res.ok) setCotizaciones(await res.json());
    } catch { /* silent */ } finally { setLoading(false); }
  };

  const categorias = ["todas", ...Array.from(new Set(cotizaciones.map(c => c.categoria).filter(Boolean) as string[]))];

  const filtradas = cotizaciones.filter(c => {
    if (busqueda && !c.nombre_identificado.toLowerCase().includes(busqueda.toLowerCase())) return false;
    if (filtroCategoria !== "todas" && c.categoria !== filtroCategoria) return false;
    return true;
  });

  const ordenadas = [...filtradas].sort((a, b) => {
    if (orden === "precio") return (a.precio_min ?? Infinity) - (b.precio_min ?? Infinity);
    if (orden === "respondieron") return (b.n_respondieron ?? 0) - (a.n_respondieron ?? 0);
    return new Date(b.created_at).getTime() - new Date(a.created_at).getTime();
  });

  // Stats resumen
  const totalEnviados = cotizaciones.reduce((s, c) => s + (c.n_enviados || 0), 0);
  const totalRespondieron = cotizaciones.reduce((s, c) => s + (c.n_respondieron || 0), 0);

  return (
    <>
      <div style={{ marginBottom: 24 }}>
        <div className="section-rule" style={{ marginBottom: 16 }} />
        <span style={{ fontSize: 10, fontWeight: 700, color: "var(--text-muted)", letterSpacing: "0.06em", display: "block", marginBottom: 6 }}>
          SEGUIMIENTO
        </span>
        <h1 style={{ fontSize: 26, fontWeight: 700, color: "var(--text-primary)", margin: "0 0 6px", letterSpacing: "-0.02em" }}>
          Cotizaciones
        </h1>
        <p style={{ fontSize: 12, color: "var(--text-secondary)", margin: 0 }}>
          {cotizaciones.length > 0
            ? `${cotizaciones.length} cotizaciones · ${totalEnviados} correos enviados · ${totalRespondieron} respondidos`
            : "Tu historial de cotizaciones."}
        </p>
      </div>

      {/* Filtros y orden */}
      <div style={{ display: "flex", gap: 8, marginBottom: 20, alignItems: "center", flexWrap: "wrap" }}>
        <input
          type="text" placeholder="Buscar..." value={busqueda}
          onChange={e => setBusqueda(e.target.value)}
          style={{
            fontSize: 12, padding: "7px 12px", border: "1px solid var(--border-default)",
            background: "var(--bg-surface)", color: "var(--text-primary)",
            fontFamily: "var(--font-mono)", outline: "none", width: 190,
          }}
        />
        <select value={filtroCategoria} onChange={e => setFiltroCategoria(e.target.value)}
          style={{ fontSize: 12, padding: "7px 12px", border: "1px solid var(--border-default)", background: "var(--bg-surface)", color: "var(--text-primary)", fontFamily: "var(--font-mono)", cursor: "pointer" }}>
          {categorias.map(c => <option key={c} value={c}>{c === "todas" ? "Categorías" : c}</option>)}
        </select>

        <div style={{ display: "flex", gap: 0, border: "1px solid var(--border-default)" }}>
          {([["fecha", "FECHA"], ["precio", "PRECIO ↑"], ["respondieron", "RESPONDIÓ"]] as const).map(([val, lbl]) => (
            <button key={val} onClick={() => setOrden(val)} style={{
              fontSize: 9, fontWeight: 700, padding: "6px 11px", cursor: "pointer",
              background: orden === val ? "var(--bg-inverse)" : "var(--bg-surface)",
              color: orden === val ? "var(--text-inverse)" : "var(--text-muted)",
              border: "none", borderRight: val !== "respondieron" ? "1px solid var(--border-default)" : "none",
              fontFamily: "var(--font-mono)", letterSpacing: "0.04em",
            }}>{lbl}</button>
          ))}
        </div>

        <Link href="/cotizar" style={{
          marginLeft: "auto", fontSize: 11, fontWeight: 700, letterSpacing: "0.04em",
          background: "var(--bg-inverse)", color: "var(--text-inverse)",
          border: "1px solid var(--border-strong)", padding: "7px 16px", textDecoration: "none",
        }}>+ NUEVA</Link>
      </div>

      {/* Tabla */}
      <div style={{ border: "1px solid var(--border-default)", background: "var(--bg-surface)" }}>
        {/* Cabecera */}
        <div style={{
          display: "grid",
          gridTemplateColumns: "72px 1fr 100px 90px 110px 110px 100px 68px",
          padding: "9px 16px",
          borderBottom: "1px solid var(--border-default)",
          background: "var(--bg-base)",
        }}>
          {["ID", "ITEM", "CATEGORÍA", "CONFIANZA", "CORREOS ENV.", "RESPONDIERON", "PRECIO MIN", "FECHA"].map(h => (
            <div key={h} style={{ fontSize: 9, fontWeight: 700, color: "var(--text-muted)", letterSpacing: "0.06em" }}>{h}</div>
          ))}
        </div>

        {loading ? (
          <div style={{ padding: "40px 0", textAlign: "center", fontSize: 12, color: "var(--text-muted)" }}>Cargando...</div>
        ) : ordenadas.length === 0 ? (
          <div style={{ padding: "40px 0", textAlign: "center" }}>
            <div style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 12 }}>
              {busqueda || filtroCategoria !== "todas" ? "Sin resultados para esos filtros." : "Aún no hay cotizaciones."}
            </div>
            <Link href="/cotizar" style={{ fontSize: 11, color: "var(--accent)" }}>Crear primera cotización →</Link>
          </div>
        ) : ordenadas.map((c, i) => {
          const conf = c.confianza_ia?.toLowerCase();
          const est = ESTADO_CONFIG[c.estado] ?? { label: c.estado.toUpperCase(), color: "var(--text-muted)" };
          const tieneRespuestas = c.n_respondieron > 0;
          const tieneEnviados = c.n_enviados > 0;

          return (
            <Link key={c.id} href={`/cotizaciones/${c.id}`}
              style={{
                display: "grid",
                gridTemplateColumns: "72px 1fr 100px 90px 110px 110px 100px 68px",
                padding: "11px 16px",
                borderBottom: i < ordenadas.length - 1 ? "1px solid var(--border-subtle)" : "none",
                alignItems: "center",
                textDecoration: "none", color: "inherit",
                background: tieneRespuestas ? "var(--fill-success)" : undefined,
              }}>
              <div style={{ fontSize: 9, color: "var(--text-muted)", fontFamily: "var(--font-mono)" }}>
                COT-{c.id.slice(-4).toUpperCase()}
              </div>
              <div>
                <div style={{ fontSize: 12, fontWeight: 700, color: "var(--text-primary)", marginBottom: 1 }}>{c.nombre_identificado}</div>
                {c.marca && <div style={{ fontSize: 9, color: "var(--text-muted)" }}>{c.marca}</div>}
              </div>
              <div style={{ fontSize: 11, color: "var(--text-secondary)" }}>{c.categoria || "—"}</div>
              <div>
                {conf ? (
                  <span style={{ fontSize: 9, fontWeight: 700, color: CONFIANZA_COLORS[conf] ?? "var(--text-muted)", border: `1px solid ${CONFIANZA_COLORS[conf] ?? "var(--border-default)"}`, padding: "2px 6px" }}>
                    {conf.toUpperCase()}
                  </span>
                ) : <span style={{ fontSize: 11, color: "var(--text-muted)" }}>—</span>}
              </div>
              {/* Correos enviados */}
              <div>
                {tieneEnviados ? (
                  <span style={{ fontSize: 10, fontWeight: 700, color: "#2980b9", border: "1px solid #2980b9", padding: "2px 8px" }}>
                    {c.n_enviados} enviado{c.n_enviados !== 1 ? "s" : ""}
                  </span>
                ) : (
                  <span style={{ fontSize: 10, color: "var(--text-muted)" }}>
                    {c.n_encontrados > 0 ? `${c.n_encontrados} encontr.` : "—"}
                  </span>
                )}
              </div>
              {/* Respondieron */}
              <div>
                {tieneRespuestas ? (
                  <span style={{ fontSize: 10, fontWeight: 700, color: "var(--text-success)", border: "1px solid var(--text-success)", padding: "2px 8px" }}>
                    {c.n_respondieron} respondió
                  </span>
                ) : tieneEnviados ? (
                  <span style={{ fontSize: 10, color: "var(--text-muted)" }}>Esperando</span>
                ) : (
                  <span style={{ fontSize: 10, color: "var(--text-muted)" }}>—</span>
                )}
              </div>
              {/* Precio mínimo */}
              <div style={{ fontSize: 11, fontWeight: 700, color: "var(--text-primary)" }}>
                {c.precio_min != null ? `$${Math.round(c.precio_min).toLocaleString("es-CL")}` : "—"}
              </div>
              <div style={{ fontSize: 10, color: "var(--text-muted)" }}>{fmtFecha(c.created_at)}</div>
            </Link>
          );
        })}
      </div>

      {/* Leyenda */}
      {ordenadas.length > 0 && (
        <div style={{ marginTop: 12, display: "flex", gap: 16, fontSize: 9, color: "var(--text-muted)", fontFamily: "var(--font-mono)" }}>
          <span style={{ background: "var(--fill-success)", padding: "2px 8px" }}>VERDE = tiene respuesta de proveedor</span>
          <span>Click en una fila para ver el detalle y comparar precios</span>
        </div>
      )}
    </>
  );
}
