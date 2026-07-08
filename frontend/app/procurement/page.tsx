"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { createClient } from "@/lib/supabase/client";
import { API_URL, EVENTO_ESTADO_META, fmtFecha } from "./constants";

interface EventoResumen {
  id: string;
  nombre: string;
  descripcion: string | null;
  estado: string;
  created_at: string;
  n_items: number;
  n_proveedores: number;
  n_cotizados: number;
  n_oc: number;
}

export default function ProcurementListPage() {
  const [userId, setUserId] = useState<string | null>(null);
  const [eventos, setEventos] = useState<EventoResumen[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    createClient().auth.getUser().then(({ data }) => setUserId(data.user?.id ?? null));
  }, []);

  useEffect(() => {
    if (!userId) return;
    fetch(`${API_URL}/api/procurement/eventos?user_id=${userId}`)
      .then((r) => r.json())
      .then((d) => setEventos(Array.isArray(d) ? d : []))
      .finally(() => setLoading(false));
  }, [userId]);

  return (
    <div style={{ maxWidth: 1100, margin: "0 auto", padding: "32px 24px" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", marginBottom: 24 }}>
        <div>
          <h1 style={{ fontSize: 22, fontWeight: 800, letterSpacing: "-0.02em", margin: 0 }}>Listas de cotización</h1>
          <p className="label" style={{ color: "var(--text-muted)", marginTop: 4 }}>
            Eventos de compra · funnel de cotización a orden de compra
          </p>
        </div>
        <Link href="/cotizar" className="btn-swiss-primary" style={{ fontSize: 12, padding: "8px 14px", textDecoration: "none" }}>
          + Nueva búsqueda
        </Link>
      </div>

      {loading ? (
        <div className="label" style={{ color: "var(--text-muted)" }}>Cargando…</div>
      ) : eventos.length === 0 ? (
        <div style={{ border: "1px solid var(--border-default)", padding: 32, textAlign: "center" }}>
          <div className="label" style={{ color: "var(--text-muted)" }}>
            Aún no tienes listas de cotización. Busca un producto y agrega proveedores para crear una.
          </div>
        </div>
      ) : (
        <div style={{ border: "1px solid var(--border-default)", borderBottom: "none" }}>
          <div style={{
            display: "grid", gridTemplateColumns: "1fr 110px 90px 100px 110px 100px",
            gap: 8, padding: "8px 14px", background: "var(--bg-surface)",
            borderBottom: "1px solid var(--border-default)",
          }}>
            {["EVENTO", "ESTADO", "ÍTEMS", "PROVEEDORES", "COTIZADOS", "FECHA"].map((h) => (
              <span key={h} className="label" style={{ fontWeight: 700 }}>{h}</span>
            ))}
          </div>
          {eventos.map((e) => {
            const em = EVENTO_ESTADO_META[e.estado] ?? EVENTO_ESTADO_META.borrador;
            return (
              <Link key={e.id} href={`/procurement/${e.id}`} style={{
                display: "grid", gridTemplateColumns: "1fr 110px 90px 100px 110px 100px",
                gap: 8, padding: "12px 14px", borderBottom: "1px solid var(--border-default)",
                textDecoration: "none", color: "var(--text-primary)", alignItems: "center",
                background: e.n_oc > 0 ? "var(--fill-success)" : "var(--bg-base)",
              }}>
                <div style={{ minWidth: 0 }}>
                  <div style={{ fontSize: 13, fontWeight: 700, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{e.nombre}</div>
                  {e.descripcion && <div className="label" style={{ color: "var(--text-muted)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{e.descripcion}</div>}
                </div>
                <span className="label" style={{ color: em.color, background: em.bg, padding: "2px 6px", justifySelf: "start", fontWeight: 700 }}>{em.label}</span>
                <span className="label">{e.n_items}</span>
                <span className="label">{e.n_proveedores}</span>
                <span className="label">{e.n_cotizados}/{e.n_proveedores}</span>
                <span className="label" style={{ color: "var(--text-muted)" }}>{fmtFecha(e.created_at)}</span>
              </Link>
            );
          })}
        </div>
      )}
    </div>
  );
}
