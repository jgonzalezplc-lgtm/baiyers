"use client";
import { useEffect, useMemo, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { ArrowLeft, Send } from "lucide-react";
import { createClient } from "@/lib/supabase/client";
import { authFetch } from "@/lib/authFetch";
import { Badge, BtnPrimary, BtnSecondary, Card, Input, SkeletonBox, SkeletonText, CascadeWrapper } from "@/components/ui";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const fmtCLP = (n: number) => `$${Math.round(n).toLocaleString("es-CL")}`;
type Definitivo = { proveedor?: string; precio_clp?: number | null; url?: string | null; origen?: "sugerido" | "proveedor" | "buscado_web" };
type Item = { cotizacion_id: string; nombre: string; cantidad: number; definitivo: Definitivo | null };
type Lista = { id: string; nombre: string; items: Item[]; justificaciones?: Record<string, string> };
type ResponsableSugerido = { id: string; nombre: string; email: string };
type Sugerencia = { nodo_nombre: string; modo_autorizacion: string; responsables: ResponsableSugerido[] };
const ORIGEN_LABEL = { sugerido: "Sugerido", proveedor: "Proveedor", buscado_web: "Buscado por web" } as const;

export default function AutorizarListaPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [lista, setLista] = useState<Lista | null>(null);
  const [userId, setUserId] = useState("");
  const [meta, setMeta] = useState<Record<string, string>>({});
  const [email, setEmail] = useState("");
  const [sugerencia, setSugerencia] = useState<Sugerencia | null>(null);
  const [cargandoSugerencia, setCargandoSugerencia] = useState(true);
  const [justificaciones, setJustificaciones] = useState<Record<string, string>>({});
  const [enviando, setEnviando] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => { createClient().auth.getUser().then(async ({ data }) => {
    const u = data.user; if (!u) return router.replace("/login");
    setUserId(u.id); const m = u.user_metadata as Record<string, string>; setMeta(m); setEmail(m.autorizador_email || "");
    const r = await authFetch(`${API_URL}/api/listas/${id}`);
    if (r.ok) {
      const d = await r.json(); setLista(d);
      const automaticas = JSON.parse(sessionStorage.getItem(`baiyer:justificaciones:${id}`) || "{}"); setJustificaciones({ ...automaticas, ...(d.justificaciones || {}) }); sessionStorage.removeItem(`baiyer:justificaciones:${id}`);
      const total = (d.items || []).filter((i: Item) => i.definitivo).reduce((s: number, i: Item) => s + (i.definitivo?.precio_clp || 0) * (i.cantidad || 1), 0);
      const sug = await authFetch(`${API_URL}/api/workflows/autorizadores-sugeridos?monto_total=${total}`).then(x => x.json()).catch(() => null);
      setSugerencia(sug || null);
    }
    else setError("No se pudo cargar la lista.");
    setCargandoSugerencia(false);
  }); }, [id, router]);

  const definitivos = useMemo(() => lista?.items.filter(i => i.definitivo) || [], [lista]);
  const total = definitivos.reduce((s, i) => s + (i.definitivo?.precio_clp || 0) * (i.cantidad || 1), 0);
  const puedeEnviar = !!sugerencia || !!email.trim();
  const enviar = async () => {
    if (!lista || !userId || !puedeEnviar) return;
    setEnviando(true); setError("");
    try {
      const r = await authFetch(`${API_URL}/api/listas/${id}/solicitar-aprobacion`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ aprobador_email: email.trim() || null, justificaciones, nombre_solicitante: meta.nombre_usuario || "", empresa: meta.empresa || "" }) });
      const d = await r.json(); if (!r.ok) throw new Error(d.detail || "No se pudo crear la solicitud");
      // El backend ya envió el correo por la cuenta Gmail conectada del
      // usuario (misma integración que se usa para cotizar a proveedores);
      // no hay que abrir el cliente de correo local.
      router.replace(`/listas/${id}`);
    } catch (e) { setError(e instanceof Error ? e.message : "Error al enviar"); }
    finally { setEnviando(false); }
  };
  if (!lista) return error ? (
    <div style={{ padding: "48px 0", textAlign: "center", fontSize: 13.5, color: "var(--n-500)" }}>{error}</div>
  ) : (
    <div style={{ maxWidth: 820, margin: "0 auto" }}>
      <SkeletonBox height={26} width={280} style={{ marginBottom: 8 }} />
      <SkeletonBox height={13} width={400} style={{ marginBottom: 20 }} />
      <Card padding={18} style={{ marginBottom: 16 }}><SkeletonBox height={38} width="100%" /></Card>
      <CascadeWrapper>
        {Array.from({ length: 2 }).map((_, i) => (
          <Card key={i} padding={18} style={{ marginBottom: 12 }}>
            <SkeletonBox height={15} width="40%" style={{ marginBottom: 10 }} />
            <SkeletonText lines={2} widths={["60%", "45%"]} />
          </Card>
        ))}
      </CascadeWrapper>
    </div>
  );
  return <div style={{ maxWidth: 820, margin: "0 auto" }}>
    <button onClick={() => router.back()} style={{ border: 0, background: "none", color: "var(--n-600)", cursor: "pointer", display: "inline-flex", gap: 6, alignItems: "center", marginBottom: 16 }}><ArrowLeft size={16} /> Volver a la selección</button>
    <h1 style={{ margin: "0 0 6px", fontSize: 26 }}>Solicitar autorización</h1>
    <p style={{ color: "var(--n-600)", margin: "0 0 20px" }}>Lista: <strong>{lista.nombre}</strong>. Explica por qué se eligió cada alternativa antes de enviarla.</p>
    <Card padding={18} style={{ marginBottom: 16 }}>
      {cargandoSugerencia ? (
        <div>
          <SkeletonBox height={13} width="55%" style={{ marginBottom: 8 }} />
          <div style={{ display: "flex", gap: 6 }}>
            <SkeletonBox height={24} width={130} radius="var(--r-sm)" />
            <SkeletonBox height={24} width={110} radius="var(--r-sm)" />
          </div>
        </div>
      ) : sugerencia ? (
        <div>
          <div style={{ fontSize: 13, color: "var(--n-600)", marginBottom: 6 }}>Según tu ciclo de compras, esto se enviará a <strong>{sugerencia.nodo_nombre}</strong>{sugerencia.modo_autorizacion === "secuencial" ? " (en orden)" : sugerencia.responsables.length > 1 ? " (todos deben aprobar)" : ""}:</div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
            {sugerencia.responsables.map(r => (
              <span key={r.id} style={{ fontSize: 12.5, padding: "4px 9px", borderRadius: "var(--r-sm)", background: "var(--brand-50)", color: "var(--brand)", border: "1px solid var(--n-200)" }}>{r.nombre} · {r.email}</span>
            ))}
          </div>
        </div>
      ) : (
        <Input label="Email del autorizador" type="email" value={email} onChange={e => setEmail(e.target.value)} placeholder="jefe@empresa.cl" />
      )}
    </Card>
    <div style={{ fontSize: 12, fontWeight: 600, color: "var(--n-600)", textTransform: "uppercase", letterSpacing: ".04em", margin: "18px 0 8px" }}>Seleccionados para autorización</div>
    {definitivos.map(item => <Card key={item.cotizacion_id} padding={18} style={{ marginBottom: 12 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
        <div style={{ fontSize: 15, fontWeight: 700 }}>{item.nombre} <span style={{ color: "var(--n-500)", fontWeight: 400 }}>× {item.cantidad}</span></div>
        <Badge status={item.definitivo?.origen === "buscado_web" ? "cotizando" : "aprobada"}>{ORIGEN_LABEL[item.definitivo?.origen || "buscado_web"]}</Badge>
      </div>
      <div style={{ margin: "8px 0", fontSize: 14 }}>{item.definitivo?.proveedor || "—"} · <a href={item.definitivo?.url || "#"} target="_blank" rel="noreferrer">Ver producto ↗</a> · <strong>{item.definitivo?.precio_clp != null ? fmtCLP(item.definitivo.precio_clp * item.cantidad) : "—"}</strong></div>
      <Input label="Justificación" value={justificaciones[item.cotizacion_id] || ""} onChange={e => setJustificaciones(j => ({ ...j, [item.cotizacion_id]: e.target.value }))} placeholder="Ej: mejor precio, entrega rápida, proveedor homologado…" />
    </Card>)}
    <Card padding={18} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 16 }}><strong>Total: {fmtCLP(total)}</strong><div style={{ display: "flex", gap: 10 }}><BtnSecondary onClick={() => router.back()}>Cancelar</BtnSecondary><BtnPrimary onClick={enviar} disabled={!puedeEnviar || enviando} icon={Send}>{enviando ? "Preparando…" : "Enviar al autorizador"}</BtnPrimary></div></Card>
    {error && <p style={{ color: "var(--danger)", marginTop: 12 }}>{error}</p>}
  </div>;
}
