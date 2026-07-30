"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { AlertTriangle, ArrowLeft, Check, Mail, ShieldCheck, X } from "lucide-react";
import { createClient } from "@/lib/supabase/client";
import { Badge, BtnPrimary, BtnSecondary, Card, CategoryChip, EmptyState, PageHeader, Spinner } from "@/components/ui";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface ItemMatriz { cotizacion_id: string; nombre: string; cantidad: number; unidad: string; categoria: string; confianza: number; estado: string; ranking: number; explicacion: string; seleccionado: boolean; }
interface ProveedorMatriz { proveedor_id: string; nombre: string; score: number; preferido: boolean; contacto: { id: string | null; nombre?: string; email?: string; cargo?: string } | null; items: ItemMatriz[]; }
interface ItemResumen { cotizacion_id: string; nombre: string; cantidad: number; unidad: string; categoria: string; n_candidatos: number; }
interface Matriz { items: ItemResumen[]; proveedores: ProveedorMatriz[]; revisado: boolean; }

export default function ProveedoresConfianzaPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [userId, setUserId] = useState<string | null>(null);
  const [matriz, setMatriz] = useState<Matriz | null>(null);
  const [seleccion, setSeleccion] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(true);
  const [guardando, setGuardando] = useState(false);
  const [preparando, setPreparando] = useState(false);
  const [mensaje, setMensaje] = useState("");

  const cargar = useCallback(async (uid: string) => {
    setLoading(true);
    try {
      const res = await fetch(`${API_URL}/api/listas/${id}/proveedores-confianza?user_id=${uid}`);
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail);
      setMatriz(data);
      setSeleccion(new Set(data.proveedores.flatMap((p: ProveedorMatriz) => p.items.filter(it => it.seleccionado).map(it => `${p.proveedor_id}:${it.cotizacion_id}`))));
    } catch (e) { setMensaje(e instanceof Error ? e.message : "No pudimos construir la matriz"); }
    finally { setLoading(false); }
  }, [id]);

  useEffect(() => { createClient().auth.getUser().then(({ data }) => { if (data.user) { setUserId(data.user.id); void cargar(data.user.id); } }); }, [cargar]);

  const alternar = (proveedorId: string, cotizacionId: string) => {
    const key = `${proveedorId}:${cotizacionId}`;
    setSeleccion(prev => { const next = new Set(prev); next.has(key) ? next.delete(key) : next.add(key); return next; });
  };

  const cobertura = useMemo(() => {
    const c: Record<string, number> = {};
    matriz?.items.forEach(it => { c[it.cotizacion_id] = 0; });
    seleccion.forEach(key => { const cid = key.split(":")[1]; c[cid] = (c[cid] || 0) + 1; });
    return c;
  }, [matriz, seleccion]);

  const guardar = async (): Promise<boolean> => {
    if (!userId || !matriz) return false;
    setGuardando(true);
    const selecciones = matriz.proveedores.map(p => ({
      proveedor_id: p.proveedor_id,
      contacto_id: p.contacto?.id || null,
      cotizacion_ids: p.items.filter(it => seleccion.has(`${p.proveedor_id}:${it.cotizacion_id}`)).map(it => it.cotizacion_id),
    })).filter(s => s.cotizacion_ids.length);
    try {
      const res = await fetch(`${API_URL}/api/listas/${id}/proveedores-confianza`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ user_id: userId, selecciones }) });
      const data = await res.json(); if (!res.ok) throw new Error(data.detail);
      setMensaje("Matriz guardada. Queda lista para preparar los correos en la Fase 5.");
      return true;
    } catch (e) { setMensaje(e instanceof Error ? e.message : "No pudimos guardar la matriz"); return false; }
    finally { setGuardando(false); }
  };

  const prepararCorreos = async () => {
    if (!userId) return;
    setPreparando(true);
    try {
      if (!(await guardar())) return;
      const res = await fetch(`${API_URL}/api/listas/${id}/rfq/preparar`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ user_id: userId }) });
      const data = await res.json(); if (!res.ok) throw new Error(data.detail);
      router.push(`/listas/${id}/rfq`);
    } catch (e) { setMensaje(e instanceof Error ? e.message : "No pudimos preparar los correos"); }
    finally { setPreparando(false); }
  };

  if (loading) return <Spinner label="Analizando proveedores conocidos…" />;
  if (!matriz) return <Card><EmptyState icon={AlertTriangle} title="No pudimos construir la matriz" description={mensaje} /></Card>;

  const cubiertos = matriz.items.filter(it => cobertura[it.cotizacion_id] > 0).length;
  const proveedoresSeleccionados = matriz.proveedores.filter(p => p.items.some(it => seleccion.has(`${p.proveedor_id}:${it.cotizacion_id}`))).length;

  return <>
    <Link href={`/listas/${id}`} style={{ display: "inline-flex", gap: 6, alignItems: "center", color: "var(--n-600)", textDecoration: "none", fontSize: 13, marginBottom: 14 }}><ArrowLeft size={15} /> Volver a la lista</Link>
    <PageHeader eyebrow="Cotización a proveedores de confianza" title="Matriz ítem–proveedor" subtitle="Revisa qué proveedor recibirá cada ítem. Nada se enviará todavía." />
    {mensaje && <div style={{ padding: 11, marginBottom: 14, borderRadius: "var(--r-md)", background: "var(--surface-2)", color: "var(--n-700)", fontSize: 13 }}>{mensaje}</div>}

    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))", gap: 10, marginBottom: 18 }}>
      {[["Ítems totales", matriz.items.length], ["Cubiertos", cubiertos], ["Sin proveedor", matriz.items.length - cubiertos], ["Proveedores", proveedoresSeleccionados], ["Solicitudes", seleccion.size]].map(([label, val]) => <Card key={String(label)} padding={14}><div style={{ fontSize: 12, color: "var(--n-500)" }}>{label}</div><div style={{ fontSize: 23, fontWeight: 600, color: label === "Sin proveedor" && Number(val) > 0 ? "var(--danger)" : "var(--n-900)", marginTop: 4 }}>{val}</div></Card>)}
    </div>

    {cubiertos < matriz.items.length && <Card style={{ marginBottom: 16, background: "var(--st-cotizando-bg)", borderColor: "var(--st-cotizando-fg)" }}><div style={{ display: "flex", gap: 10, alignItems: "flex-start" }}><AlertTriangle size={19} color="var(--st-cotizando-fg)" /><div><strong style={{ color: "var(--n-900)" }}>{matriz.items.length - cubiertos} ítem(s) sin cobertura</strong><div style={{ color: "var(--n-600)", fontSize: 13, marginTop: 3 }}>Podrás buscar proveedores externos para ellos mediante la búsqueda complementaria. Esto no bloquea guardar la matriz.</div></div></div></Card>}

    <Card style={{ marginBottom: 18 }}><h2 style={{ margin: "0 0 12px", fontSize: 16, color: "var(--n-900)" }}>Cobertura por ítem</h2><div style={{ display: "grid", gap: 8 }}>{matriz.items.map(it => { const n = cobertura[it.cotizacion_id] || 0; const low = n === 1; return <div key={it.cotizacion_id} style={{ display: "flex", alignItems: "center", gap: 10, padding: 9, borderRadius: "var(--r-md)", background: n ? (low ? "var(--st-cotizando-bg)" : "var(--st-aprobada-bg)") : "var(--st-rechazada-bg)" }}>{n ? (low ? <AlertTriangle size={17} /> : <Check size={17} />) : <X size={17} />}<CategoryChip categoria={it.categoria} size={30} /><div style={{ flex: 1 }}><div style={{ fontSize: 13.5, fontWeight: 600, color: "var(--n-900)" }}>{it.nombre}</div><div style={{ fontSize: 12, color: "var(--n-600)" }}>{it.cantidad} {it.unidad} · {it.categoria.replaceAll("_", " ")}</div></div><strong style={{ fontSize: 12.5, color: "var(--n-700)" }}>{n === 0 ? "Sin proveedor" : n === 1 ? "1 proveedor" : `${n} proveedores`}</strong></div>; })}</div></Card>

    {matriz.proveedores.length === 0 ? <Card><EmptyState icon={ShieldCheck} title="Aún no hay proveedores compatibles" description="Agrega categorías a tus proveedores para que Baiyer pueda relacionarlos con los ítems de esta lista." action={<Link href="/proveedores" style={{ textDecoration: "none" }}><BtnPrimary>Gestionar proveedores</BtnPrimary></Link>} /></Card> : <div style={{ display: "grid", gap: 14 }}>{matriz.proveedores.map(p => <Card key={p.proveedor_id}>
      <div style={{ display: "flex", justifyContent: "space-between", gap: 12, flexWrap: "wrap", marginBottom: 12 }}><div><div style={{ display: "flex", alignItems: "center", gap: 8 }}><Link href={`/proveedores/${p.proveedor_id}`} style={{ color: "var(--n-900)", fontWeight: 600, textDecoration: "none", fontSize: 16 }}>{p.nombre}</Link>{p.preferido && <Badge status="cotizando">Preferido</Badge>}</div><div style={{ display: "flex", alignItems: "center", gap: 6, color: "var(--n-500)", fontSize: 12.5, marginTop: 4 }}><Mail size={14} /> {p.contacto?.email || "Sin correo configurado"}</div></div><div style={{ color: "var(--n-600)", fontSize: 13 }}>Score {p.score}</div></div>
      <div style={{ display: "grid", gap: 8 }}>{p.items.map(it => { const checked = seleccion.has(`${p.proveedor_id}:${it.cotizacion_id}`); return <label key={it.cotizacion_id} style={{ display: "flex", gap: 10, alignItems: "flex-start", padding: 10, border: `1px solid ${checked ? "var(--brand-200)" : "var(--n-200)"}`, borderRadius: "var(--r-md)", background: checked ? "var(--brand-50)" : "var(--surface)", cursor: "pointer" }}><input type="checkbox" checked={checked} onChange={() => alternar(p.proveedor_id, it.cotizacion_id)} style={{ marginTop: 4 }} /><CategoryChip categoria={it.categoria} size={34} /><div style={{ flex: 1 }}><div style={{ fontWeight: 600, color: "var(--n-900)", fontSize: 13.5 }}>{it.nombre} · {it.cantidad} {it.unidad}</div><div style={{ color: "var(--n-600)", fontSize: 12, marginTop: 3 }}>{it.explicacion}</div></div><div style={{ textAlign: "right" }}><strong style={{ color: it.confianza >= .8 ? "var(--success)" : "var(--warning)", fontSize: 13 }}>{Math.round(it.confianza * 100)}%</strong><div style={{ color: "var(--n-500)", fontSize: 11.5 }}>{it.estado}</div></div></label>; })}</div>
    </Card>)}</div>}

    <div style={{ display: "flex", justifyContent: "flex-end", gap: 9, marginTop: 18, flexWrap: "wrap" }}><BtnSecondary onClick={() => router.push(`/listas/${id}`)}>Volver a la lista</BtnSecondary>{matriz.items[0] && <BtnSecondary onClick={() => router.push(`/cotizar/${matriz.items[0].cotizacion_id}/resultados?lista=${id}`)}>Continuar a comparar ofertas</BtnSecondary>}<BtnSecondary disabled={guardando} onClick={() => void guardar()}>{guardando ? "Guardando…" : "Guardar matriz"}</BtnSecondary><BtnPrimary disabled={preparando || seleccion.size === 0} onClick={() => void prepararCorreos()}>{preparando ? "Preparando…" : "Preparar correos"}</BtnPrimary></div>
  </>;
}
