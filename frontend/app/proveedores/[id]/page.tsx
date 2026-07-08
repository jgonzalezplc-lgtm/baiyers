"use client";
import { useState, useEffect } from "react";
import { useParams } from "next/navigation";
import { createClient } from "@/lib/supabase/client";
import Link from "next/link";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface Rating {
  id: string;
  estrellas: number;
  precio_cumplido: boolean | null;
  plazo_cumplido: boolean | null;
  comentario: string | null;
  created_at: string;
}

interface Orden {
  numero_oc: string;
  estado: string;
  precio_total: number;
  moneda: string;
  created_at: string;
  confirmada_at: string | null;
}

interface Proveedor {
  id: string;
  nombre: string;
  email?: string;
  score: number;
  categoria_score: string;
  total_solicitudes: number;
  total_oc_enviadas: number;
  total_oc_confirmadas: number;
  total_respuestas: number;
  bloqueado: boolean;
}

const CATEGORIAS: Record<string, { label: string; color: string }> = {
  preferido:      { label: "Preferido",    color: "#f59e0b" },
  confiable:      { label: "Confiable",    color: "#34d399" },
  con_reparos:    { label: "Con reparos",  color: "#94a3b8" },
  problematico:   { label: "Problematico", color: "#f87171" },
  bloqueado_auto: { label: "Bloqueado",    color: "#475569" },
};

function Estrellas({ n }: { n: number }) {
  return (
    <span>
      {[1, 2, 3, 4, 5].map(i => (
        <span key={i} style={{ color: i <= n ? "#f59e0b" : "#334155", fontSize: 14 }}>★</span>
      ))}
    </span>
  );
}

export default function ProveedorHistorialPage() {
  const params = useParams();
  const proveedorId = params.id as string;

  const [proveedor, setProveedor] = useState<Proveedor | null>(null);
  const [ratings, setRatings] = useState<Rating[]>([]);
  const [ordenes, setOrdenes] = useState<Orden[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [userId, setUserId] = useState<string | null>(null);

  useEffect(() => {
    createClient().auth.getUser().then(({ data }) => {
      const uid = data.user?.id ?? null;
      setUserId(uid);
      if (uid) cargar(uid);
    });
  }, [proveedorId]);

  const cargar = async (uid: string) => {
    setLoading(true);
    try {
      const res = await fetch(`${API_URL}/api/suppliers/${proveedorId}/historial?user_id=${uid}`);
      if (!res.ok) throw new Error();
      const data = await res.json();
      setProveedor(data.proveedor);
      setRatings(data.ratings);
      setOrdenes(data.ordenes);
    } catch {
      setError("Error cargando el historial.");
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <div style={{ minHeight: "100vh", background: "#060610", display: "flex", alignItems: "center", justifyContent: "center" }}>
        <div style={{ fontSize: 11, color: "#475569" }}>Cargando...</div>
      </div>
    );
  }

  if (error || !proveedor) {
    return (
      <div style={{ minHeight: "100vh", background: "#060610", display: "flex", alignItems: "center", justifyContent: "center", padding: 20 }}>
        <div style={{ fontSize: 13, color: "#f87171" }}>{error || "Proveedor no encontrado"}</div>
      </div>
    );
  }

  const cat = CATEGORIAS[proveedor.bloqueado ? "bloqueado_auto" : proveedor.categoria_score] ?? CATEGORIAS.con_reparos;

  return (
    <div style={{ minHeight: "100vh", background: "#060610", padding: "24px 20px" }}>
      <div style={{ maxWidth: 800, margin: "0 auto" }}>

        <div style={{ marginBottom: 24 }}>
          <Link href="/proveedores" style={{ fontSize: 10, color: "#475569", textDecoration: "none" }}>← Proveedores</Link>
        </div>

        {/* Header proveedor */}
        <div style={{ background: "#0a0a18", border: "1px solid #1a1a2e", borderRadius: 12, padding: "20px 24px", marginBottom: 20 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
            <div>
              <div style={{ fontSize: 10, color: "#6366f1", textTransform: "uppercase", letterSpacing: "0.15em", marginBottom: 4 }}>Supplier Intelligence</div>
              <h1 style={{ fontSize: 18, fontWeight: 800, color: "#f1f5f9", margin: "0 0 4px" }}>{proveedor.nombre}</h1>
              {proveedor.email && <div style={{ fontSize: 10, color: "#475569" }}>{proveedor.email}</div>}
            </div>
            <div style={{ textAlign: "right" }}>
              <div style={{ fontSize: 32, fontWeight: 800, color: cat.color }}>{proveedor.score}</div>
              <div style={{ fontSize: 10, color: cat.color, fontWeight: 700 }}>{cat.label}</div>
            </div>
          </div>

          <div style={{ display: "flex", gap: 20, marginTop: 16, flexWrap: "wrap" }}>
            {[
              { label: "Solicitudes enviadas", val: proveedor.total_solicitudes || 0 },
              { label: "Respuestas recibidas", val: proveedor.total_respuestas || 0 },
              { label: "OCs emitidas", val: proveedor.total_oc_enviadas || 0 },
              { label: "OCs confirmadas", val: proveedor.total_oc_confirmadas || 0 },
            ].map(m => (
              <div key={m.label}>
                <div style={{ fontSize: 9, color: "#334155", textTransform: "uppercase", letterSpacing: "0.08em" }}>{m.label}</div>
                <div style={{ fontSize: 20, fontWeight: 800, color: "#94a3b8" }}>{m.val}</div>
              </div>
            ))}
          </div>
        </div>

        {/* Ordenes de Compra */}
        <div style={{ marginBottom: 20 }}>
          <div style={{ fontSize: 11, color: "#475569", textTransform: "uppercase", letterSpacing: "0.1em", marginBottom: 10, fontWeight: 700 }}>
            Ordenes de Compra ({ordenes.length})
          </div>
          {ordenes.length === 0 ? (
            <div style={{ fontSize: 11, color: "#334155", padding: "16px 0" }}>Sin ordenes de compra.</div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              {ordenes.map(oc => (
                <div key={oc.numero_oc} style={{ background: "#0a0a18", border: "1px solid #1a1a2e", borderRadius: 8, padding: "12px 16px", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <div>
                    <div style={{ fontSize: 12, fontWeight: 700, color: "#f1f5f9" }}>{oc.numero_oc}</div>
                    <div style={{ fontSize: 10, color: "#475569", marginTop: 2 }}>
                      {new Date(oc.created_at).toLocaleDateString("es-CL")}
                      {oc.confirmada_at && ` · Confirmada ${new Date(oc.confirmada_at).toLocaleDateString("es-CL")}`}
                    </div>
                  </div>
                  <div style={{ textAlign: "right" }}>
                    <div style={{ fontSize: 12, fontWeight: 700, color: "#94a3b8" }}>
                      {oc.moneda} {Number(oc.precio_total).toLocaleString("es-CL")}
                    </div>
                    <div style={{ fontSize: 10, marginTop: 2, color: oc.estado === "confirmada" ? "#34d399" : oc.estado === "enviada" ? "#6366f1" : "#475569", fontWeight: 600 }}>
                      {oc.estado}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Ratings */}
        <div>
          <div style={{ fontSize: 11, color: "#475569", textTransform: "uppercase", letterSpacing: "0.1em", marginBottom: 10, fontWeight: 700 }}>
            Calificaciones ({ratings.length})
          </div>
          {ratings.length === 0 ? (
            <div style={{ fontSize: 11, color: "#334155", padding: "16px 0" }}>Sin calificaciones aun.</div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {ratings.map(r => (
                <div key={r.id} style={{ background: "#0a0a18", border: "1px solid #1a1a2e", borderRadius: 8, padding: "14px 16px" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 8 }}>
                    <Estrellas n={r.estrellas} />
                    <span style={{ fontSize: 10, color: "#334155" }}>{new Date(r.created_at).toLocaleDateString("es-CL")}</span>
                  </div>
                  <div style={{ display: "flex", gap: 12, marginBottom: r.comentario ? 8 : 0 }}>
                    {r.precio_cumplido !== null && (
                      <span style={{ fontSize: 10, color: r.precio_cumplido ? "#34d399" : "#f87171" }}>
                        Precio: {r.precio_cumplido ? "Si" : "No"}
                      </span>
                    )}
                    {r.plazo_cumplido !== null && (
                      <span style={{ fontSize: 10, color: r.plazo_cumplido ? "#34d399" : "#f87171" }}>
                        Plazo: {r.plazo_cumplido ? "Si" : "No"}
                      </span>
                    )}
                  </div>
                  {r.comentario && (
                    <div style={{ fontSize: 11, color: "#94a3b8", fontStyle: "italic" }}>"{r.comentario}"</div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
