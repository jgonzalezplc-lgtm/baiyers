"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Building2, Plus, Search, Upload } from "lucide-react";
import { createClient } from "@/lib/supabase/client";
import { authFetch } from "@/lib/authFetch";
import { BtnPrimary, BtnSecondary, Card, CategoryChip, EmptyState, FieldLabel, Input, Modal, PageHeader, Textarea, SkeletonCard, CascadeWrapper } from "@/components/ui";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const CATEGORIAS = [
  ["electronica", "Electrónica"], ["construccion", "Construcción"], ["carpinteria", "Carpintería"],
  ["insumos_medicos", "Insumos médicos"], ["industrial", "Industrial"], ["tuberias_valvulas", "Tuberías y válvulas"],
  ["mecanico", "Mecánico"], ["electrico", "Eléctrico"], ["hidraulico", "Hidráulico"],
  ["neumatico", "Neumático"], ["servicio", "Servicios"], ["consumible", "Consumibles"], ["otro", "Otro"],
] as const;

interface Proveedor {
  id: string; nombre: string; email?: string; score: number; categoria_score: string;
  total_solicitudes: number; total_respuestas: number; tasa_respuesta: number;
  bloqueado: boolean; preferido?: boolean; sitio_web?: string;
}

interface Formulario {
  nombre: string; rut: string; sitio_web: string; pais: string; email: string;
  contacto_nombre: string; telefono: string; notas_privadas: string;
  preferido: boolean; bloqueado: boolean; categorias: string[];
}

const FORM_INICIAL: Formulario = {
  nombre: "", rut: "", sitio_web: "", pais: "CL", email: "", contacto_nombre: "",
  telefono: "", notas_privadas: "", preferido: false, bloqueado: false, categorias: [],
};

export default function ProveedoresPage() {
  const [proveedores, setProveedores] = useState<Proveedor[]>([]);
  const [loading, setLoading] = useState(true);
  const [userId, setUserId] = useState<string | null>(null);
  const [toast, setToast] = useState("");
  const [filtro, setFiltro] = useState<"activos" | "bloqueados">("activos");
  const [modal, setModal] = useState(false);
  const [form, setForm] = useState<Formulario>(FORM_INICIAL);
  const [investigando, setInvestigando] = useState(false);
  const [guardando, setGuardando] = useState(false);
  const [sugerencia, setSugerencia] = useState("");

  useEffect(() => {
    createClient().auth.getUser().then(({ data }) => {
      if (data.user) { setUserId(data.user.id); void cargar(data.user.id); }
    });
  }, []);

  const mostrarToast = (mensaje: string) => {
    setToast(mensaje);
    window.setTimeout(() => setToast(""), 3000);
  };

  const cargar = async (uid: string) => {
    setLoading(true);
    try {
      const res = await authFetch(`${API_URL}/api/suppliers`);
      if (!res.ok) throw new Error();
      setProveedores(await res.json());
    } catch { mostrarToast("No pudimos cargar los proveedores"); }
    finally { setLoading(false); }
  };

  const alternarCategoria = (categoria: string) => setForm(prev => ({
    ...prev,
    categorias: prev.categorias.includes(categoria)
      ? prev.categorias.filter(c => c !== categoria)
      : [...prev.categorias, categoria],
  }));

  const investigar = async () => {
    if (!form.nombre.trim() && !form.sitio_web.trim()) return mostrarToast("Ingresa un nombre o sitio web");
    setInvestigando(true);
    try {
      const res = await authFetch(`${API_URL}/api/proveedores/investigar`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ nombre: form.nombre, sitio_web: form.sitio_web }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail);
      setForm(prev => ({
        ...prev,
        nombre: data.razon_social || prev.nombre,
        rut: data.rut || prev.rut,
        sitio_web: data.sitio_web || prev.sitio_web,
        pais: data.pais || prev.pais,
        categorias: Array.isArray(data.categorias) ? data.categorias : prev.categorias,
      }));
      setSugerencia([data.descripcion, data.territorio && `Cobertura: ${data.territorio}`, data.confianza && `Confianza: ${data.confianza}`].filter(Boolean).join(" · "));
    } catch (e) { mostrarToast(e instanceof Error ? e.message : "No pudimos investigar el proveedor"); }
    finally { setInvestigando(false); }
  };

  const guardar = async () => {
    if (!userId || !form.nombre.trim()) return mostrarToast("El nombre es obligatorio");
    setGuardando(true);
    try {
      const res = await authFetch(`${API_URL}/api/proveedores`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(form),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail);
      setModal(false); setForm(FORM_INICIAL); setSugerencia("");
      await cargar(userId); mostrarToast("Proveedor guardado");
    } catch (e) { mostrarToast(e instanceof Error ? e.message : "No pudimos guardar el proveedor"); }
    finally { setGuardando(false); }
  };

  const alternarBloqueo = async (p: Proveedor) => {
    if (!userId) return;
    const accion = p.bloqueado ? "desbloquear" : "bloquear";
    try {
      const res = await authFetch(`${API_URL}/api/suppliers/${p.id}/${accion}`, { method: "POST" });
      if (!res.ok) throw new Error();
      setProveedores(prev => prev.map(x => x.id === p.id ? { ...x, bloqueado: !x.bloqueado } : x));
      mostrarToast(p.bloqueado ? "Proveedor desbloqueado" : "Proveedor bloqueado");
    } catch { mostrarToast("No pudimos actualizar el proveedor"); }
  };

  const visibles = proveedores.filter(p => filtro === "bloqueados" ? p.bloqueado : !p.bloqueado);

  return (
    <>
      {toast && <div style={{ position: "fixed", top: 20, right: 20, zIndex: 300, background: "var(--n-900)", color: "var(--surface)", padding: "10px 14px", borderRadius: "var(--r-md)", fontSize: 13 }}>{toast}</div>}
      <PageHeader eyebrow="Red de abastecimiento" title="Proveedores" subtitle="Administra tus proveedores y el conocimiento sobre lo que pueden suministrar."
        actions={<><Link href="/proveedores/importar" style={{ textDecoration: "none" }}><BtnSecondary icon={Upload}>Importar Excel</BtnSecondary></Link><BtnPrimary icon={Plus} onClick={() => setModal(true)}>Agregar proveedor</BtnPrimary></>} />

      <div style={{ display: "flex", gap: 8, marginBottom: 16 }}>
        <BtnSecondary size="sm" onClick={() => setFiltro("activos")} style={filtro === "activos" ? { borderColor: "var(--brand)", color: "var(--brand)" } : undefined}>Activos</BtnSecondary>
        <BtnSecondary size="sm" onClick={() => setFiltro("bloqueados")} style={filtro === "bloqueados" ? { borderColor: "var(--brand)", color: "var(--brand)" } : undefined}>Bloqueados</BtnSecondary>
      </div>

      {loading ? (
        <div style={{ display: "grid", gap: 10 }}>
          <CascadeWrapper>
            {Array.from({ length: 4 }).map((_, i) => <SkeletonCard key={i} />)}
          </CascadeWrapper>
        </div>
      ) : visibles.length === 0 ? (
        <Card padding={0}><EmptyState icon={Building2} title={filtro === "bloqueados" ? "No hay proveedores bloqueados" : "Aún no tienes proveedores"} description="Agrégalos manualmente o importa tu directorio desde Excel." action={filtro === "activos" ? <BtnPrimary icon={Plus} onClick={() => setModal(true)}>Agregar proveedor</BtnPrimary> : undefined} /></Card>
      ) : (
        <div style={{ display: "grid", gap: 10 }}>
          {visibles.map(p => <Card key={p.id} style={{ display: "flex", alignItems: "center", gap: 14, flexWrap: "wrap" }}>
            <CategoryChip categoria={p.categoria_score} />
            <div style={{ flex: 1, minWidth: 180 }}>
              <Link href={`/proveedores/${p.id}`} style={{ fontSize: 15, fontWeight: 600, color: "var(--n-900)", textDecoration: "none" }}>{p.nombre}</Link>
              <div style={{ fontSize: 12.5, color: "var(--n-500)", marginTop: 3 }}>{p.email || p.sitio_web || "Sin datos de contacto"}</div>
            </div>
            {p.preferido && <span style={{ fontSize: 12, color: "var(--warning)", fontWeight: 600 }}>Preferido</span>}
            <div style={{ textAlign: "right", minWidth: 90 }}><div style={{ fontSize: 18, fontWeight: 600, color: "var(--n-900)" }}>{p.score ?? 0}</div><div style={{ fontSize: 11.5, color: "var(--n-500)" }}>score · {p.tasa_respuesta ?? 0}% respuesta</div></div>
            <BtnSecondary size="sm" onClick={() => void alternarBloqueo(p)}>{p.bloqueado ? "Desbloquear" : "Bloquear"}</BtnSecondary>
          </Card>)}
        </div>
      )}

      <Modal open={modal} onClose={() => setModal(false)} title="Agregar proveedor" icon={Building2} width={720}
        footer={<><BtnSecondary onClick={() => setModal(false)}>Cancelar</BtnSecondary><BtnPrimary disabled={guardando || !form.nombre.trim()} onClick={() => void guardar()}>{guardando ? "Guardando…" : "Guardar proveedor"}</BtnPrimary></>}>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: 14 }}>
          <Input label="Nombre *" value={form.nombre} onChange={e => setForm({ ...form, nombre: e.target.value })} />
          <Input label="RUT" value={form.rut} onChange={e => setForm({ ...form, rut: e.target.value })} placeholder="76.123.456-7" />
          <Input label="Sitio web" value={form.sitio_web} onChange={e => setForm({ ...form, sitio_web: e.target.value })} placeholder="https://proveedor.cl" />
          <Input label="País" value={form.pais} onChange={e => setForm({ ...form, pais: e.target.value })} />
          <Input label="Email" type="email" value={form.email} onChange={e => setForm({ ...form, email: e.target.value })} />
          <Input label="Nombre del contacto" value={form.contacto_nombre} onChange={e => setForm({ ...form, contacto_nombre: e.target.value })} />
          <Input label="Teléfono" value={form.telefono} onChange={e => setForm({ ...form, telefono: e.target.value })} />
        </div>
        <div style={{ marginTop: 16 }}><Textarea label="Notas privadas" value={form.notas_privadas} onChange={e => setForm({ ...form, notas_privadas: e.target.value })} /></div>
        <div style={{ display: "flex", alignItems: "center", gap: 10, margin: "16px 0" }}><BtnSecondary icon={Search} disabled={investigando} onClick={() => void investigar()}>{investigando ? "Investigando…" : "Investigar y recomendar categorías"}</BtnSecondary><span style={{ fontSize: 12.5, color: "var(--n-500)" }}>Nada se guarda hasta que confirmes.</span></div>
        {sugerencia && <div style={{ padding: 12, background: "var(--surface-2)", borderRadius: "var(--r-md)", color: "var(--n-600)", fontSize: 13, marginBottom: 14 }}>{sugerencia}</div>}
        <FieldLabel>Categorías que abastece</FieldLabel>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginTop: 8 }}>{CATEGORIAS.map(([key, label]) => <button key={key} type="button" onClick={() => alternarCategoria(key)} style={{ padding: "7px 10px", borderRadius: "var(--r-pill)", border: `1px solid ${form.categorias.includes(key) ? "var(--brand)" : "var(--n-300)"}`, background: form.categorias.includes(key) ? "var(--brand-50)" : "var(--surface)", color: form.categorias.includes(key) ? "var(--brand)" : "var(--n-700)", cursor: "pointer", fontSize: 12.5 }}>{label}</button>)}</div>
        <div style={{ display: "flex", gap: 20, marginTop: 16 }}>{[["preferido", "Proveedor preferido"], ["bloqueado", "Bloqueado"]].map(([key, label]) => <label key={key} style={{ display: "flex", gap: 8, alignItems: "center", fontSize: 13, color: "var(--n-700)" }}><input type="checkbox" checked={form[key as "preferido" | "bloqueado"]} onChange={e => setForm({ ...form, [key]: e.target.checked })} />{label}</label>)}</div>
      </Modal>
    </>
  );
}
