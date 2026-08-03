"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { Plus, Trash2 } from "lucide-react";
import { createClient } from "@/lib/supabase/client";
import { Badge, BtnPrimary, BtnSecondary, Card, CategoryChip, FieldLabel, Input, PageHeader, SkeletonBox, CascadeWrapper, Textarea } from "@/components/ui";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const CATEGORIAS = ["electronica", "construccion", "carpinteria", "insumos_medicos", "industrial", "tuberias_valvulas", "mecanico", "electrico", "hidraulico", "neumatico", "servicio", "consumible", "otro"];

interface Capacidad { categoria: string; confianza: number; estado: string; concepto?: string; updated_at?: string; }
interface Orden { numero_oc: string; estado: string; precio_total: number; moneda: string; created_at: string; confirmada_at?: string; }
interface Proveedor { id: string; nombre: string; email?: string; rut?: string; sitio_web?: string; telefono?: string; pais?: string; notas_privadas?: string; preferido?: boolean; bloqueado?: boolean; score?: number; total_solicitudes?: number; total_respuestas?: number; total_oc_enviadas?: number; }

export default function ProveedorPage() {
  const proveedorId = useParams().id as string;
  const [userId, setUserId] = useState<string | null>(null);
  const [proveedor, setProveedor] = useState<Proveedor | null>(null);
  const [capacidades, setCapacidades] = useState<Capacidad[]>([]);
  const [ordenes, setOrdenes] = useState<Orden[]>([]);
  const [loading, setLoading] = useState(true);
  const [guardando, setGuardando] = useState(false);
  const [nuevaCategoria, setNuevaCategoria] = useState("");
  const [mensaje, setMensaje] = useState("");

  useEffect(() => { createClient().auth.getUser().then(({ data }) => { const uid = data.user?.id; if (uid) { setUserId(uid); void cargar(uid); } }); }, [proveedorId]);

  const cargar = async (uid: string) => {
    setLoading(true);
    try {
      const res = await fetch(`${API_URL}/api/proveedores/${proveedorId}?user_id=${uid}`);
      const data = await res.json(); if (!res.ok) throw new Error(data.detail);
      setProveedor(data.proveedor); setCapacidades(data.capacidades || []); setOrdenes(data.ordenes || []);
    } catch (e) { setMensaje(e instanceof Error ? e.message : "No pudimos cargar el proveedor"); }
    finally { setLoading(false); }
  };

  const guardar = async () => {
    if (!userId || !proveedor) return;
    setGuardando(true);
    try {
      const res = await fetch(`${API_URL}/api/proveedores/${proveedorId}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ user_id: userId, nombre: proveedor.nombre, rut: proveedor.rut || null, sitio_web: proveedor.sitio_web ?? "", pais: proveedor.pais ?? "", email: proveedor.email ?? "", telefono: proveedor.telefono ?? "", notas_privadas: proveedor.notas_privadas ?? "", preferido: !!proveedor.preferido, bloqueado: !!proveedor.bloqueado }) });
      const data = await res.json(); if (!res.ok) throw new Error(data.detail); setProveedor(data); setMensaje("Cambios guardados");
    } catch (e) { setMensaje(e instanceof Error ? e.message : "No pudimos guardar los cambios"); }
    finally { setGuardando(false); }
  };

  const agregarCategoria = async () => {
    if (!userId || !nuevaCategoria) return;
    const res = await fetch(`${API_URL}/api/proveedores/${proveedorId}/categorias`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ user_id: userId, categorias: [nuevaCategoria] }) });
    if (res.ok) { setNuevaCategoria(""); await cargar(userId); setMensaje("Categoría agregada"); } else setMensaje("No pudimos agregar la categoría");
  };

  const quitarCategoria = async (categoria: string) => {
    if (!userId) return;
    const res = await fetch(`${API_URL}/api/proveedores/${proveedorId}/categorias/${encodeURIComponent(categoria)}?user_id=${userId}`, { method: "DELETE" });
    if (res.ok) { setCapacidades(prev => prev.filter(c => c.categoria !== categoria)); setMensaje("Categoría quitada"); } else setMensaje("No pudimos quitar la categoría");
  };

  if (loading) return (
    <div>
      <SkeletonBox height={13} width={100} style={{ marginBottom: 14 }} />
      <SkeletonBox height={24} width={260} style={{ marginBottom: 20 }} />
      <Card padding={20} style={{ display: "flex", flexDirection: "column", gap: 14 }}>
        <CascadeWrapper>
          {Array.from({ length: 5 }).map((_, i) => (
            <div key={i}>
              <SkeletonBox height={11} width={100} style={{ marginBottom: 7 }} />
              <SkeletonBox height={38} width="100%" />
            </div>
          ))}
        </CascadeWrapper>
      </Card>
    </div>
  );
  if (!proveedor) return <Card><div style={{ color: "var(--danger)" }}>{mensaje || "Proveedor no encontrado"}</div></Card>;
  const disponibles = CATEGORIAS.filter(c => !capacidades.some(x => x.categoria === c && x.estado !== "rejected"));

  return <>
    <div style={{ marginBottom: 14 }}><Link href="/proveedores" style={{ color: "var(--n-600)", textDecoration: "none", fontSize: 13 }}>← Volver a proveedores</Link></div>
    <PageHeader eyebrow="Supplier Capability Intelligence" title={proveedor.nombre} subtitle={proveedor.email || proveedor.sitio_web || "Ficha del proveedor"} actions={<BtnPrimary disabled={guardando} onClick={() => void guardar()}>{guardando ? "Guardando…" : "Guardar cambios"}</BtnPrimary>} />
    {mensaje && <div style={{ marginBottom: 14, padding: 10, borderRadius: "var(--r-md)", background: "var(--surface-2)", color: "var(--n-700)", fontSize: 13 }}>{mensaje}</div>}

    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: 16, marginBottom: 16 }}>
      <Card><h2 style={{ margin: "0 0 16px", fontSize: 17, color: "var(--n-900)" }}>Datos del proveedor</h2><div style={{ display: "grid", gap: 12 }}>
        <Input label="Nombre" value={proveedor.nombre} onChange={e => setProveedor({ ...proveedor, nombre: e.target.value })} />
        <Input label="RUT" value={proveedor.rut || ""} onChange={e => setProveedor({ ...proveedor, rut: e.target.value })} />
        <Input label="Sitio web" value={proveedor.sitio_web || ""} onChange={e => setProveedor({ ...proveedor, sitio_web: e.target.value })} />
        <Input label="Email" value={proveedor.email || ""} onChange={e => setProveedor({ ...proveedor, email: e.target.value })} />
        <Input label="Teléfono" value={proveedor.telefono || ""} onChange={e => setProveedor({ ...proveedor, telefono: e.target.value })} />
        <Input label="País" value={proveedor.pais || ""} onChange={e => setProveedor({ ...proveedor, pais: e.target.value })} />
        <Textarea label="Notas privadas" value={proveedor.notas_privadas || ""} onChange={e => setProveedor({ ...proveedor, notas_privadas: e.target.value })} />
        <div style={{ display: "flex", gap: 18 }}>{[["preferido", "Preferido"], ["bloqueado", "Bloqueado"]].map(([key, label]) => <label key={key} style={{ display: "flex", gap: 8, fontSize: 13, color: "var(--n-700)" }}><input type="checkbox" checked={!!proveedor[key as "preferido" | "bloqueado"]} onChange={e => setProveedor({ ...proveedor, [key]: e.target.checked })} />{label}</label>)}</div>
      </div></Card>

      <Card><h2 style={{ margin: "0 0 6px", fontSize: 17, color: "var(--n-900)" }}>Categorías</h2><p style={{ margin: "0 0 16px", color: "var(--n-500)", fontSize: 13 }}>Capacidades respaldadas por evidencia para este proveedor.</p>
        <div style={{ display: "grid", gap: 8 }}>{capacidades.filter(c => c.estado !== "rejected").map(c => <div key={`${c.categoria}-${c.concepto || ""}`} style={{ display: "flex", alignItems: "center", gap: 10, padding: 10, border: "1px solid var(--n-200)", borderRadius: "var(--r-md)" }}><CategoryChip categoria={c.categoria} size={34} /><div style={{ flex: 1 }}><div style={{ fontSize: 13.5, fontWeight: 600, color: "var(--n-900)" }}>{c.categoria.replaceAll("_", " ")}</div><div style={{ fontSize: 11.5, color: "var(--n-500)" }}>{Math.round(c.confianza * 100)}% confianza · {c.estado}</div></div><BtnSecondary size="sm" icon={Trash2} title="Quitar categoría" onClick={() => void quitarCategoria(c.categoria)}>Quitar</BtnSecondary></div>)}</div>
        {capacidades.filter(c => c.estado !== "rejected").length === 0 && <div style={{ color: "var(--n-500)", fontSize: 13, padding: "10px 0" }}>Sin categorías confirmadas.</div>}
        <div style={{ marginTop: 16 }}><FieldLabel>Agregar categoría</FieldLabel><div style={{ display: "flex", gap: 8, marginTop: 7 }}><select value={nuevaCategoria} onChange={e => setNuevaCategoria(e.target.value)} style={{ flex: 1, height: 40, border: "1px solid var(--n-300)", borderRadius: "var(--r-md)", background: "var(--surface)", color: "var(--n-900)", padding: "0 10px" }}><option value="">Selecciona…</option>{disponibles.map(c => <option key={c} value={c}>{c.replaceAll("_", " ")}</option>)}</select><BtnPrimary size="sm" icon={Plus} disabled={!nuevaCategoria} onClick={() => void agregarCategoria()}>Agregar</BtnPrimary></div></div>
      </Card>
    </div>

    <Card><h2 style={{ margin: "0 0 16px", fontSize: 17, color: "var(--n-900)" }}>Órdenes de compra ({ordenes.length})</h2>{ordenes.length === 0 ? <div style={{ color: "var(--n-500)", fontSize: 13 }}>Sin órdenes de compra.</div> : <div style={{ display: "grid", gap: 8 }}>{ordenes.map(oc => <div key={oc.numero_oc} style={{ display: "flex", justifyContent: "space-between", gap: 12, padding: "10px 0", borderBottom: "1px solid var(--n-100)" }}><div><div style={{ fontWeight: 600, color: "var(--n-900)" }}>{oc.numero_oc}</div><div style={{ color: "var(--n-500)", fontSize: 12 }}>{new Date(oc.created_at).toLocaleDateString("es-CL")}</div></div><div style={{ textAlign: "right" }}><div style={{ color: "var(--n-900)" }}>{oc.moneda} {Number(oc.precio_total).toLocaleString("es-CL")}</div><Badge status={oc.estado}>{oc.estado.replaceAll("_", " ")}</Badge></div></div>)}</div>}</Card>
  </>;
}
