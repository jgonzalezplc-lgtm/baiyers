"use client";
import { useState, useEffect } from "react";
import { createClient } from "@/lib/supabase/client";
import Link from "next/link";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface OC {
  id: string;
  numero_oc: string;
  cotizacion_id: string;
  item: string;
  proveedor_nombre: string;
  condiciones_pago: string | null;
  total: number;
  moneda: string;
  estado: string;
  created_at: string;
}

const ESTADO_CONFIG: Record<string, { label: string; color: string }> = {
  borrador:   { label: "BORRADOR",   color: "var(--text-muted)" },
  enviada:    { label: "ENVIADA",    color: "#2980b9" },
  confirmada: { label: "CONFIRMADA", color: "var(--text-success)" },
  rechazada:  { label: "RECHAZADA", color: "var(--text-error)" },
  pendiente:  { label: "PENDIENTE",  color: "var(--text-warning)" },
  pagada:     { label: "PAGADA",     color: "var(--text-success)" },
};

function fmt(n: number) {
  return `$${Math.round(n).toLocaleString("es-CL")}`;
}

function fmtFecha(iso: string) {
  const d = new Date(iso);
  return `${d.getDate()} ${["Ene","Feb","Mar","Abr","May","Jun","Jul","Ago","Sep","Oct","Nov","Dic"][d.getMonth()]}`;
}

export default function OCPage() {
  const [ocs, setOcs] = useState<OC[]>([]);
  const [loading, setLoading] = useState(true);
  const [userId, setUserId] = useState<string | null>(null);
  const [filtroEstado, setFiltroEstado] = useState("todas");

  useEffect(() => {
    createClient().auth.getUser().then(({ data }) => {
      if (data.user) { setUserId(data.user.id); cargar(data.user.id); }
    });
  }, []);

  const cargar = async (uid: string) => {
    setLoading(true);
    try {
      const res = await fetch(`${API_URL}/api/oc?user_id=${uid}`);
      if (res.ok) setOcs(await res.json());
    } catch { /* silent */ } finally { setLoading(false); }
  };

  const filtradas = filtroEstado === "todas" ? ocs : ocs.filter(o => o.estado === filtroEstado);
  const totalMes = ocs.filter(o => o.estado === "confirmada" || o.estado === "pagada").reduce((s, o) => s + o.total, 0);

  return (
    <>
      {/* Header */}
      <div style={{ marginBottom: 28 }}>
        <div className="section-rule" style={{ marginBottom: 16 }} />
        <span style={{ fontSize: 10, fontWeight: 700, color: "var(--text-muted)", letterSpacing: "0.06em", display: "block", marginBottom: 6 }}>
          DOCUMENTOS
        </span>
        <h1 style={{ fontSize: 26, fontWeight: 700, color: "var(--text-primary)", margin: "0 0 6px", letterSpacing: "-0.02em" }}>
          OC Emitidas
        </h1>
        <p style={{ fontSize: 12, color: "var(--text-secondary)", margin: 0 }}>
          {ocs.length > 0 ? `${ocs.length} órdenes de compra emitidas este mes.` : "Órdenes de compra generadas."}
        </p>
      </div>

      {/* Filtros */}
      <div style={{ display: "flex", gap: 8, marginBottom: 20, flexWrap: "wrap" }}>
        {["todas", "enviada", "confirmada", "pendiente", "rechazada", "pagada"].map(e => (
          <button key={e} onClick={() => setFiltroEstado(e)} style={{
            fontSize: 10,
            fontWeight: 700,
            letterSpacing: "0.05em",
            padding: "5px 12px",
            border: "1px solid var(--border-default)",
            background: filtroEstado === e ? "var(--accent)" : "var(--bg-surface)",
            color: filtroEstado === e ? "#fff" : "var(--text-muted)",
            cursor: "pointer",
            fontFamily: "var(--font-mono)",
            textTransform: "uppercase",
          }}>
            {e}
          </button>
        ))}
        {totalMes > 0 && (
          <span style={{ marginLeft: "auto", fontSize: 12, fontWeight: 700, color: "var(--text-primary)", alignSelf: "center" }}>
            Total confirmadas: {fmt(totalMes)} CLP
          </span>
        )}
      </div>

      {/* Tabla */}
      <div style={{ border: "1px solid var(--border-default)", background: "var(--bg-surface)" }}>
        {/* Header */}
        <div style={{
          display: "grid",
          gridTemplateColumns: "110px 1fr 150px 110px 100px 110px 70px",
          padding: "10px 16px",
          borderBottom: "1px solid var(--border-default)",
        }}>
          {["N° OC", "ITEM", "PROVEEDOR", "CONDICIONES", "TOTAL", "ESTADO", "FECHA"].map(h => (
            <div key={h} style={{ fontSize: 9, fontWeight: 700, color: "var(--text-muted)", letterSpacing: "0.06em" }}>{h}</div>
          ))}
        </div>

        {loading ? (
          <div style={{ padding: "40px 16px", textAlign: "center", fontSize: 12, color: "var(--text-muted)" }}>
            Cargando...
          </div>
        ) : filtradas.length === 0 ? (
          <div style={{ padding: "40px 16px", textAlign: "center" }}>
            <div style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 12 }}>
              {filtroEstado === "todas" ? "Aún no hay órdenes de compra." : `No hay OCs con estado "${filtroEstado}".`}
            </div>
            {filtroEstado === "todas" && (
              <Link href="/cotizar" style={{ fontSize: 11, color: "var(--accent)" }}>
                Crear primera cotización →
              </Link>
            )}
          </div>
        ) : (
          filtradas.map((oc, i) => {
            const est = ESTADO_CONFIG[oc.estado] ?? { label: oc.estado.toUpperCase(), color: "var(--text-muted)" };
            return (
              <div key={oc.id} style={{
                display: "grid",
                gridTemplateColumns: "110px 1fr 150px 110px 100px 110px 70px",
                padding: "12px 16px",
                borderBottom: i < filtradas.length - 1 ? "1px solid var(--border-subtle)" : "none",
                alignItems: "center",
              }}>
                <div style={{ fontSize: 11, fontWeight: 700, color: "var(--text-primary)" }}>{oc.numero_oc}</div>
                <div style={{ fontSize: 12, fontWeight: 700, color: "var(--text-primary)" }}>{oc.item}</div>
                <div style={{ fontSize: 11, color: "var(--text-secondary)" }}>{oc.proveedor_nombre}</div>
                <div style={{ fontSize: 11, color: "var(--text-secondary)" }}>{oc.condiciones_pago || "—"}</div>
                <div style={{ fontSize: 12, fontWeight: 700, color: "var(--text-primary)" }}>{fmt(oc.total)}</div>
                <div>
                  <span style={{
                    fontSize: 9,
                    fontWeight: 700,
                    letterSpacing: "0.06em",
                    color: est.color,
                    border: `1px solid ${est.color}`,
                    padding: "2px 7px",
                  }}>{est.label}</span>
                </div>
                <div style={{ fontSize: 11, color: "var(--text-muted)" }}>{fmtFecha(oc.created_at)}</div>
              </div>
            );
          })
        )}
      </div>
    </>
  );
}
