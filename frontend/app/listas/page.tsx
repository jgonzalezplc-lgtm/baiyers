"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { createClient } from "@/lib/supabase/client";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface ListaResumen {
  id: string;
  nombre: string;
  created_at: string | null;
  monto_total: number;
  n_items: number;
  n_comparados: number;
  n_definitivos: number;
}

export default function ListasPage() {
  const [listas, setListas] = useState<ListaResumen[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    createClient().auth.getUser().then(({ data }) => {
      const uid = data.user?.id;
      if (!uid) { setLoading(false); return; }
      fetch(`${API_URL}/api/listas?user_id=${uid}`)
        .then(r => (r.ok ? r.json() : []))
        .then(setListas)
        .catch(() => {})
        .finally(() => setLoading(false));
    });
  }, []);

  return (
    <>
      <div style={{ marginBottom: 24 }}>
        <div className="section-rule" style={{ marginBottom: 14 }} />
        <h1 style={{ fontSize: 22, fontWeight: 700, color: "var(--text-primary)", margin: "0 0 6px", letterSpacing: "-0.02em" }}>
          Listas de cotización
        </h1>
        <p style={{ fontSize: 12, color: "var(--text-secondary)", margin: 0 }}>
          Varios ítems cotizados en paralelo. Crea una nueva separando ítems con &quot;;&quot; en{" "}
          <Link href="/cotizar" style={{ color: "var(--accent)" }}>Nueva cotización</Link>.
        </p>
      </div>

      {loading ? (
        <div style={{ padding: "40px 0", textAlign: "center", fontSize: 12, color: "var(--text-muted)" }}>Cargando…</div>
      ) : listas.length === 0 ? (
        <div style={{ background: "var(--bg-surface)", border: "1px solid var(--border-default)", padding: "48px 20px", textAlign: "center" }}>
          <div className="label" style={{ color: "var(--text-muted)", marginBottom: 8 }}>Sin listas</div>
          <div style={{ fontSize: 12, color: "var(--text-secondary)", marginBottom: 16 }}>
            Escribe varios ítems separados por &quot;;&quot; en Nueva cotización, ej: <em>martillo; taladro; madera</em>
          </div>
          <Link href="/cotizar" className="btn-swiss-primary" style={{ textDecoration: "none" }}>Nueva cotización</Link>
        </div>
      ) : (
        <div style={{ border: "1px solid var(--border-default)", background: "var(--bg-surface)" }}>
          <div style={{
            display: "grid", gridTemplateColumns: "1fr 110px 130px 130px 130px",
            padding: "9px 16px", borderBottom: "1px solid var(--border-default)", background: "var(--bg-base)",
          }}>
            {["LISTA", "ÍTEMS", "COMPARADOS", "DEFINITIVOS", "TOTAL"].map(h => (
              <div key={h} style={{ fontSize: 9, fontWeight: 700, color: "var(--text-muted)", letterSpacing: "0.06em" }}>{h}</div>
            ))}
          </div>
          {listas.map((l, i) => (
            <Link key={l.id} href={`/listas/${l.id}`} style={{ textDecoration: "none" }}>
              <div style={{
                display: "grid", gridTemplateColumns: "1fr 110px 130px 130px 130px",
                padding: "13px 16px", alignItems: "center", cursor: "pointer",
                borderBottom: i < listas.length - 1 ? "1px solid var(--border-subtle)" : "none",
              }}>
                <div>
                  <div style={{ fontSize: 12, fontWeight: 700, color: "var(--text-primary)" }}>{l.nombre}</div>
                  {l.created_at && (
                    <div className="label" style={{ color: "var(--text-muted)", marginTop: 2 }}>
                      {new Date(l.created_at).toLocaleDateString("es-CL")}
                    </div>
                  )}
                </div>
                <div style={{ fontSize: 12, color: "var(--text-secondary)" }}>{l.n_items}</div>
                <div style={{ fontSize: 12, color: l.n_comparados === l.n_items ? "var(--text-success)" : "var(--text-secondary)" }}>
                  {l.n_comparados}/{l.n_items}
                </div>
                <div style={{ fontSize: 12, color: l.n_definitivos === l.n_items ? "var(--text-success)" : "var(--text-secondary)" }}>
                  {l.n_definitivos}/{l.n_items}
                </div>
                <div style={{ fontSize: 12, fontWeight: 700, color: "var(--text-primary)" }}>
                  {l.monto_total ? `$${Math.round(l.monto_total).toLocaleString("es-CL")}` : "—"}
                </div>
              </div>
            </Link>
          ))}
        </div>
      )}
    </>
  );
}
