"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import dynamic from "next/dynamic";
import {
  ArrowLeft, Check, Send, Wand2, Camera, ShoppingBag, Mail, ExternalLink,
  Search, ChevronRight, Cpu, Building2, Hammer, HeartPulse, Factory,
  Wrench, Zap, Droplets, Wind, Briefcase, Package, Boxes, GitBranch,
} from "lucide-react";
import { createClient } from "@/lib/supabase/client";
import { authFetch } from "@/lib/authFetch";
import { Card, Badge, BtnPrimary, BtnSecondary, SummaryPanel, Input, SkeletonBox, SkeletonText, CascadeWrapper } from "@/components/ui";
import { useMiembrosOrg } from "@/lib/useMiembrosOrg";

const InformeLista = dynamic(() => import("@/components/InformeLista"), { ssr: false });
const OCModal = dynamic(() => import("@/components/OCModal"), { ssr: false });

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export interface ComparadoLista {
  resultado_id: string;
  proveedor: string | null;
  fuente: string | null;
  precio: number | null;
  moneda: string;
  precio_cotizado: number | null;
  plazo_entrega: string | null;
  ubicacion: string | null;
  contacto: string | null;
  url: string;
  descripcion: string | null;
  origen?: "sugerido" | "proveedor" | "buscado_web";
}

export interface ProveedorRecomendado {
  id: string;
  nombre: string;
  email: string | null;
  sitio_web?: string | null;
  telefono?: string | null;
  origen: "sugerido" | "proveedor";
  origen_label: string;
  match_label: string;
  match_score?: number;
  categorias?: string[];
  categorias_producto?: string[];
  productos?: string[];
  seleccionado: boolean;
}

export interface Definitivo {
  resultado_id: string | null;
  proveedor: string | null;
  precio: number | null;
  moneda: string;
  url: string | null;
  fuente: string | null;
  precio_clp: number | null;
  precio_unitario?: number | null;
  unidad_medida?: string;
  seleccionado_por?: string | null;
  seleccionado_at?: string | null;
  origen?: "sugerido" | "proveedor" | "buscado_web";
}

export interface ItemLista {
  cotizacion_id: string;
  nombre: string;
  cantidad: number;
  unidad: string;
  partida?: string | null;
  categoria?: string | null;
  comparado: boolean;
  comparados: ComparadoLista[];
  definitivo: Definitivo | null;
  proveedores_recomendados: ProveedorRecomendado[];
}

interface Aprobacion {
  estado: "pendiente" | "aprobado" | "rechazado" | "aprobado_con_observaciones";
  resultado?: "aprobado_con_observaciones";
  aprobador_email?: string;
  token?: string;
  comentario_rechazo?: string;
  comentario_observaciones?: string;
  observaciones_items?: Record<string, string>;
  decidido_at?: string;
}

export interface Compra {
  estado: "enviada_oc" | "comprado" | "pendiente";
  oc_id?: string;
  numero_oc?: string;
  precio_real?: number;
  boleta_url?: string;
  notas?: string;
  origen?: string;
  enviada_oc_at?: string;
  comprado_at?: string;
}

export interface DetalleLista {
  id: string;
  nombre: string;
  created_at: string | null;
  monto_total: number;
  items: ItemLista[];
  aprobacion?: Aprobacion;
  justificaciones?: Record<string, string>;
  compras?: Record<string, Compra>;
  creado_por?: string | null;
}

const FUENTE_LABEL: Record<string, string> = {
  mercadolibre: "MercadoLibre", google: "Google Shopping",
  mouser: "Mouser", digikey: "DigiKey", tme: "TME", manual: "Manual",
  sodimac: "Sodimac", easy: "Easy", lasierra: "La Sierra", construmart: "Construmart",
  vitel: "Vitel", dartel: "Dartel", ferrelectrica: "Ferrelectrica", gobantes: "Gobantes", rhona: "Rhona",
  clcsa: "CLC Maderas", wmaderas: "W Maderas", ferramenta: "Ferramenta", maderas_dir: "Aserraderos CL",
};

const fmtCLP = (n: number) => `$${Math.round(n).toLocaleString("es-CL")}`;
const fmtPrecio = (n: number, m: string) =>
  m === "CLP" ? fmtCLP(n) : `${n.toLocaleString("en-US", { minimumFractionDigits: 2 })} ${m}`;

const CATEGORIAS_ITEM = {
  electronica: { label: "Electrónica", icon: Cpu },
  construccion: { label: "Construcción", icon: Building2 },
  carpinteria: { label: "Carpintería", icon: Hammer },
  insumos_medicos: { label: "Insumos médicos", icon: HeartPulse },
  industrial: { label: "Industrial", icon: Factory },
  tuberias_valvulas: { label: "Tuberías y válvulas", icon: GitBranch },
  mecanico: { label: "Mecánico", icon: Wrench },
  electrico: { label: "Eléctrico", icon: Zap },
  hidraulico: { label: "Hidráulico", icon: Droplets },
  neumatico: { label: "Neumático", icon: Wind },
  servicio: { label: "Servicio", icon: Briefcase },
  consumible: { label: "Consumible", icon: Package },
  otro: { label: "Otro", icon: Boxes },
} as const;

function categoriaItem(categoria: string | null | undefined) {
  const clave = (categoria || "otro").toLowerCase() as keyof typeof CATEGORIAS_ITEM;
  return CATEGORIAS_ITEM[clave] ?? {
    label: categoria ? categoria.replaceAll("_", " ") : "Otro",
    icon: Boxes,
  };
}

export default function ListaDetallePage() {
  const { id: idUrl } = useParams<{ id: string }>();
  const router = useRouter();
  const { nombreDe, hayVariosMiembros } = useMiembrosOrg();
  const [userId, setUserId] = useState<string | null>(null);
  const [lista, setLista] = useState<DetalleLista | null>(null);
  const [loading, setLoading] = useState(true);
  const [toast, setToast] = useState("");
  const [tasas, setTasas] = useState<Record<string, number>>({});
  const [guardandoDef, setGuardandoDef] = useState<string | null>(null);
  const [guardandoProveedor, setGuardandoProveedor] = useState<string | null>(null);
  const [sugeridosAbiertos, setSugeridosAbiertos] = useState<Set<string>>(new Set());
  const [confianzaAbiertos, setConfianzaAbiertos] = useState<Set<string>>(new Set());
  const [proveedoresAbiertos, setProveedoresAbiertos] = useState<Set<string>>(new Set());
  const [preparandoComparacion, setPreparandoComparacion] = useState(false);
  const [justificaciones, setJustificaciones] = useState<Record<string, string>>({});
  const [aprobadorEmail, setAprobadorEmail] = useState("");
  const [solicitando, setSolicitando] = useState(false);
  const [mostrarAprobacion, setMostrarAprobacion] = useState(false);
  const [userMeta, setUserMeta] = useState<Record<string, string>>({});
  const [plan, setPlan] = useState<string>("free");
  // Item cuyo OC se está editando en el modal (solo ese ítem, no toda la lista)
  const [ocItem, setOcItem] = useState<ItemLista | null>(null);
  // Panel "Lista de compras" para ítems que se compran online (no por OC)
  const [mostrarComprasOnline, setMostrarComprasOnline] = useState(false);
  const [subiendoBoleta, setSubiendoBoleta] = useState(false);
  const [resultadoBoleta, setResultadoBoleta] = useState<{
    proveedor?: string; total?: number;
    items_detectados: { nombre_ocr: string; cotizacion_id: string | null; precio: number | null }[];
  } | null>(null);
  const boletaInputRef = useRef<HTMLInputElement>(null);

  const alternarSugeridos = (cotizacionId: string) => {
    setSugeridosAbiertos(actual => {
      const siguiente = new Set(actual);
      if (siguiente.has(cotizacionId)) siguiente.delete(cotizacionId);
      else siguiente.add(cotizacionId);
      return siguiente;
    });
  };

  const alternarProveedoresConfianza = (cotizacionId: string) => {
    setConfianzaAbiertos(actual => {
      const siguiente = new Set(actual);
      if (siguiente.has(cotizacionId)) siguiente.delete(cotizacionId);
      else siguiente.add(cotizacionId);
      return siguiente;
    });
  };

  const alternarDetalleProveedor = (clave: string) => {
    setProveedoresAbiertos(actual => {
      const siguiente = new Set(actual);
      if (siguiente.has(clave)) siguiente.delete(clave);
      else siguiente.add(clave);
      return siguiente;
    });
  };

  // Id real de la lista (una vez cargada) — las cotizaciones sueltas se
  // envuelven al vuelo con un id nuevo distinto al de la URL original.
  const id = lista?.id ?? idUrl;

  const aCLP = useCallback((valor: number, moneda: string | null | undefined): number => {
    const m = moneda || "CLP";
    if (m === "CLP") return valor;
    return (valor / (tasas[m] ?? 1)) * (tasas.CLP ?? 950);
  }, [tasas]);

  const cargar = useCallback(async (uid: string) => {
    try {
      const res = await authFetch(`${API_URL}/api/listas/${idUrl}`);
      if (res.ok) {
        const data = await res.json();
        setLista(data);
        if (data.justificaciones) setJustificaciones(data.justificaciones);
        // Cotizaciones sueltas se envuelven al vuelo con un id nuevo: actualiza
        // la URL al id real de la lista para que las siguientes acciones apunten ahí.
        if (data.id && data.id !== idUrl) router.replace(`/listas/${data.id}`);
      }
    } catch { /* silent */ }
    setLoading(false);
  }, [idUrl, router]);

  useEffect(() => {
    fetch("https://open.er-api.com/v6/latest/USD")
      .then(r => r.json())
      .then(d => { if (d.rates) setTasas(d.rates); })
      .catch(() => setTasas({ CLP: 950, EUR: 0.92, CNY: 7.25, GBP: 0.79 }));
    createClient().auth.getUser().then(({ data }) => {
      const uid = data.user?.id ?? null;
      setUserId(uid);
      if (uid) cargar(uid); else setLoading(false);
      const m = data.user?.user_metadata ?? {};
      setUserMeta(m);
      if (m.autorizador_email) setAprobadorEmail(m.autorizador_email);
      if (m.plan) setPlan(m.plan);
    });
  }, [cargar]);

  const elegirDefinitivo = async (item: ItemLista, c: ComparadoLista) => {
    if (!userId) return;
    const precio = c.precio_cotizado ?? c.precio;
    const moneda = c.precio_cotizado != null ? "CLP" : c.moneda;
    setGuardandoDef(item.cotizacion_id);
    try {
      await authFetch(`${API_URL}/api/listas/${id}/definitivo`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          cotizacion_id: item.cotizacion_id,
          resultado_id: c.resultado_id,
          proveedor: c.proveedor,
          precio, moneda,
          url: c.url, fuente: c.fuente,
          precio_clp: precio != null ? aCLP(precio, moneda) : null,
        }),
      });
      setToast(`Definitivo para ${item.nombre}: ${c.proveedor}`);
      setTimeout(() => setToast(""), 3000);
      await cargar(userId);
    } catch {
      setToast("No se pudo guardar el definitivo");
      setTimeout(() => setToast(""), 3000);
    } finally {
      setGuardandoDef(null);
    }
  };

  const alternarProveedor = async (item: ItemLista, proveedor: ProveedorRecomendado) => {
    if (!userId) return;
    const clave = `${item.cotizacion_id}:${proveedor.id}`;
    setGuardandoProveedor(clave);
    try {
      const res = await authFetch(`${API_URL}/api/listas/${id}/seleccionar-proveedor`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          cotizacion_id: item.cotizacion_id,
          origen: proveedor.origen, proveedor_id: proveedor.origen === "proveedor" ? proveedor.id : null,
          email: proveedor.email, seleccionado: !proveedor.seleccionado,
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "No se pudo guardar la selección");
      await cargar(userId);
      setToast(proveedor.seleccionado ? "Proveedor quitado" : "Proveedor agregado a la cotización");
    } catch (e) {
      setToast(e instanceof Error ? e.message : "No se pudo guardar la selección");
    } finally { setGuardandoProveedor(null); }
  };

  const irACompararProveedores = async () => {
    if (!userId) return;
    setPreparandoComparacion(true);
    try {
      const res = await authFetch(`${API_URL}/api/listas/${id}/rfq/preparar`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "No se pudo preparar la comparación");
      router.push(`/listas/${id}/rfq`);
    } catch (e) {
      setToast(e instanceof Error ? e.message : "No se pudo preparar la comparación");
    } finally { setPreparandoComparacion(false); }
  };

  const actualizarCantidad = async (item: ItemLista, cantidad: number) => {
    if (!userId || cantidad <= 0 || cantidad === item.cantidad) return;
    // Optimista: refleja al tiro en la UI
    setLista(prev => prev ? {
      ...prev,
      items: prev.items.map(it => it.cotizacion_id === item.cotizacion_id ? { ...it, cantidad } : it),
    } : prev);
    try {
      await authFetch(`${API_URL}/api/listas/${id}/cantidad`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ cotizacion_id: item.cotizacion_id, cantidad }),
      });
    } catch {
      setToast("No se pudo guardar la cantidad");
      setTimeout(() => setToast(""), 3000);
    }
  };

  const quitarDefinitivo = async (item: ItemLista) => {
    if (!userId) return;
    setGuardandoDef(item.cotizacion_id);
    try {
      const resp = await authFetch(`${API_URL}/api/listas/${id}/definitivo`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ cotizacion_id: item.cotizacion_id, quitar: true }),
      });
      if (!resp.ok) throw new Error();
      await cargar(userId);
    } catch {
      setToast("No se pudo quitar la selección. Intenta de nuevo.");
      setTimeout(() => setToast(""), 3500);
    } finally {
      setGuardandoDef(null);
    }
  };

  const autoSeleccionarBaratos = async () => {
    if (!userId || !lista) return;
    const motivos: Record<string, string> = {};
    for (const it of lista.items) {
      const comparados = it.comparados.filter(c => (c.precio_cotizado ?? c.precio) != null);
      if (!comparados.length) continue;
      comparados.sort((a, b) => {
        const pa = aCLP(a.precio_cotizado ?? a.precio!, a.precio_cotizado != null ? "CLP" : a.moneda);
        const pb = aCLP(b.precio_cotizado ?? b.precio!, b.precio_cotizado != null ? "CLP" : b.moneda);
        return pa - pb;
      });
      await elegirDefinitivo(it, comparados[0]);
      motivos[it.cotizacion_id] = "El más económico";
    }
    // La pantalla siguiente consume este valor y lo convierte en el motivo por
    // defecto de cada ítem. No pisa una justificación escrita manualmente.
    sessionStorage.setItem(`baiyer:justificaciones:${id}`, JSON.stringify(motivos));
    router.push(`/listas/${id}/autorizacion`);
  };

  const solicitarAprobacion = async () => {
    if (!userId || !lista || !aprobadorEmail.trim()) return;
    setSolicitando(true);
    try {
      const res = await authFetch(`${API_URL}/api/listas/${id}/solicitar-aprobacion`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          aprobador_email: aprobadorEmail.trim(),
          justificaciones,
          nombre_solicitante: userMeta.nombre_usuario ?? "",
          empresa: userMeta.empresa ?? "",
        }),
      });
      if (!res.ok) {
        const d = await res.json().catch(() => ({}));
        throw new Error(d.detail ?? "Error al solicitar");
      }

      // El backend ya envió el correo por la cuenta Gmail conectada del
      // usuario (misma integración que se usa para cotizar a proveedores);
      // no hay que abrir el cliente de correo local.
      setToast("Solicitud de autorización enviada por correo");
      setTimeout(() => setToast(""), 4000);
      setMostrarAprobacion(false);
      await cargar(userId);
    } catch (e) {
      setToast(e instanceof Error ? e.message : "Error al solicitar aprobación");
      setTimeout(() => setToast(""), 3500);
    } finally {
      setSolicitando(false);
    }
  };

  const reiniciarAprobacion = async () => {
    if (!userId) return;
    try {
      await authFetch(`${API_URL}/api/listas/${id}/reenviar-aprobacion`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      });
      setToast("Lista desbloqueada, puedes modificarla y re-solicitar");
      setTimeout(() => setToast(""), 3500);
      await cargar(userId);
    } catch {
      setToast("Error al reiniciar aprobación");
      setTimeout(() => setToast(""), 3000);
    }
  };

  // Marca la compra de un ítem: OC enviada (con id/número) o comprado a mano
  const registrarCompra = async (
    cotizacionId: string,
    estado: "enviada_oc" | "comprado" | "pendiente",
    extra: { oc_id?: string; numero_oc?: string; precio_real?: number } = {},
  ) => {
    if (!userId) return;
    try {
      const resp = await authFetch(`${API_URL}/api/listas/${id}/compra`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ cotizacion_id: cotizacionId, estado, ...extra }),
      });
      if (!resp.ok) throw new Error();
      await cargar(userId);
    } catch {
      setToast("No se pudo registrar la compra. Intenta de nuevo.");
      setTimeout(() => setToast(""), 3500);
    }
  };

  const subirBoleta = async (file: File) => {
    if (!userId) return;
    setSubiendoBoleta(true);
    setResultadoBoleta(null);
    try {
      const base64 = await new Promise<string>((res, rej) => {
        const r = new FileReader();
        r.onload = () => res((r.result as string).split(",")[1]);
        r.onerror = rej;
        r.readAsDataURL(file);
      });
      const resp = await authFetch(`${API_URL}/api/listas/${id}/boleta-scan`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          imagen_base64: base64,
          imagen_mime: file.type || "image/jpeg",
          auto_marcar: true,
        }),
      });
      const data = await resp.json();
      if (!resp.ok) throw new Error(data?.detail || "Error al leer la boleta");
      setResultadoBoleta({
        proveedor: data.proveedor,
        total: data.total,
        items_detectados: data.items_detectados || [],
      });
      const n = (data.items_detectados || []).filter((m: { cotizacion_id: string | null }) => m.cotizacion_id).length;
      setToast(n > 0 ? `Boleta procesada: ${n} ítem${n !== 1 ? "s" : ""} marcados como comprados` : "Boleta procesada, no se encontraron coincidencias");
      setTimeout(() => setToast(""), 4000);
      await cargar(userId);
    } catch (e) {
      setToast(e instanceof Error ? e.message : "Error al subir boleta");
      setTimeout(() => setToast(""), 3500);
    } finally {
      setSubiendoBoleta(false);
    }
  };

  if (loading) return (
    <div>
      <SkeletonBox height={13} width={140} style={{ marginBottom: 16 }} />
      <SkeletonBox height={26} width={320} style={{ marginBottom: 8 }} />
      <SkeletonBox height={13} width={220} style={{ marginBottom: 20 }} />
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: 12, marginBottom: 20 }}>
        <CascadeWrapper>
          {Array.from({ length: 3 }).map((_, i) => (
            <Card key={i} padding={16}>
              <SkeletonBox height={11} width="60%" style={{ marginBottom: 8 }} />
              <SkeletonBox height={22} width="40%" />
            </Card>
          ))}
        </CascadeWrapper>
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        <CascadeWrapper staggerMs={70}>
          {Array.from({ length: 4 }).map((_, i) => (
            <Card key={i} padding={16}>
              <SkeletonBox height={15} width="35%" style={{ marginBottom: 8 }} />
              <SkeletonText lines={1} widths={["50%"]} />
            </Card>
          ))}
        </CascadeWrapper>
      </div>
    </div>
  );
  if (!lista) return <div style={{ color: "var(--n-600)", padding: "40px 0", textAlign: "center", fontSize: 13.5 }}>Lista no encontrada.</div>;

  const definitivos = lista.items.filter(it => it.definitivo);
  const totalCLP = definitivos.reduce((a, it) => a + (it.definitivo?.precio_clp ?? 0) * (it.cantidad || 1), 0);
  const completa = definitivos.length === lista.items.length;
  const proveedoresSeleccionados = new Set(
    lista.items.flatMap(it => (it.proveedores_recomendados || [])
      .filter(p => p.seleccionado)
      .map(p => p.origen === "sugerido" ? p.email || p.id : p.id))
  ).size;

  return (
    <>
      {toast && (
        <div style={{
          position: "fixed", top: 20, right: 20, zIndex: 999,
          background: "var(--n-900)", color: "var(--canvas)",
          padding: "11px 16px", fontSize: 13.5, fontWeight: 500,
          borderRadius: "var(--r-md)", boxShadow: "var(--shadow-pop)",
        }}>{toast}</div>
      )}

      {!lista.aprobacion && proveedoresSeleccionados > 0 && (
        <div style={{
          position: "fixed", bottom: 24, left: "50%", transform: "translateX(-50%)",
          width: "min(780px, calc(100vw - 40px))", zIndex: 300,
        }}>
          <div style={{
            background: "var(--n-900)", borderRadius: "var(--r-xl)",
            boxShadow: "var(--shadow-modal)", padding: "12px 18px",
            display: "flex", justifyContent: "space-between", alignItems: "center",
            gap: 10, flexWrap: "wrap",
          }}>
            <span style={{ fontSize: 13.5, fontWeight: 500, color: "var(--canvas)" }}>
              {proveedoresSeleccionados} proveedor{proveedoresSeleccionados !== 1 ? "es" : ""} seleccionado{proveedoresSeleccionados !== 1 ? "s" : ""}
            </span>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              <button onClick={() => router.push(`/listas/${id}/busqueda-complementaria`)} style={{
                background: "var(--surface)", color: "var(--n-900)", border: "none",
                borderRadius: "var(--r-md)", padding: "9px 14px",
                fontSize: 13.5, fontWeight: 500, fontFamily: "var(--font-sans)", cursor: "pointer",
              }}>
                Buscar online <span style={{ color: "var(--n-500)", fontSize: 12 }}>(opcional)</span>
              </button>
              <button onClick={() => void irACompararProveedores()} disabled={preparandoComparacion} style={{
                background: "var(--brand)", color: "#fff", border: "none",
                borderRadius: "var(--r-md)", padding: "9px 16px",
                fontSize: 13.5, fontWeight: 600, fontFamily: "var(--font-sans)",
                cursor: preparandoComparacion ? "not-allowed" : "pointer",
                opacity: preparandoComparacion ? .5 : 1,
              }}>
                {preparandoComparacion ? "Preparando…" : `Comparar (${proveedoresSeleccionados}) →`}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Header */}
      <div style={{ marginBottom: 20 }}>
        <Link href="/listas" style={{
          display: "inline-flex", alignItems: "center", gap: 6, marginBottom: 12,
          fontSize: 13, color: "var(--n-500)", textDecoration: "none",
        }}>
          <ArrowLeft size={15} strokeWidth={1.75} /> Cotizaciones
        </Link>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 16, flexWrap: "wrap" }}>
          <div>
            <h1 style={{ fontSize: 26, lineHeight: 1.2, fontWeight: 600, color: "var(--n-900)", margin: "0 0 6px", letterSpacing: "-0.015em" }}>
              {lista.nombre}
            </h1>
            <div style={{ fontSize: 13.5, color: "var(--n-600)" }}>
              {lista.items.length} ítems · {lista.items.filter(i => i.comparado).length} comparados · {definitivos.length} definitivos
              {hayVariosMiembros && nombreDe(lista.creado_por) && (
                <> · creada por <strong style={{ color: "var(--n-700)", fontWeight: 500 }}>{nombreDe(lista.creado_por)}</strong></>
              )}
            </div>
          </div>
          <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap", justifyContent: "flex-end" }}>
            {!lista.aprobacion && (
              <BtnSecondary onClick={() => router.push(`/listas/${lista.id}/busqueda-complementaria`)} icon={Search}>
                Completar cobertura
              </BtnSecondary>
            )}
            {!lista.aprobacion && lista.items.some(it => it.comparados.some(c => (c.precio_cotizado ?? c.precio) != null)) && (
              <BtnSecondary onClick={autoSeleccionarBaratos} icon={Wand2}>Escoger lo más barato</BtnSecondary>
            )}
            <InformeLista listaId={lista.id} userId={userId ?? ""} nombreLista={lista.nombre} />
          </div>
        </div>
      </div>

      {/* Resumen */}
      <div style={{
        display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))",
        gap: 12, marginBottom: 20,
      }}>
        {[
          { label: "Definitivos elegidos", val: `${definitivos.length}/${lista.items.length}`, color: completa ? "var(--success)" : undefined },
          { label: "Total seleccionados", val: totalCLP ? fmtCLP(totalCLP) : "—", mono: true },
          { label: "Proveedores distintos", val: String(new Set(definitivos.map(it => it.definitivo?.proveedor)).size || "—") },
        ].map((s, i) => (
          <Card key={i} padding={16}>
            <div style={{ fontSize: 12.5, color: "var(--n-500)", marginBottom: 6 }}>{s.label}</div>
            <div style={{
              fontSize: 24, fontWeight: 600, letterSpacing: "-0.015em",
              color: s.color ?? "var(--n-900)",
              fontFamily: s.mono ? "var(--font-mono)" : undefined,
              fontVariantNumeric: s.mono ? "tabular-nums" : undefined,
            }}>{s.val}</div>
          </Card>
        ))}
      </div>

      {/* Banner de estado de aprobación */}
      {lista.aprobacion && (() => {
        const est = lista.aprobacion.estado;
        const badge = est === "aprobado" ? "aprobada" : est === "rechazado" ? "rechazada" : "cotizando";
        const texto = est === "aprobado_con_observaciones" ? "Aprobada con observaciones" : est === "aprobado" ? "Autorizada" : est === "rechazado" ? "Rechazada" : "Esperando autorización";
        return (
          <Card padding={16} style={{ marginBottom: 20 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <Badge status={badge}>{texto}</Badge>
                {lista.aprobacion.aprobador_email && (
                  <span style={{ fontSize: 13.5, color: "var(--n-600)" }}>{lista.aprobacion.aprobador_email}</span>
                )}
              </div>
              {(est === "rechazado" || est === "aprobado_con_observaciones") && (
                <BtnSecondary onClick={reiniciarAprobacion} size="sm">
                  Modificar y volver a solicitar
                </BtnSecondary>
              )}
            </div>
            {(est === "rechazado" ? lista.aprobacion.comentario_rechazo : lista.aprobacion.comentario_observaciones) && (
              <SummaryPanel style={{ marginTop: 12 }}>
                <div style={{ fontSize: 12.5, color: "var(--n-500)", marginBottom: 4 }}>{est === "rechazado" ? "Motivo del autorizador" : "Observaciones del autorizador"}</div>
                <div style={{ fontSize: 14, color: "var(--n-900)", lineHeight: 1.6 }}>
                  {est === "rechazado" ? lista.aprobacion.comentario_rechazo : lista.aprobacion.comentario_observaciones}
                </div>
              </SummaryPanel>
            )}
            {est === "aprobado_con_observaciones" && lista.aprobacion.observaciones_items && Object.keys(lista.aprobacion.observaciones_items).length > 0 && (
              <SummaryPanel style={{ marginTop: 12 }}>
                <div style={{ fontSize: 12.5, color: "var(--n-500)", marginBottom: 6 }}>Ítems a corregir antes de reenviar</div>
                {Object.entries(lista.aprobacion.observaciones_items).map(([cotizacionId, motivo]) => (
                  <div key={cotizacionId} style={{ fontSize: 13.5, color: "var(--n-800)", padding: "5px 0", borderTop: "1px solid var(--n-200)" }}>
                    <strong>{lista.items.find(item => item.cotizacion_id === cotizacionId)?.nombre ?? "Ítem"}</strong>{motivo ? ` — ${motivo}` : ""}
                  </div>
                ))}
              </SummaryPanel>
            )}
          </Card>
        );
      })()}

      {/* Ítems con sus comparados */}
      {lista.items.map((it, idx) => {
        // ¿La lista está autorizada y este ítem tiene definitivo elegido?
        const autorizadaYConDef = lista.aprobacion?.estado === "aprobado" && !!it.definitivo;
        const compra = lista.compras?.[it.cotizacion_id];
        // Si el definitivo trae email (via contacto en comparados), OC por correo
        const emailProveedor = it.comparados.find(c => c.resultado_id === it.definitivo?.resultado_id)?.contacto || null;
        const puedeEnviarOC = autorizadaYConDef && !!emailProveedor && compra?.estado !== "comprado";
        const compraOnline = autorizadaYConDef && !emailProveedor && compra?.estado !== "comprado";
        // El autorizador rechazó este ítem puntual al aprobar con observaciones.
        const rechazado = lista.aprobacion?.estado === "aprobado_con_observaciones" && !!lista.aprobacion.observaciones_items?.[it.cotizacion_id];
        const categoria = categoriaItem(it.categoria);
        const IconoCategoria = categoria.icon;

        return (
        <div key={it.cotizacion_id} style={{
          border: rechazado ? "1px solid var(--st-rechazada-fg)" : "1px solid var(--n-200)",
          background: "var(--surface)",
          borderRadius: "var(--r-lg)", marginBottom: 16, overflow: "hidden",
          boxShadow: "var(--shadow-card)",
        }}>
          <div style={{
            display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 10,
            padding: "12px 16px", borderBottom: "1px solid var(--n-200)",
            background: rechazado ? "var(--st-rechazada-bg)" : "var(--canvas)",
          }}>
            <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
              <span style={{
                fontSize: 15, fontWeight: 600,
                color: rechazado ? "var(--st-rechazada-fg)" : "var(--n-900)",
                textDecoration: rechazado ? "line-through" : undefined,
              }}>{idx + 1}. {it.nombre}</span>
              {rechazado && <Badge status="rechazada">Rechazado</Badge>}
              <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
                <span style={{ fontSize: 12.5, color: "var(--n-500)" }}>Cant.</span>
                <input
                  type="number"
                  min={1}
                  defaultValue={it.cantidad || 1}
                  key={`${it.cotizacion_id}-${it.cantidad}`}
                  onBlur={e => actualizarCantidad(it, parseFloat(e.target.value) || 1)}
                  onKeyDown={e => { if (e.key === "Enter") (e.target as HTMLInputElement).blur(); }}
                  style={{
                    width: 62, background: "var(--surface)", border: "1px solid var(--n-300)",
                    borderRadius: "var(--r-sm)", padding: "5px 8px", fontSize: 13,
                    color: "var(--n-900)", fontFamily: "var(--font-mono)",
                    fontVariantNumeric: "tabular-nums", outline: "none", textAlign: "right",
                  }}
                />
                <span style={{ fontSize: 12.5, color: "var(--n-600)" }}>{it.unidad || "unidad"}</span>
              </span>
              <span style={{
                display: "inline-flex", alignItems: "center", gap: 6,
                padding: "4px 8px", border: "1px solid var(--n-200)",
                borderRadius: "var(--r-sm)", background: "var(--surface)",
                fontSize: 11.5, fontWeight: 500, color: "var(--n-600)",
                textTransform: "capitalize",
              }} title={`Categoría: ${categoria.label}`}>
                <IconoCategoria size={13} strokeWidth={1.8} />
                {categoria.label}
              </span>
              {it.definitivo && (
                <Badge status="aprobada">
                  {it.definitivo.proveedor}
                  {it.definitivo.precio_clp != null && (it.cantidad || 1) > 1 &&
                    ` · ${it.cantidad} ${it.unidad || "unidad"} × ${fmtCLP(it.definitivo.precio_clp)}/${it.unidad || "unidad"}`}
                </Badge>
              )}
              {it.definitivo && hayVariosMiembros && nombreDe(it.definitivo.seleccionado_por) && (
                <span style={{ fontSize: 11.5, color: "var(--n-500)" }}>
                  seleccionado por <strong style={{ color: "var(--n-700)", fontWeight: 500 }}>{nombreDe(it.definitivo.seleccionado_por)}</strong>
                </span>
              )}
              {/* Estado de compra por ítem — visible solo si ya está en curso o comprado */}
              {compra?.estado === "comprado" && (
                <Badge status="cerrada">
                  ✓ Comprado
                  {compra.precio_real != null ? ` · ${fmtCLP(compra.precio_real)}` : ""}
                </Badge>
              )}
              {compra?.estado === "enviada_oc" && (
                <Badge status="en_curso">
                  OC {compra.numero_oc || "enviada"}
                </Badge>
              )}
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
              {/* Acciones de compra (solo si la lista está aprobada) */}
              {puedeEnviarOC && (
                <BtnPrimary size="sm" icon={Send} onClick={() => setOcItem(it)}>
                  Enviar OC
                </BtnPrimary>
              )}
              {compraOnline && (
                <>
                  {it.definitivo?.url && (
                    <a href={it.definitivo.url} target="_blank" rel="noopener noreferrer"
                      style={{ display: "inline-flex", alignItems: "center", gap: 6,
                        fontSize: 13, fontWeight: 500, color: "var(--brand)", textDecoration: "none" }}>
                      <ExternalLink size={14} strokeWidth={1.75} /> Ir a comprar
                    </a>
                  )}
                  <BtnSecondary size="sm" icon={Check} onClick={() => registrarCompra(it.cotizacion_id, "comprado")}>
                    Marcar comprado
                  </BtnSecondary>
                </>
              )}
              {compra?.estado && compra.estado !== "pendiente" && (
                <button
                  onClick={() => registrarCompra(it.cotizacion_id, "pendiente")}
                  title="Deshacer estado de compra"
                  style={{
                    background: "transparent", border: "none", cursor: "pointer",
                    color: "var(--n-500)", fontSize: 12.5, fontFamily: "var(--font-sans)",
                    textDecoration: "underline",
                  }}
                >
                  Deshacer
                </button>
              )}
              <Link href={`/cotizar/${it.cotizacion_id}/resultados?lista=${lista.id}`}
                style={{ fontSize: 13.5, fontWeight: 500, color: "var(--brand)", textDecoration: "none" }}>
                {it.comparado ? "Cambiar selección →" : "Buscar opciones →"}
              </Link>
            </div>
          </div>

          {it.proveedores_recomendados?.length > 0 && (
            <div style={{ padding: "14px 16px", borderBottom: "1px solid var(--n-200)", background: "var(--surface)" }}>
              {(["proveedor", "sugerido"] as const).map(origen => {
                const proveedores = it.proveedores_recomendados
                  .filter(p => p.origen === origen)
                  .sort((a, b) => (b.match_score ?? 0) - (a.match_score ?? 0));
                if (!proveedores.length) return null;
                const esSugerido = origen === "sugerido";
                const grupoAbierto = esSugerido
                  ? sugeridosAbiertos.has(it.cotizacion_id)
                  : confianzaAbiertos.has(it.cotizacion_id);
                return <div key={origen} style={{ marginBottom: origen === "proveedor" ? 14 : 0 }}>
                  <button
                    type="button"
                    aria-expanded={grupoAbierto}
                    onClick={() => esSugerido ? alternarSugeridos(it.cotizacion_id) : alternarProveedoresConfianza(it.cotizacion_id)}
                    style={{
                      width: "100%", display: "flex", alignItems: "center", gap: 7,
                      border: "none", background: "transparent", padding: "3px 0 8px",
                      color: "var(--n-700)", cursor: "pointer", textAlign: "left",
                      fontFamily: "var(--font-sans)", fontSize: 12, fontWeight: 600,
                      textTransform: "uppercase", letterSpacing: ".04em",
                    }}
                  >
                    <ChevronRight size={15} strokeWidth={2} style={{
                      flexShrink: 0, transition: "transform .3s cubic-bezier(.4,0,.2,1)",
                      transform: grupoAbierto ? "rotate(90deg)" : "rotate(0deg)",
                    }} />
                    {esSugerido ? "Sugeridos por Baiyer" : "Proveedores de confianza"}
                    <span style={{ color: "var(--n-400)", fontWeight: 500, letterSpacing: 0, textTransform: "none" }}>
                      ({proveedores.length})
                    </span>
                  </button>
                  <div className={`acc-panel${grupoAbierto ? " open" : ""}`}>
                    <div className="acc-inner">
                      <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                    {proveedores.map(proveedor => {
                      const clave = `${it.cotizacion_id}:${proveedor.id}`;
                      const detalleAbierto = proveedoresAbiertos.has(clave);
                      const matchPorProducto = proveedor.match_label.startsWith("Match por producto:");
                      return <div key={proveedor.id} style={{
                        border: `1px solid ${proveedor.seleccionado ? "var(--brand)" : matchPorProducto ? "var(--success)" : "var(--n-200)"}`,
                        borderRadius: "var(--r-md)",
                        background: proveedor.seleccionado ? "var(--brand-50)" : matchPorProducto ? "var(--st-aprobada-bg)" : "var(--canvas)",
                        boxShadow: matchPorProducto ? "0 0 0 1px color-mix(in srgb, var(--success) 22%, transparent), 0 0 18px color-mix(in srgb, var(--success) 22%, transparent)" : undefined,
                        minWidth: 280, flex: "1 1 320px", maxWidth: 460,
                        transition: "border-color .2s ease, box-shadow .2s ease, background .2s ease",
                      }}>
                        <div
                          role="button" tabIndex={0} aria-expanded={detalleAbierto}
                          onClick={() => alternarDetalleProveedor(clave)}
                          onKeyDown={e => { if (e.key === "Enter" || e.key === " ") alternarDetalleProveedor(clave); }}
                          style={{ display: "flex", alignItems: "center", gap: 10, padding: "9px 10px", cursor: "pointer" }}
                        >
                          <ChevronRight size={15} style={{ flexShrink: 0, color: "var(--n-400)", transform: detalleAbierto ? "rotate(90deg)" : "rotate(0deg)", transition: "transform .3s cubic-bezier(.4,0,.2,1)" }} />
                          <div style={{ minWidth: 0, flex: 1 }}>
                            <div style={{ display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap" }}>
                              <strong style={{ fontSize: 13.5, color: "var(--n-900)" }}>{proveedor.nombre}</strong>
                              <span style={{ fontSize: 10.5, color: "var(--brand)", border: "1px solid var(--brand)", borderRadius: "var(--r-sm)", padding: "1px 5px" }}>{proveedor.match_label}</span>
                            </div>
                            <div style={{ display: "flex", gap: 5, alignItems: "center", fontSize: 11.5, color: "var(--n-500)", marginTop: 3, overflow: "hidden" }}>
                              <Mail size={12} /> <span style={{ overflow: "hidden", textOverflow: "ellipsis" }}>{proveedor.email || "Sin correo"}</span>
                            </div>
                          </div>
                          <div style={{ display: "flex", alignItems: "center", gap: 6, flexShrink: 0 }}>
                            <button onClick={e => { e.stopPropagation(); void alternarProveedor(it, proveedor); }} disabled={guardandoProveedor === clave || !proveedor.email} style={{
                              border: `1px solid ${proveedor.seleccionado ? "var(--brand)" : "var(--n-300)"}`,
                              background: proveedor.seleccionado ? "var(--brand)" : "var(--surface)",
                              color: proveedor.seleccionado ? "white" : "var(--brand)", borderRadius: "var(--r-md)",
                              padding: "6px 9px", fontSize: 12, fontWeight: 600, cursor: proveedor.email ? "pointer" : "not-allowed",
                            }}>{proveedor.seleccionado ? "Seleccionado" : "Agregar"}</button>
                          </div>
                        </div>
                        <div className={`acc-panel${detalleAbierto ? " open" : ""}`}>
                          <div className="acc-inner">
                            <div style={{ borderTop: "1px solid var(--n-200)", padding: "10px 12px 12px 37px", background: "var(--surface)" }}>
                              <div style={{ fontSize: 12, fontWeight: 600, color: "var(--n-800)", marginBottom: 7 }}>Por qué puede cotizar este ítem</div>
                              <div style={{ fontSize: 12.5, color: "var(--n-600)", lineHeight: 1.5, marginBottom: 8 }}>
                                {proveedor.match_label}. {proveedor.origen === "sugerido"
                                  ? "El proveedor está asociado a la categoría del ítem y estas capacidades provienen del catálogo Baiyer."
                                  : "Este proveedor pertenece al directorio de tu organización y tiene capacidad registrada para la categoría del ítem."}
                              </div>
                              {!!proveedor.categorias_producto?.length && <div style={{ marginBottom: 7 }}>
                                <span style={{ fontSize: 11.5, color: "var(--n-500)" }}>Especialidades: </span>
                                <span style={{ fontSize: 11.5, color: "var(--n-700)" }}>{proveedor.categorias_producto.join(" · ")}</span>
                              </div>}
                              {!!proveedor.productos?.length && <div>
                                <span style={{ fontSize: 11.5, color: "var(--n-500)" }}>Ejemplos del catálogo: </span>
                                <span style={{ fontSize: 11.5, color: "var(--n-700)" }}>{proveedor.productos.join(" · ")}</span>
                              </div>}
                            </div>
                          </div>
                        </div>
                      </div>;
                        })}
                      </div>
                    </div>
                  </div>
                </div>;
              })}
              <div style={{ marginTop: 10, fontSize: 11.5, color: "var(--n-500)" }}>
                Las sugerencias se ordenan por coincidencia con productos, especialidades y categoría. Confirma disponibilidad y precio al cotizar.
              </div>
            </div>
          )}

          {it.comparados.length === 0 ? (
            <div style={{ padding: "24px 16px", fontSize: 13.5, color: "var(--n-500)", textAlign: "center" }}>
              Aún no hay precios comparados. Selecciona proveedores arriba o usa “Buscar opciones”.
            </div>
          ) : (
            <div>
              <div style={{
                display: "grid", gridTemplateColumns: "1.4fr 120px 100px 120px 90px 110px", gap: 10,
                padding: "9px 16px", borderBottom: "1px solid var(--n-200)", background: "var(--canvas)",
              }}>
                {["Proveedor / página", "Precio", "Entrega", "Ubicación", "Origen", ""].map((h, hi) => (
                  <div key={hi} style={{ fontSize: 12, fontWeight: 600, color: "var(--n-600)" }}>{h}</div>
                ))}
              </div>
              {it.comparados.map((c, ci) => {
                const esDef = it.definitivo?.resultado_id === c.resultado_id;
                const precio = c.precio_cotizado ?? c.precio;
                const moneda = c.precio_cotizado != null ? "CLP" : c.moneda;
                return (
                  <div key={c.resultado_id} style={{
                    display: "grid", gridTemplateColumns: "1.4fr 120px 100px 120px 90px 110px", gap: 10,
                    padding: "12px 16px", alignItems: "center",
                    borderBottom: ci < it.comparados.length - 1 ? "1px solid var(--n-100)" : "none",
                    background: esDef ? "var(--st-aprobada-bg)" : ci % 2 ? "var(--canvas)" : undefined,
                  }}>
                    <div style={{ paddingRight: 8, minWidth: 0 }}>
                      {c.url ? (
                        <a href={c.url} target="_blank" rel="noopener noreferrer"
                          style={{ fontSize: 14, fontWeight: 600, color: "var(--n-900)", textDecoration: "none" }}>
                          {c.proveedor} ↗
                        </a>
                      ) : (
                        <span style={{ fontSize: 14, fontWeight: 600, color: "var(--n-900)" }}>{c.proveedor}</span>
                      )}
                      <div style={{ fontSize: 12.5, color: "var(--brand)" }}>
                        {FUENTE_LABEL[c.fuente ?? ""] ?? c.fuente ?? "—"}
                      </div>
                    </div>
                    <div style={{ fontSize: 14, fontWeight: 600, fontFamily: "var(--font-mono)", fontVariantNumeric: "tabular-nums" }}>
                      {precio != null ? fmtPrecio(precio, moneda) : "—"}
                      {precio != null && moneda !== "CLP" && (
                        <div style={{ fontSize: 12, color: "var(--n-500)", fontWeight: 400 }}>≈ {fmtCLP(aCLP(precio, moneda))}</div>
                      )}
                    </div>
                    <div style={{ fontSize: 13, color: "var(--n-600)" }}>{c.plazo_entrega ?? "—"}</div>
                    <div style={{ fontSize: 13, color: "var(--n-600)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{c.ubicacion ?? "—"}</div>
                    <div style={{ fontSize: 12.5, color: "var(--n-500)" }}>{c.contacto ? "Correo" : "Vía web"}</div>
                    <div style={{ textAlign: "right" }}>
                      {esDef ? (
                        <button
                          onClick={() => quitarDefinitivo(it)}
                          disabled={guardandoDef === it.cotizacion_id}
                          style={{
                            display: "inline-flex", alignItems: "center", gap: 5,
                            color: "var(--st-aprobada-fg)", background: "transparent", cursor: "pointer",
                            border: "1px solid var(--success)", borderRadius: "var(--r-md)",
                            padding: "6px 11px", fontSize: 13, fontWeight: 600, fontFamily: "var(--font-sans)",
                          }}
                        >
                          <Check size={14} strokeWidth={2} /> Elegido
                        </button>
                      ) : (
                        <button
                          onClick={() => elegirDefinitivo(it, c)}
                          disabled={guardandoDef === it.cotizacion_id || precio == null}
                          style={{
                            color: precio == null ? "var(--n-400)" : "var(--brand)",
                            background: "transparent", cursor: precio == null ? "not-allowed" : "pointer",
                            border: `1px solid ${precio == null ? "var(--n-200)" : "var(--n-300)"}`,
                            borderRadius: "var(--r-md)", padding: "6px 11px",
                            fontSize: 13, fontWeight: 600, fontFamily: "var(--font-sans)",
                          }}
                        >
                          Elegir
                        </button>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
        );
      })}

      {/* Ruta de compra final */}
      {definitivos.length > 0 && (
        <div style={{
          border: "1px solid var(--n-200)", borderRadius: "var(--r-lg)",
          overflow: "hidden", marginBottom: 24, boxShadow: "var(--shadow-card)",
        }}>
          <div style={{
            background: "var(--surface-2)", padding: "12px 16px",
            display: "flex", justifyContent: "space-between", alignItems: "center",
            gap: 10, flexWrap: "wrap", borderBottom: "1px solid var(--n-200)",
          }}>
            <span style={{ fontSize: 15, fontWeight: 600, color: "var(--n-900)" }}>
              Ruta de compra final
              {!completa && (
                <span style={{ fontWeight: 400, color: "var(--n-600)" }}>
                  {" "}({definitivos.length}/{lista.items.length} ítems definidos)
                </span>
              )}
            </span>
            <span style={{ fontSize: 16, fontWeight: 600, color: "var(--n-900)", fontFamily: "var(--font-mono)", fontVariantNumeric: "tabular-nums" }}>
              Total: {fmtCLP(totalCLP)}
            </span>
          </div>
          {definitivos.map((it, i) => {
            const d = it.definitivo!;
            const cant = it.cantidad || 1;
            const rechazado = lista.aprobacion?.estado === "aprobado_con_observaciones" && !!lista.aprobacion.observaciones_items?.[it.cotizacion_id];
            return (
              <div key={it.cotizacion_id} style={{
                display: "grid", gridTemplateColumns: "1fr 1fr 160px", gap: 12,
                padding: "12px 16px", alignItems: "center",
                background: rechazado ? "var(--st-rechazada-bg)" : "var(--surface)",
                borderBottom: i < definitivos.length - 1 ? "1px solid var(--n-100)" : "none",
              }}>
                <div style={{
                  fontSize: 14, fontWeight: 600,
                  color: rechazado ? "var(--st-rechazada-fg)" : "var(--n-900)",
                  textDecoration: rechazado ? "line-through" : undefined,
                }}>
                  {it.nombre}
                  <span style={{ color: "var(--n-500)", fontWeight: 400, marginLeft: 6, textDecoration: "none", display: "inline-block" }}>× {cant} {it.unidad || "unidad"}</span>
                </div>
                <div style={{ minWidth: 0 }}>
                  {d.url ? (
                    <a href={d.url} target="_blank" rel="noopener noreferrer" style={{ fontSize: 14, color: "var(--brand)", textDecoration: "none", fontWeight: 500 }}>
                      {d.proveedor}, comprar aquí ↗
                    </a>
                  ) : (
                    <span style={{ fontSize: 14 }}>{d.proveedor}</span>
                  )}
                  <div style={{ fontSize: 12.5, color: "var(--n-500)" }}>{FUENTE_LABEL[d.fuente ?? ""] ?? d.fuente ?? ""}</div>
                </div>
                <div style={{ textAlign: "right" }}>
                  <div style={{ fontSize: 15, fontWeight: 600, fontFamily: "var(--font-mono)", fontVariantNumeric: "tabular-nums" }}>
                    {d.precio_clp != null ? fmtCLP(d.precio_clp * cant) : d.precio != null ? fmtPrecio(d.precio * cant, d.moneda) : "—"}
                  </div>
                  {cant > 1 && d.precio_clp != null && (
                    <div style={{ fontSize: 12, color: "var(--n-500)" }}>{cant} × {fmtCLP(d.precio_clp)}</div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Acciones de aprobación */}
      {definitivos.length > 0 && !lista.aprobacion && (
        <div style={{ display: "flex", gap: 10, marginBottom: 16, flexWrap: "wrap" }}>
          <BtnPrimary onClick={() => router.push(`/listas/${id}/autorizacion`)} icon={Send}>
            Solicitar autorización
          </BtnPrimary>
        </div>
      )}

      {/* Panel de solicitud de aprobación */}
      {mostrarAprobacion && !lista.aprobacion && (
        <Card padding={20} style={{ marginBottom: 30, borderColor: "var(--brand-200)" }}>
          <h2 style={{ fontSize: 20, fontWeight: 600, color: "var(--n-900)", margin: "0 0 4px" }}>
            Solicitar autorización
          </h2>
          <p style={{ fontSize: 13.5, color: "var(--n-600)", margin: "0 0 18px", lineHeight: 1.6 }}>
            Le enviaremos un correo con el detalle y un enlace para aprobar o rechazar.
          </p>

          <div style={{ marginBottom: 18 }}>
            <Input
              label="Email del autorizador"
              value={aprobadorEmail}
              onChange={e => setAprobadorEmail(e.target.value)}
              placeholder="jefe@empresa.cl"
              type="email"
            />
          </div>

          <div style={{ fontSize: 13, fontWeight: 500, color: "var(--n-700)", marginBottom: 10 }}>
            Justificación por ítem <span style={{ color: "var(--n-500)", fontWeight: 400 }}>(opcional)</span>
          </div>
          {definitivos.map(it => (
            <div key={it.cotizacion_id} style={{ marginBottom: 12 }}>
              <div style={{ fontSize: 14, fontWeight: 600, color: "var(--n-900)", marginBottom: 5 }}>
                {it.nombre}, {it.definitivo?.proveedor}
                {it.definitivo?.precio_clp != null && (
                  <span style={{
                    color: "var(--n-500)", fontWeight: 400, marginLeft: 6,
                    fontFamily: "var(--font-mono)", fontVariantNumeric: "tabular-nums",
                  }}>
                    {fmtCLP(it.definitivo.precio_clp * (it.cantidad || 1))}
                  </span>
                )}
              </div>
              <input
                value={justificaciones[it.cotizacion_id] ?? ""}
                onChange={e => setJustificaciones(j => ({ ...j, [it.cotizacion_id]: e.target.value }))}
                placeholder="Ej: mejor precio, entrega rápida, proveedor conocido…"
                style={{
                  width: "100%", height: 38, background: "var(--surface)",
                  border: "1px solid var(--n-300)", borderRadius: "var(--r-md)",
                  padding: "0 12px", fontSize: 14, color: "var(--n-900)",
                  fontFamily: "var(--font-sans)", outline: "none", boxSizing: "border-box",
                }}
              />
            </div>
          ))}

          <div style={{ display: "flex", gap: 10, marginTop: 18 }}>
            <BtnPrimary
              onClick={solicitarAprobacion}
              disabled={solicitando || !aprobadorEmail.trim()}
              icon={Send}
            >
              {solicitando ? "Enviando…" : "Enviar solicitud por correo"}
            </BtnPrimary>
            <BtnSecondary onClick={() => setMostrarAprobacion(false)}>
              Cancelar
            </BtnSecondary>
          </div>
        </Card>
      )}

      {/* Modal OC — se abre por ítem: la OC contiene SOLO ese ítem con su cantidad */}
      {ocItem && (() => {
        const d = ocItem.definitivo!;
        const c = ocItem.comparados.find(x => x.resultado_id === d.resultado_id);
        const emailProv = c?.contacto || "";
        // OCModal espera un "Resultado" del comparador; lo armamos desde el definitivo
        const resultadoParaOC = {
          titulo: ocItem.nombre,
          proveedor: d.proveedor || "",
          precio: d.precio,
          moneda: d.moneda || "CLP",
          url: d.url || "",
          fuente: d.fuente || "",
          pais: "CL",
          proveedor_email: emailProv,
          plazo_entrega: c?.plazo_entrega ?? undefined,
        };
        return (
          <OCModal
            resultado={resultadoParaOC}
            nombreItem={ocItem.nombre}
            cotizacionId={ocItem.cotizacion_id}
            userId={userId ?? ""}
            plan={plan}
            cantidadInicial={ocItem.cantidad || 1}
            onClose={() => setOcItem(null)}
            onEnviada={(numeroOc: string) => {
              registrarCompra(ocItem.cotizacion_id, "enviada_oc", { numero_oc: numeroOc });
              setOcItem(null);
              setToast(`OC ${numeroOc} enviada a ${d.proveedor}`);
              setTimeout(() => setToast(""), 4000);
            }}
          />
        );
      })()}

      {/* Panel "Lista de compras" (ítems que se compran online, sin OC por correo) */}
      {lista.aprobacion?.estado === "aprobado" && (() => {
        const itemsOnline = lista.items.filter(it => {
          if (!it.definitivo) return false;
          const c = it.comparados.find(x => x.resultado_id === it.definitivo?.resultado_id);
          return !c?.contacto; // sin email = compra online
        });
        if (itemsOnline.length === 0) return null;
        const pendientes = itemsOnline.filter(it => lista.compras?.[it.cotizacion_id]?.estado !== "comprado");
        const totalPend = pendientes.reduce((s, it) => s + (it.definitivo!.precio_clp ?? 0) * (it.cantidad || 1), 0);

        // mailto con la lista de compras para reenviarla al comprador
        const cuerpoCorreo = itemsOnline.map(it => {
          const total = it.definitivo!.precio_clp != null ? fmtCLP(it.definitivo!.precio_clp * (it.cantidad || 1)) : "—";
          return `${it.cantidad} × ${it.nombre}\n  Proveedor: ${it.definitivo!.proveedor}\n  Total: ${total}\n  ${it.definitivo!.url || ""}`;
        }).join("\n\n");
        const mailto = `mailto:?subject=${encodeURIComponent(`Lista de compras · ${lista.nombre}`)}&body=${encodeURIComponent(cuerpoCorreo)}`;

        return (
          <Card style={{ marginTop: 24 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: 12, marginBottom: 12 }}>
              <div>
                <div style={{ display: "inline-flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
                  <ShoppingBag size={18} strokeWidth={1.75} style={{ color: "var(--brand)" }} />
                  <h3 style={{ fontSize: 18, fontWeight: 600, color: "var(--n-900)", margin: 0 }}>Lista de compras</h3>
                </div>
                <div style={{ fontSize: 13.5, color: "var(--n-600)" }}>
                  {pendientes.length} ítem{pendientes.length !== 1 ? "s" : ""} pendiente{pendientes.length !== 1 ? "s" : ""} de comprar en persona · Total {fmtCLP(totalPend)}
                </div>
              </div>
              <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                <a href={mailto} style={{ textDecoration: "none" }}>
                  <BtnSecondary size="sm" icon={Mail}>Enviar por correo</BtnSecondary>
                </a>
                <BtnPrimary size="sm" icon={Camera} onClick={() => boletaInputRef.current?.click()} disabled={subiendoBoleta}>
                  {subiendoBoleta ? "Leyendo boleta…" : "Foto de boleta"}
                </BtnPrimary>
                <input
                  ref={boletaInputRef}
                  type="file"
                  accept="image/*"
                  capture="environment"
                  style={{ display: "none" }}
                  onChange={e => { const f = e.target.files?.[0]; if (f) subirBoleta(f); e.target.value = ""; }}
                />
              </div>
            </div>

            {/* Ítems del checklist */}
            <div>
              {itemsOnline.map((it, i) => {
                const comprado = lista.compras?.[it.cotizacion_id]?.estado === "comprado";
                const compra = lista.compras?.[it.cotizacion_id];
                return (
                  <div key={it.cotizacion_id} style={{
                    display: "grid", gridTemplateColumns: "28px 1fr auto", gap: 12, alignItems: "center",
                    padding: "12px 4px",
                    borderBottom: i < itemsOnline.length - 1 ? "1px solid var(--n-100)" : "none",
                    opacity: comprado ? 0.55 : 1,
                  }}>
                    <button
                      onClick={() => registrarCompra(it.cotizacion_id, comprado ? "pendiente" : "comprado")}
                      aria-label={comprado ? "Desmarcar" : "Marcar como comprado"}
                      style={{
                        width: 22, height: 22, borderRadius: 6,
                        border: `1.5px solid ${comprado ? "var(--success)" : "var(--n-400)"}`,
                        background: comprado ? "var(--success)" : "var(--surface)",
                        color: "#fff", cursor: "pointer",
                        display: "inline-flex", alignItems: "center", justifyContent: "center",
                        padding: 0, fontFamily: "inherit",
                      }}
                    >
                      {comprado && <Check size={14} strokeWidth={2.5} />}
                    </button>
                    <div style={{ minWidth: 0 }}>
                      <div style={{
                        fontSize: 14, fontWeight: 500, color: "var(--n-900)",
                        textDecoration: comprado ? "line-through" : "none",
                      }}>
                        {it.cantidad || 1} × {it.nombre}
                      </div>
                      <div style={{ fontSize: 12.5, color: "var(--n-500)", display: "flex", gap: 10, flexWrap: "wrap", marginTop: 2 }}>
                        <span>{it.definitivo!.proveedor}</span>
                        {it.definitivo!.url && (
                          <a href={it.definitivo!.url} target="_blank" rel="noopener noreferrer"
                            style={{ color: "var(--brand)", textDecoration: "none", display: "inline-flex", alignItems: "center", gap: 3 }}>
                            <ExternalLink size={12} strokeWidth={1.75} /> Ver en tienda
                          </a>
                        )}
                        {compra?.boleta_url && (
                          <a href={compra.boleta_url} target="_blank" rel="noopener noreferrer" style={{ color: "var(--brand)", textDecoration: "none" }}>
                            Boleta
                          </a>
                        )}
                      </div>
                    </div>
                    <div style={{ textAlign: "right", fontFamily: "var(--font-mono)", fontVariantNumeric: "tabular-nums" }}>
                      <div style={{ fontSize: 14, fontWeight: 600, color: "var(--n-900)" }}>
                        {compra?.precio_real != null
                          ? fmtCLP(compra.precio_real)
                          : it.definitivo!.precio_clp != null
                            ? fmtCLP(it.definitivo!.precio_clp * (it.cantidad || 1))
                            : "—"}
                      </div>
                      {compra?.precio_real != null && it.definitivo!.precio_clp != null && (
                        <div style={{ fontSize: 11, color: "var(--n-500)" }}>
                          cotizado {fmtCLP(it.definitivo!.precio_clp * (it.cantidad || 1))}
                        </div>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>

            {/* Resumen del último escaneo de boleta */}
            {resultadoBoleta && (
              <SummaryPanel style={{ marginTop: 14 }}>
                <div style={{ fontSize: 13.5, color: "var(--n-700)", marginBottom: 6 }}>
                  Boleta procesada
                  {resultadoBoleta.proveedor ? ` · ${resultadoBoleta.proveedor}` : ""}
                  {resultadoBoleta.total ? ` · Total ${fmtCLP(resultadoBoleta.total)}` : ""}
                </div>
                <div style={{ fontSize: 12.5, color: "var(--n-600)", display: "flex", flexDirection: "column", gap: 3 }}>
                  {resultadoBoleta.items_detectados.map((m, i) => (
                    <div key={i}>
                      {m.cotizacion_id ? "✓" : "○"} {m.nombre_ocr}
                      {m.precio != null ? ` · ${fmtCLP(m.precio)}` : ""}
                      {!m.cotizacion_id && <span style={{ color: "var(--n-500)" }}> (no calzó con la lista)</span>}
                    </div>
                  ))}
                </div>
                <button
                  onClick={() => setResultadoBoleta(null)}
                  style={{ marginTop: 8, background: "none", border: "none", cursor: "pointer",
                    color: "var(--n-500)", fontSize: 12.5, textDecoration: "underline" }}
                >
                  Cerrar
                </button>
              </SummaryPanel>
            )}
          </Card>
        );
      })()}
    </>
  );
}
