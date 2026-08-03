"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { AlertTriangle, ArrowLeft, Check, Mail, Send } from "lucide-react";
import { createClient } from "@/lib/supabase/client";
import { Badge, BtnPrimary, BtnSecondary, Card, CategoryChip, EmptyState, Input, PageHeader, SkeletonBox, CascadeWrapper, Textarea } from "@/components/ui";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface RFQItem { id: string; cotizacion_id: string; resultado_id: string; nombre: string; categoria: string; cantidad: number; unidad: string; estado: string; }
interface RFQBatch { id: string; proveedor_id: string; destinatario_email: string; subject: string; body: string; estado: string; error_detalle?: string; sent_at?: string; proveedor: { nombre?: string; score?: number; preferido?: boolean }; items: RFQItem[]; }

export default function RevisarRFQPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [userId, setUserId] = useState<string | null>(null);
  const [batches, setBatches] = useState<RFQBatch[]>([]);
  const [loading, setLoading] = useState(true);
  const [ocupado, setOcupado] = useState<string | null>(null);
  const [mensaje, setMensaje] = useState("");

  const cargar = useCallback(async (uid: string) => {
    setLoading(true);
    try {
      const res = await fetch(`${API_URL}/api/listas/${id}/rfq?user_id=${uid}`);
      const data = await res.json(); if (!res.ok) throw new Error(data.detail);
      setBatches(data.batches || []);
    } catch (e) { setMensaje(e instanceof Error ? e.message : "No pudimos cargar los borradores"); }
    finally { setLoading(false); }
  }, [id]);

  useEffect(() => { createClient().auth.getUser().then(({ data }) => { if (data.user) { setUserId(data.user.id); void cargar(data.user.id); } }); }, [cargar]);

  const editarLocal = (batchId: string, campo: "destinatario_email" | "subject" | "body", valor: string) => setBatches(prev => prev.map(b => b.id === batchId ? { ...b, [campo]: valor } : b));

  const guardar = async (batch: RFQBatch): Promise<boolean> => {
    if (!userId) return false;
    const res = await fetch(`${API_URL}/api/listas/${id}/rfq/${batch.id}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ user_id: userId, destinatario_email: batch.destinatario_email, subject: batch.subject, body: batch.body }) });
    const data = await res.json();
    if (!res.ok) { setMensaje(data.detail || "No pudimos guardar el borrador"); return false; }
    setBatches(prev => prev.map(b => b.id === batch.id ? { ...b, ...data } : b));
    return true;
  };

  const enviar = async (batch: RFQBatch) => {
    if (!userId || batch.estado === "sent") return;
    setOcupado(batch.id); setMensaje("");
    try {
      if (!(await guardar(batch))) return;
      const res = await fetch(`${API_URL}/api/listas/${id}/rfq/${batch.id}/enviar`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ user_id: userId }) });
      const data = await res.json(); if (!res.ok) throw new Error(data.detail);
      setBatches(prev => prev.map(b => b.id === batch.id ? { ...b, estado: "sent", sent_at: new Date().toISOString() } : b));
      setMensaje(`Correo enviado a ${batch.proveedor.nombre || batch.destinatario_email}.`);
    } catch (e) { setMensaje(e instanceof Error ? e.message : "No pudimos enviar el correo"); await cargar(userId); }
    finally { setOcupado(null); }
  };

  if (loading) return (
    <div>
      <SkeletonBox height={13} width={140} style={{ marginBottom: 14 }} />
      <SkeletonBox height={20} width={280} style={{ marginBottom: 8 }} />
      <SkeletonBox height={13} width={380} style={{ marginBottom: 20 }} />
      <div style={{ display: "grid", gap: 16 }}>
        <CascadeWrapper staggerMs={80}>
          {Array.from({ length: 2 }).map((_, i) => (
            <Card key={i}>
              <div style={{ display: "flex", justifyContent: "space-between", gap: 12, marginBottom: 14 }}>
                <SkeletonBox height={17} width={160} />
                <SkeletonBox height={20} width={80} />
              </div>
              <div style={{ display: "grid", gap: 11 }}>
                <SkeletonBox height={38} width="100%" />
                <SkeletonBox height={38} width="100%" />
                <SkeletonBox height={90} width="100%" />
              </div>
            </Card>
          ))}
        </CascadeWrapper>
      </div>
    </div>
  );
  const enviados = batches.filter(b => b.estado === "sent").length;

  return <>
    <Link href={`/listas/${id}/proveedores-confianza`} style={{ display: "inline-flex", gap: 6, alignItems: "center", color: "var(--n-600)", textDecoration: "none", fontSize: 13, marginBottom: 14 }}><ArrowLeft size={15} /> Volver a la matriz</Link>
    <PageHeader eyebrow="RFQ agrupada" title="Revisar correos a proveedores" subtitle="Se enviará un correo por proveedor, únicamente con los ítems asignados." />
    {mensaje && <div style={{ padding: 11, marginBottom: 14, borderRadius: "var(--r-md)", background: "var(--surface-2)", color: "var(--n-700)", fontSize: 13 }}>{mensaje}</div>}

    {batches.length === 0 ? <Card><EmptyState icon={Mail} title="No hay correos preparados" description="Vuelve a la matriz, selecciona al menos un proveedor y prepara los borradores." /></Card> : <>
      <Card style={{ marginBottom: 16 }}><div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12, flexWrap: "wrap" }}><div><strong style={{ color: "var(--n-900)" }}>{batches.length} correos agrupados</strong><div style={{ color: "var(--n-500)", fontSize: 12.5, marginTop: 3 }}>{enviados} enviados · {batches.length - enviados} pendientes</div></div><div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}><Badge status={enviados === batches.length ? "aprobada" : "cotizando"}>{enviados === batches.length ? "Completado" : "En revisión"}</Badge>{enviados > 0 && <BtnPrimary onClick={() => router.push(`/listas/${id}`)}>Ir al comparador</BtnPrimary>}<BtnSecondary onClick={() => router.push(`/listas/${id}/busqueda-complementaria`)}>Búsqueda complementaria</BtnSecondary></div></div></Card>
      <div style={{ display: "grid", gap: 16 }}>{batches.map(batch => { const bloqueado = ["sent", "sending", "delivery_uncertain"].includes(batch.estado); return <Card key={batch.id}>
        <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "flex-start", marginBottom: 14 }}><div><h2 style={{ margin: 0, fontSize: 17, color: "var(--n-900)" }}>{batch.proveedor.nombre || "Proveedor"}</h2><div style={{ color: "var(--n-500)", fontSize: 12.5, marginTop: 3 }}>Score {batch.proveedor.score ?? "—"} · {batch.items.length} ítem(s)</div></div><Badge status={batch.estado === "sent" ? "aprobada" : batch.estado === "delivery_uncertain" ? "rechazada" : "cotizando"}>{batch.estado.replaceAll("_", " ")}</Badge></div>
        {batch.estado === "delivery_uncertain" && <div style={{ display: "flex", gap: 8, padding: 10, marginBottom: 12, borderRadius: "var(--r-md)", background: "var(--st-rechazada-bg)", color: "var(--danger)", fontSize: 12.5 }}><AlertTriangle size={17} /> Revisa la carpeta Enviados de Gmail antes de hacer cualquier reintento. {batch.error_detalle}</div>}
        <div style={{ display: "grid", gap: 11 }}><Input label="Destinatario" type="email" disabled={bloqueado} value={batch.destinatario_email} onChange={e => editarLocal(batch.id, "destinatario_email", e.target.value)} /><Input label="Asunto" disabled={bloqueado} value={batch.subject} onChange={e => editarLocal(batch.id, "subject", e.target.value)} /><Textarea label="Cuerpo del correo" rows={10} value={batch.body} onChange={e => { if (!bloqueado) editarLocal(batch.id, "body", e.target.value); }} style={bloqueado ? { opacity: .65, pointerEvents: "none" } : undefined} /></div>
        <div style={{ marginTop: 14, padding: 12, borderRadius: "var(--r-md)", background: "var(--surface-2)" }}><div style={{ fontSize: 12, fontWeight: 600, color: "var(--n-700)", marginBottom: 8 }}>Ítems incluidos</div>{batch.items.map(it => <div key={it.id} style={{ display: "flex", alignItems: "center", gap: 8, padding: "5px 0", color: "var(--n-800)", fontSize: 13 }}><CategoryChip categoria={it.categoria} size={28} /><span style={{ flex: 1 }}>{it.nombre}</span><span>{Number(it.cantidad).toLocaleString("es-CL")} {it.unidad}</span></div>)}</div>
        <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, marginTop: 14 }}>{!bloqueado && <BtnSecondary disabled={ocupado === batch.id} onClick={() => void guardar(batch)}>Guardar borrador</BtnSecondary>}<BtnPrimary icon={batch.estado === "sent" ? Check : Send} disabled={bloqueado || ocupado === batch.id} onClick={() => void enviar(batch)}>{batch.estado === "sent" ? "Enviado" : ocupado === batch.id ? "Enviando…" : "Enviar por Gmail"}</BtnPrimary></div>
      </Card>; })}</div>
    </>}
  </>;
}
