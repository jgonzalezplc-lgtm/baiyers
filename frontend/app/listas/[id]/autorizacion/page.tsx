"use client";
import { useEffect, useMemo, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { ArrowLeft, Send } from "lucide-react";
import { createClient } from "@/lib/supabase/client";
import { BtnPrimary, BtnSecondary, Card, Input, Spinner } from "@/components/ui";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const fmtCLP = (n: number) => `$${Math.round(n).toLocaleString("es-CL")}`;
type Definitivo = { proveedor?: string; precio_clp?: number | null; url?: string | null };
type Item = { cotizacion_id: string; nombre: string; cantidad: number; definitivo: Definitivo | null };
type Lista = { id: string; nombre: string; items: Item[]; justificaciones?: Record<string, string> };

export default function AutorizarListaPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [lista, setLista] = useState<Lista | null>(null);
  const [userId, setUserId] = useState("");
  const [meta, setMeta] = useState<Record<string, string>>({});
  const [email, setEmail] = useState("");
  const [justificaciones, setJustificaciones] = useState<Record<string, string>>({});
  const [enviando, setEnviando] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => { createClient().auth.getUser().then(async ({ data }) => {
    const u = data.user; if (!u) return router.replace("/login");
    setUserId(u.id); const m = u.user_metadata as Record<string, string>; setMeta(m); setEmail(m.autorizador_email || "");
    const r = await fetch(`${API_URL}/api/listas/${id}?user_id=${u.id}`);
    if (r.ok) { const d = await r.json(); setLista(d); const automaticas = JSON.parse(sessionStorage.getItem(`baiyer:justificaciones:${id}`) || "{}"); setJustificaciones({ ...automaticas, ...(d.justificaciones || {}) }); sessionStorage.removeItem(`baiyer:justificaciones:${id}`); }
    else setError("No se pudo cargar la lista.");
  }); }, [id, router]);

  const definitivos = useMemo(() => lista?.items.filter(i => i.definitivo) || [], [lista]);
  const total = definitivos.reduce((s, i) => s + (i.definitivo?.precio_clp || 0) * (i.cantidad || 1), 0);
  const enviar = async () => {
    if (!lista || !userId || !email.trim()) return;
    setEnviando(true); setError("");
    try {
      const r = await fetch(`${API_URL}/api/listas/${id}/solicitar-aprobacion`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ user_id: userId, aprobador_email: email.trim(), justificaciones, nombre_solicitante: meta.nombre_usuario || "", empresa: meta.empresa || "" }) });
      const d = await r.json(); if (!r.ok) throw new Error(d.detail || "No se pudo crear la solicitud");
      const lineas = definitivos.map(i => `• ${i.nombre} ×${i.cantidad}: ${i.definitivo?.proveedor || "—"} — ${i.definitivo?.precio_clp != null ? fmtCLP(i.definitivo.precio_clp * i.cantidad) : "—"}\n  Link: ${i.definitivo?.url || "—"}\n  Motivo: ${justificaciones[i.cotizacion_id] || "—"}`).join("\n\n");
      const asunto = encodeURIComponent(`Autorización requerida: ${lista.nombre}`);
      const cuerpo = encodeURIComponent(`Hola,\n\nSe solicita autorización para la lista: ${lista.nombre}\n\n${lineas}\n\nTotal: ${fmtCLP(total)}\n\nRevisa las alternativas y aprueba o rechaza cada ítem aquí:\n${d.magic_link_aprobar}\n\nEl enlace expira el ${new Date(d.expira_at).toLocaleDateString("es-CL")}.`);
      window.open(`mailto:${email.trim()}?subject=${asunto}&body=${cuerpo}`, "_self");
      router.replace(`/listas/${id}`);
    } catch (e) { setError(e instanceof Error ? e.message : "Error al enviar"); }
    finally { setEnviando(false); }
  };
  if (!lista) return <Spinner label={error || "Cargando autorización…"} />;
  return <div style={{ maxWidth: 820, margin: "0 auto" }}>
    <button onClick={() => router.back()} style={{ border: 0, background: "none", color: "var(--n-600)", cursor: "pointer", display: "inline-flex", gap: 6, alignItems: "center", marginBottom: 16 }}><ArrowLeft size={16} /> Volver a la selección</button>
    <h1 style={{ margin: "0 0 6px", fontSize: 26 }}>Solicitar autorización</h1>
    <p style={{ color: "var(--n-600)", margin: "0 0 20px" }}>Lista: <strong>{lista.nombre}</strong>. Explica por qué se eligió cada alternativa antes de enviarla.</p>
    <Card padding={18} style={{ marginBottom: 16 }}><Input label="Email del autorizador" type="email" value={email} onChange={e => setEmail(e.target.value)} placeholder="jefe@empresa.cl" /></Card>
    {definitivos.map(item => <Card key={item.cotizacion_id} padding={18} style={{ marginBottom: 12 }}>
      <div style={{ fontSize: 15, fontWeight: 700 }}>{item.nombre} <span style={{ color: "var(--n-500)", fontWeight: 400 }}>× {item.cantidad}</span></div>
      <div style={{ margin: "8px 0", fontSize: 14 }}>{item.definitivo?.proveedor || "—"} · <a href={item.definitivo?.url || "#"} target="_blank" rel="noreferrer">Ver producto ↗</a> · <strong>{item.definitivo?.precio_clp != null ? fmtCLP(item.definitivo.precio_clp * item.cantidad) : "—"}</strong></div>
      <Input label="Justificación" value={justificaciones[item.cotizacion_id] || ""} onChange={e => setJustificaciones(j => ({ ...j, [item.cotizacion_id]: e.target.value }))} placeholder="Ej: mejor precio, entrega rápida, proveedor homologado…" />
    </Card>)}
    <Card padding={18} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 16 }}><strong>Total: {fmtCLP(total)}</strong><div style={{ display: "flex", gap: 10 }}><BtnSecondary onClick={() => router.back()}>Cancelar</BtnSecondary><BtnPrimary onClick={enviar} disabled={!email.trim() || enviando} icon={Send}>{enviando ? "Preparando…" : "Enviar al autorizador"}</BtnPrimary></div></Card>
    {error && <p style={{ color: "var(--danger)", marginTop: 12 }}>{error}</p>}
  </div>;
}
