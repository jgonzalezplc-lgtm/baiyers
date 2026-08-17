"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { ArrowLeft, CheckCircle2, FileQuestion, XCircle } from "lucide-react";
import { authFetch } from "@/lib/authFetch";
import { Badge, BtnGhost, BtnPrimary, BtnSecondary, Card, CascadeWrapper, SkeletonBox } from "@/components/ui";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface Caso {
  id: string;
  estado: string;
  requisitos: string[];
  antecedentes_recibidos: string[];
  comentario_decision?: string | null;
  proveedores?: { nombre?: string; email?: string | null };
  responsables?: { nombre?: string; email?: string | null };
  recibido_at?: string | null;
}

const LABEL: Record<string, string> = {
  solicitado: "Esperando antecedentes",
  recepcion_parcial: "Recepción parcial",
  en_revision: "Listo para revisar",
  requiere_aclaracion: "Información pendiente",
  homologado: "Homologado",
  rechazado: "Rechazado",
};

export default function HomologacionListaPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [casos, setCasos] = useState<Caso[]>([]);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState("");
  const [procesando, setProcesando] = useState<string | null>(null);
  const [comentarios, setComentarios] = useState<Record<string, string>>({});
  const [pendientes, setPendientes] = useState<Record<string, string>>({});

  const cargar = useCallback(async () => {
    setCargando(true); setError("");
    try {
      const res = await authFetch(`${API_URL}/api/workflows/homologacion/casos?lista_id=${encodeURIComponent(id)}`);
      if (!res.ok) throw new Error((await res.json().catch(() => null))?.detail || "No se pudo cargar la homologación");
      const data = await res.json();
      setCasos(data.casos || []);
    } catch (e) { setError(e instanceof Error ? e.message : "Error inesperado"); }
    finally { setCargando(false); }
  }, [id]);

  useEffect(() => { void cargar(); }, [cargar]);

  async function decidir(caso: Caso, decision: "incompleta" | "homologado" | "rechazado") {
    setProcesando(caso.id); setError("");
    try {
      const reqs = (pendientes[caso.id] || "").split("\n").map(v => v.trim()).filter(Boolean);
      const res = await authFetch(`${API_URL}/api/workflows/homologacion/${caso.id}/decidir`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ decision, comentario: comentarios[caso.id] || "", requisitos_pendientes: reqs }),
      });
      if (!res.ok) throw new Error((await res.json().catch(() => null))?.detail || "No se pudo guardar la decisión");
      await cargar();
    } catch (e) { setError(e instanceof Error ? e.message : "Error inesperado"); }
    finally { setProcesando(null); }
  }

  return (
    <CascadeWrapper>
      <div style={{ maxWidth: 980, margin: "0 auto", padding: "28px 20px 60px" }}>
        <BtnGhost onClick={() => router.push(`/listas/${id}`)} size="sm"><ArrowLeft size={15} /> Volver a la lista</BtnGhost>
        <div style={{ margin: "18px 0 20px" }}>
          <h1 style={{ fontSize: 25, margin: 0, color: "var(--n-900)" }}>Homologación de proveedores</h1>
          <p style={{ color: "var(--n-600)", fontSize: 13.5, marginTop: 6 }}>La recepción del correo no homologa automáticamente: la decisión siempre es humana.</p>
        </div>
        {error && <div style={{ color: "var(--danger)", fontSize: 13, marginBottom: 14 }}>{error}</div>}
        {cargando ? <SkeletonBox height={180} /> : casos.length === 0 ? (
          <Card padding={20}>No hay expedientes de homologación para esta lista.</Card>
        ) : <div style={{ display: "grid", gap: 14 }}>
          {casos.map(caso => {
            const terminal = ["homologado", "rechazado"].includes(caso.estado);
            return <Card key={caso.id} padding={18}>
              <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "flex-start" }}>
                <div>
                  <div style={{ fontWeight: 700, color: "var(--n-900)" }}>{caso.proveedores?.nombre || "Proveedor"}</div>
                  <div style={{ fontSize: 12, color: "var(--n-500)", marginTop: 2 }}>{caso.proveedores?.email || "Sin email"} · Responsable: {caso.responsables?.nombre || "—"}</div>
                </div>
                <Badge>{LABEL[caso.estado] || caso.estado}</Badge>
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))", gap: 14, marginTop: 15 }}>
                <div>
                  <div style={{ fontSize: 11.5, fontWeight: 650, color: "var(--n-700)", marginBottom: 5 }}>Antecedentes solicitados</div>
                  <ul style={{ margin: 0, paddingLeft: 18, fontSize: 12.5, color: "var(--n-600)", lineHeight: 1.6 }}>{(caso.requisitos || []).map(r => <li key={r}>{r}</li>)}</ul>
                </div>
                <div>
                  <div style={{ fontSize: 11.5, fontWeight: 650, color: "var(--n-700)", marginBottom: 5 }}>Archivos recibidos</div>
                  {(caso.antecedentes_recibidos || []).length ? <ul style={{ margin: 0, paddingLeft: 18, fontSize: 12.5, color: "var(--n-600)", lineHeight: 1.6 }}>{caso.antecedentes_recibidos.map(a => <li key={a}>{a}</li>)}</ul> : <div style={{ fontSize: 12.5, color: "var(--n-500)" }}>Todavía no hay adjuntos registrados.</div>}
                </div>
              </div>
              {!terminal && <div style={{ borderTop: "1px solid var(--n-200)", marginTop: 15, paddingTop: 14 }}>
                <textarea value={comentarios[caso.id] || ""} onChange={e => setComentarios(v => ({ ...v, [caso.id]: e.target.value }))} placeholder="Comentario o fundamento de la decisión" rows={2} style={{ width: "100%", resize: "vertical", padding: 8, fontFamily: "inherit", fontSize: 12.5, border: "1px solid var(--n-300)", background: "var(--surface)", color: "var(--n-900)" }} />
                <textarea value={pendientes[caso.id] || ""} onChange={e => setPendientes(v => ({ ...v, [caso.id]: e.target.value }))} placeholder="Si falta información, escribe un requisito por línea" rows={2} style={{ width: "100%", resize: "vertical", padding: 8, marginTop: 7, fontFamily: "inherit", fontSize: 12.5, border: "1px solid var(--n-300)", background: "var(--surface)", color: "var(--n-900)" }} />
                <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginTop: 9 }}>
                  <BtnSecondary disabled={!!procesando} onClick={() => void decidir(caso, "incompleta")}><FileQuestion size={14} /> Solicitar faltantes</BtnSecondary>
                  <BtnPrimary disabled={!!procesando} onClick={() => void decidir(caso, "homologado")}><CheckCircle2 size={14} /> Homologar</BtnPrimary>
                  <button disabled={!!procesando} onClick={() => void decidir(caso, "rechazado")} style={{ border: "1px solid var(--danger)", color: "var(--danger)", background: "transparent", padding: "7px 11px", cursor: "pointer" }}><XCircle size={14} style={{ verticalAlign: -2, marginRight: 5 }} />Rechazar</button>
                </div>
              </div>}
              {terminal && caso.comentario_decision && <div style={{ marginTop: 12, fontSize: 12.5, color: "var(--n-600)" }}>Decisión: {caso.comentario_decision}</div>}
            </Card>;
          })}
        </div>}
      </div>
    </CascadeWrapper>
  );
}
