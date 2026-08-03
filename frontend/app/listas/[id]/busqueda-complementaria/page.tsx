"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { AlertTriangle, ArrowLeft, Check, Search } from "lucide-react";
import { createClient } from "@/lib/supabase/client";
import { Badge, BtnPrimary, BtnSecondary, Card, CategoryChip, EmptyState, PageHeader, SkeletonBox, CascadeWrapper } from "@/components/ui";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
interface Item { cotizacion_id: string; nombre: string; cantidad: number; unidad: string; categoria: string; proveedores: { proveedor_id: string; nombre: string }[]; n_proveedores: number; rfq_enviada: boolean; }

export default function BusquedaComplementariaPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [userId, setUserId] = useState<string | null>(null);
  const [faltantes, setFaltantes] = useState<Item[]>([]);
  const [cubiertos, setCubiertos] = useState<Item[]>([]);
  const [loading, setLoading] = useState(true);
  const [abriendo, setAbriendo] = useState<string | null>(null);
  const [mensaje, setMensaje] = useState("");

  const cargar = useCallback(async (uid: string) => {
    try {
      const res = await fetch(`${API_URL}/api/listas/${id}/busqueda-complementaria?user_id=${uid}`);
      const data = await res.json(); if (!res.ok) throw new Error(data.detail);
      setFaltantes(data.requieren_proveedores || []); setCubiertos(data.ya_cubiertos || []);
    } catch (e) { setMensaje(e instanceof Error ? e.message : "No pudimos cargar la cobertura"); }
    finally { setLoading(false); }
  }, [id]);
  useEffect(() => { createClient().auth.getUser().then(({ data }) => { if (data.user) { setUserId(data.user.id); void cargar(data.user.id); } }); }, [cargar]);

  const buscar = async (item: Item, alternativa = false) => {
    if (!userId) return;
    setAbriendo(item.cotizacion_id);
    let padre = "";
    try {
      const comentario = alternativa ? "Buscar más alternativas para un ítem ya cubierto" : "Faltan proveedores de confianza; iniciar búsqueda complementaria";
      const res = await fetch(`${API_URL}/api/buscar/sesiones/complementaria/preparar`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ user_id: userId, cotizacion_id: item.cotizacion_id, lista_proyecto_id: id, comentario }) });
      if (res.ok) padre = (await res.json()).session_padre_id || "";
    } catch { /* la búsqueda puede continuar aunque falle la telemetría */ }
    const qs = new URLSearchParams({ lista: id, modo: "expanded", origen: alternativa ? "alternativa" : "sin_cobertura" });
    if (padre) qs.set("session_padre", padre);
    router.push(`/cotizar/${item.cotizacion_id}/resultados?${qs.toString()}`);
  };

  if (loading) return (
    <div>
      <SkeletonBox height={13} width={140} style={{ marginBottom: 14 }} />
      <SkeletonBox height={20} width={260} style={{ marginBottom: 8 }} />
      <SkeletonBox height={13} width={420} style={{ marginBottom: 22 }} />
      <div style={{ display: "grid", gap: 9 }}>
        <CascadeWrapper>
          {Array.from({ length: 3 }).map((_, i) => (
            <Card key={i} style={{ display: "flex", alignItems: "center", gap: 11, flexWrap: "wrap" }}>
              <SkeletonBox width={34} height={34} radius="var(--r-md)" />
              <div style={{ flex: 1, minWidth: 180, display: "flex", flexDirection: "column", gap: 6 }}>
                <SkeletonBox height={14} width="40%" />
                <SkeletonBox height={11} width="60%" />
              </div>
              <SkeletonBox width={140} height={32} />
            </Card>
          ))}
        </CascadeWrapper>
      </div>
    </div>
  );
  return <>
    <Link href={`/listas/${id}`} style={{ display: "inline-flex", gap: 6, alignItems: "center", color: "var(--n-600)", textDecoration: "none", fontSize: 13, marginBottom: 14 }}><ArrowLeft size={15} /> Volver a la lista</Link>
    <PageHeader eyebrow="Búsqueda complementaria" title="Completar cobertura" subtitle="Primero buscaremos proveedores para los ítems que aún no están cubiertos. También puedes buscar alternativas para los ya asignados." />
    {mensaje && <div style={{ padding: 11, marginBottom: 14, borderRadius: "var(--r-md)", background: "var(--st-rechazada-bg)", color: "var(--danger)", fontSize: 13 }}>{mensaje}</div>}

    <section style={{ marginBottom: 22 }}><h2 style={{ fontSize: 17, color: "var(--n-900)", margin: "0 0 5px" }}>Requieren proveedores</h2><p style={{ color: "var(--n-500)", fontSize: 13, margin: "0 0 12px" }}>Estos ítems no se incluyeron en ningún correo a proveedores de confianza.</p>
      {faltantes.length === 0 ? <Card><EmptyState icon={Check} title="Todos los ítems tienen cobertura" description="Puedes buscar alternativas opcionales más abajo." /></Card> : <div style={{ display: "grid", gap: 9 }}>{faltantes.map(item => <Card key={item.cotizacion_id} style={{ display: "flex", alignItems: "center", gap: 11, flexWrap: "wrap", background: "var(--st-rechazada-bg)" }}><AlertTriangle size={18} color="var(--danger)" /><CategoryChip categoria={item.categoria} size={34} /><div style={{ flex: 1, minWidth: 180 }}><div style={{ fontWeight: 600, color: "var(--n-900)" }}>{item.nombre}</div><div style={{ color: "var(--n-600)", fontSize: 12.5 }}>{item.cantidad} {item.unidad} · {item.categoria.replaceAll("_", " ")}</div></div><BtnPrimary icon={Search} disabled={abriendo === item.cotizacion_id} onClick={() => void buscar(item)}>{abriendo === item.cotizacion_id ? "Abriendo…" : "Buscar proveedores"}</BtnPrimary></Card>)}</div>}
    </section>

    <section><h2 style={{ fontSize: 17, color: "var(--n-900)", margin: "0 0 5px" }}>Ya cubiertos</h2><p style={{ color: "var(--n-500)", fontSize: 13, margin: "0 0 12px" }}>No repetiremos su búsqueda automáticamente.</p>
      <div style={{ display: "grid", gap: 9 }}>{cubiertos.map(item => <Card key={item.cotizacion_id} style={{ display: "flex", alignItems: "center", gap: 11, flexWrap: "wrap" }}><Check size={18} color="var(--success)" /><CategoryChip categoria={item.categoria} size={34} /><div style={{ flex: 1, minWidth: 180 }}><div style={{ display: "flex", alignItems: "center", gap: 7 }}><strong style={{ color: "var(--n-900)" }}>{item.nombre}</strong>{item.rfq_enviada && <Badge status="aprobada">RFQ enviada</Badge>}</div><div style={{ color: "var(--n-600)", fontSize: 12.5, marginTop: 3 }}>{item.proveedores.map(p => p.nombre).join(", ")}</div></div><BtnSecondary icon={Search} disabled={abriendo === item.cotizacion_id} onClick={() => void buscar(item, true)}>Buscar más alternativas</BtnSecondary></Card>)}</div>
    </section>
  </>;
}
