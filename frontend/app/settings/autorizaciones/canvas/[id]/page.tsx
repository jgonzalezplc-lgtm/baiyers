"use client";
import { useEffect, useRef, useState, type CSSProperties } from "react";
import { useRouter, useParams } from "next/navigation";
import { ArrowLeft, Trash2, Plus, Link2, CheckCircle2, XCircle } from "lucide-react";
import { createClient } from "@/lib/supabase/client";
import { authFetch } from "@/lib/authFetch";
import { BtnPrimary, BtnSecondary, BtnGhost, Card, Input, SkeletonBox, CascadeWrapper, TypingBubble } from "@/components/ui";
import { ChatBubbles } from "@/components/chat/ChatBubbles";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface Posicion { x: number; y: number }

interface Condicion {
  campo: string;
  operador: string;
  valor: string | number;
}

interface Nodo {
  id: string;
  tipo: string;
  nombre: string;
  roles?: string[];
  resultados?: string[];
  condicion_entrada?: Condicion | null;
  posicion?: Posicion;
  entrada?: string;
  proceso?: string;
}

interface Conexion {
  origen_nodo_id: string;
  destino_nodo_id: string;
  resultado?: string;
}

interface ResponsableInfo {
  id: string;
  nombre: string;
  cargo?: string | null;
  email: string | null;
  telefono?: string | null;
  activo: boolean;
}

interface AsignacionRol {
  id: string;
  rol_clave: string;
  orden_autorizacion: number | null;
  responsables: ResponsableInfo;
}

interface Workflow {
  id: string;
  nombre: string;
  estado: string;
  nodos: Nodo[];
  conexiones: Conexion[];
  roles?: { clave: string; nombre: string }[];
  responsables?: AsignacionRol[];
}

const TIPOS: { valor: string; label: string }[] = [
  { valor: "tarea_humana", label: "Tarea humana" },
  { valor: "revision", label: "Revisión" },
  { valor: "autorizacion", label: "Autorización" },
  { valor: "decision", label: "Decisión / condición" },
  { valor: "accion_automatica", label: "Acción automática" },
  { valor: "homologacion", label: "Homologación" },
  { valor: "emision_oc", label: "Emisión de OC" },
  { valor: "compra_sin_oc", label: "Compra sin OC" },
  { valor: "espera_documento", label: "Espera de documento" },
];

const ROLES_BASE = ["cotizador", "revisor", "autorizador", "comprador"];
const CAMPOS_CONDICION = ["monto_total", "moneda", "categoria", "centro_costo", "proyecto", "proveedor_nuevo", "proveedor_homologado", "requiere_oc"];
const OPERADORES = [">", ">=", "<", "<=", "==", "!=", "in", "not in"];

const NODE_W = 168;
const NODE_H = 60;

const COLOR_RESULTADO: Record<string, string> = {
  aprobado: "var(--success)",
  rechazado: "var(--danger)",
  default: "var(--n-500)",
};

function colorClaveResultado(resultado?: string): string {
  const r = (resultado || "").toLowerCase();
  if (r.includes("aprob")) return "aprobado";
  if (r.includes("rechaz")) return "rechazado";
  return "default";
}

function colorNodo(tipo: string): string {
  if (tipo === "inicio") return "var(--success)";
  if (tipo === "fin") return "var(--n-700)";
  if (tipo === "decision") return "var(--st-cotizando-fg)";
  if (tipo === "autorizacion") return "var(--brand)";
  return "var(--n-500)";
}

function nuevoId(nodos: Nodo[]): string {
  let i = 0;
  const ids = new Set(nodos.map(n => n.id));
  while (ids.has(`n${i}`)) i++;
  return `n${i}`;
}

const COL_W = 240;
const ROW_H = 110;

// Ordena por columnas según la distancia real desde el/los nodos sin
// entradas (normalmente "inicio") — así el flujo queda de izquierda a
// derecha en el mismo orden en que se ejecuta, y las líneas dejan de cruzar
// por encima de tarjetas que no tienen nada que ver con esa conexión.
// Los nodos que el grafo no alcanza (sueltos) quedan en la última columna.
function ordenarPorNiveles(nodos: Nodo[], conexiones: Conexion[]): Nodo[] {
  const idsValidos = new Set(nodos.map(n => n.id));
  const salientes = new Map<string, string[]>();
  const entrantes = new Map<string, number>();
  nodos.forEach(n => { salientes.set(n.id, []); entrantes.set(n.id, 0); });
  conexiones.forEach(c => {
    if (!idsValidos.has(c.origen_nodo_id) || !idsValidos.has(c.destino_nodo_id)) return;
    salientes.get(c.origen_nodo_id)!.push(c.destino_nodo_id);
    entrantes.set(c.destino_nodo_id, (entrantes.get(c.destino_nodo_id) ?? 0) + 1);
  });

  const nivel = new Map<string, number>();
  const raices = nodos.filter(n => (entrantes.get(n.id) ?? 0) === 0).map(n => n.id);
  const cola = raices.length ? [...raices] : nodos.slice(0, 1).map(n => n.id);
  cola.forEach(id => nivel.set(id, 0));
  for (let i = 0; i < cola.length; i++) {
    const actual = cola[i];
    const lv = nivel.get(actual) ?? 0;
    for (const siguiente of salientes.get(actual) || []) {
      if (nivel.get(siguiente) === undefined || nivel.get(siguiente)! < lv + 1) {
        nivel.set(siguiente, lv + 1);
        cola.push(siguiente);
      }
    }
  }
  let maxNivel = 0;
  nivel.forEach(v => { if (v > maxNivel) maxNivel = v; });
  nodos.forEach(n => { if (nivel.get(n.id) === undefined) nivel.set(n.id, maxNivel + 1); });

  const filaPorNivel = new Map<number, number>();
  return nodos.map(n => {
    const lv = nivel.get(n.id)!;
    const fila = filaPorNivel.get(lv) ?? 0;
    filaPorNivel.set(lv, fila + 1);
    return { ...n, posicion: { x: 40 + lv * COL_W, y: 40 + fila * ROW_H } };
  });
}

export default function CanvasWorkflowPage() {
  const router = useRouter();
  const params = useParams();
  const workflowId = params.id as string;

  const [userId, setUserId] = useState<string | null>(null);
  const [workflow, setWorkflow] = useState<Workflow | null>(null);
  const [nodos, setNodos] = useState<Nodo[]>([]);
  const [conexiones, setConexiones] = useState<Conexion[]>([]);
  const [cargando, setCargando] = useState(true);
  const [guardando, setGuardando] = useState(false);
  const [seleccionado, setSeleccionado] = useState<string | null>(null);
  const [conectando, setConectando] = useState<string | null>(null);
  const [errores, setErrores] = useState<{ codigo: string; mensaje: string }[] | null>(null);
  const [activando, setActivando] = useState(false);
  const [toast, setToast] = useState("");
  const [responsablesOrg, setResponsablesOrg] = useState<ResponsableInfo[]>([]);
  const [asignandoRol, setAsignandoRol] = useState<string | null>(null);
  const [nuevoNombre, setNuevoNombre] = useState("");
  const [nuevoEmail, setNuevoEmail] = useState("");
  const [guardandoResponsable, setGuardandoResponsable] = useState(false);

  // Chat de correcciones: le pide al modelo una lista de operaciones sobre
  // el grafo actual (nunca uno nuevo) y las aplica con las mismas funciones
  // que usa la edición manual — nunca guarda solo, sigue haciendo falta
  // apretar "Guardar" para persistir.
  const [mensajesCorreccion, setMensajesCorreccion] = useState<{ rol: "bot" | "user"; texto: string }[]>([
    { rol: "bot", texto: "Cuéntame qué corregir del ciclo — por ejemplo \"agrega que finanzas también autorice sobre 2 millones\"." },
  ]);
  const [entradaCorreccion, setEntradaCorreccion] = useState("");
  const [enviandoCorreccion, setEnviandoCorreccion] = useState(false);

  const arrastre = useRef<{ id: string; offX: number; offY: number } | null>(null);
  const lienzoRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    createClient().auth.getUser().then(({ data }) => setUserId(data.user?.id ?? null));
  }, []);

  const cargarWorkflow = async (uid: string) => {
    const data: Workflow = await fetch(`${API_URL}/api/workflows/${workflowId}?user_id=${uid}`).then(r => r.json());
    setWorkflow(data);
    setNodos(prev => {
      const conPosicion = (data.nodos || []).map((n, i) => {
        const existente = prev.find(p => p.id === n.id);
        return { ...n, posicion: existente?.posicion ?? n.posicion ?? { x: 60 + (i % 3) * 220, y: 40 + Math.floor(i / 3) * 130 } };
      });
      return conPosicion;
    });
    setConexiones(data.conexiones || []);
    return data;
  };

  useEffect(() => {
    if (!userId) return;
    (async () => {
      await cargarWorkflow(userId);
      const org: ResponsableInfo[] = await fetch(`${API_URL}/api/workflows/responsables/listar?user_id=${userId}`).then(r => r.json()).catch(() => []);
      setResponsablesOrg(org || []);
      setCargando(false);
    })();
  }, [userId, workflowId]);

  const asignaciones = workflow?.responsables || [];

  const asignarExistente = async (rol: string, responsableId: string) => {
    if (!userId) return;
    setGuardandoResponsable(true);
    try {
      const res = await fetch(`${API_URL}/api/workflows/responsables/${responsableId}/roles`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user_id: userId, workflow_id: workflowId, rol_clave: rol }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        setToast(body.detail || "No se pudo asignar el responsable");
        setTimeout(() => setToast(""), 3500);
        return;
      }
      await cargarWorkflow(userId);
      setAsignandoRol(null);
      const nombre = responsablesOrg.find(r => r.id === responsableId)?.nombre || "Responsable";
      setToast(`${nombre} asignado a "${rol}"`);
      setTimeout(() => setToast(""), 2500);
    } finally {
      setGuardandoResponsable(false);
    }
  };

  const crearYAsignar = async (rol: string) => {
    if (!userId || !nuevoNombre.trim() || !nuevoEmail.trim()) return;
    setGuardandoResponsable(true);
    try {
      const creado = await fetch(`${API_URL}/api/workflows/responsables`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user_id: userId, nombre: nuevoNombre.trim(), email: nuevoEmail.trim() }),
      }).then(r => r.json());
      await fetch(`${API_URL}/api/workflows/responsables/${creado.id}/roles`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user_id: userId, workflow_id: workflowId, rol_clave: rol }),
      });
      // Fase C: invitación real. Si falla (email ya en otra org, admin gate,
      // etc.) el responsable igual queda creado — mostramos el error al usuario
      // pero no bloqueamos el flujo del workflow.
      let mensajeInvitacion = "";
      try {
        const inv = await fetch(`${API_URL}/api/organizacion/invitar`, {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ user_id: userId, email: nuevoEmail.trim(), responsable_id: creado.id }),
        });
        const invData = await inv.json();
        if (!inv.ok) {
          mensajeInvitacion = `Responsable creado, pero no pudimos invitar: ${invData.detail || "error desconocido"}`;
        } else if (invData.estado === "ya_miembro") {
          mensajeInvitacion = `${nuevoEmail.trim()} ya es miembro de la organización.`;
        } else {
          mensajeInvitacion = `Invitación enviada a ${nuevoEmail.trim()}.`;
        }
      } catch (e) {
        mensajeInvitacion = `Responsable creado, pero no pudimos enviar la invitación (${(e as Error).message}).`;
      }
      setToast(mensajeInvitacion);
      setTimeout(() => setToast(""), 4500);
      const org: ResponsableInfo[] = await fetch(`${API_URL}/api/workflows/responsables/listar?user_id=${userId}`).then(r => r.json()).catch(() => []);
      setResponsablesOrg(org || []);
      await cargarWorkflow(userId);
      setAsignandoRol(null); setNuevoNombre(""); setNuevoEmail("");
    } finally {
      setGuardandoResponsable(false);
    }
  };

  const quitarAsignacion = async (rol: string, responsableId: string) => {
    if (!userId) return;
    setGuardandoResponsable(true);
    try {
      await fetch(`${API_URL}/api/workflows/responsables/${responsableId}/roles/${workflowId}/${rol}?user_id=${userId}`, { method: "DELETE" });
      await cargarWorkflow(userId);
    } finally {
      setGuardandoResponsable(false);
    }
  };

  const nodoSel = nodos.find(n => n.id === seleccionado) || null;

  const actualizarNodo = (id: string, cambios: Partial<Nodo>) => {
    setNodos(prev => prev.map(n => (n.id === id ? { ...n, ...cambios } : n)));
  };

  const agregarNodo = (tipo: string) => {
    const id = nuevoId(nodos);
    const label = TIPOS.find(t => t.valor === tipo)?.label || tipo;
    const nuevo: Nodo = {
      id, tipo, nombre: label,
      posicion: { x: 60 + (nodos.length % 3) * 220, y: 40 + Math.floor(nodos.length / 3) * 130 },
      ...(tipo === "decision" || tipo === "autorizacion" ? { resultados: ["aprobado", "rechazado"] } : {}),
      ...(["tarea_humana", "revision", "autorizacion", "homologacion"].includes(tipo) ? { roles: [] } : {}),
    };
    setNodos(prev => [...prev, nuevo]);
    setSeleccionado(id);
  };

  const eliminarNodo = (id: string) => {
    setNodos(prev => prev.filter(n => n.id !== id));
    setConexiones(prev => prev.filter(c => c.origen_nodo_id !== id && c.destino_nodo_id !== id));
    if (seleccionado === id) setSeleccionado(null);
  };

  // Punto de salida (derecha de la tarjeta): arma el origen de una conexión
  // nueva. Nunca termina una conexión — eso es solo el punto de entrada, así
  // no hay ambigüedad sobre qué extremo se está tocando.
  const iniciarConexionDesde = (id: string) => {
    const nodo = nodos.find(n => n.id === id);
    if (nodo?.tipo === "fin") return;
    setConectando(prev => (prev === id ? null : id));
  };

  // Punto de entrada (izquierda de la tarjeta): solo hace algo si ya hay una
  // conexión armada desde otro nodo — nunca inicia una conexión por sí solo,
  // así arrastrar/clickear el lado equivocado no puede pisar otra conexión.
  const completarConexionHacia = (id: string) => {
    if (!conectando || conectando === id) { setConectando(null); return; }
    const destinoNodo = nodos.find(n => n.id === id);
    if (destinoNodo?.tipo === "inicio") { setConectando(null); return; }

    const origenNodo = nodos.find(n => n.id === conectando);
    const necesitaResultado = !!origenNodo?.resultados?.length;
    let resultado: string | undefined;
    if (necesitaResultado) {
      const opciones = origenNodo!.resultados || [];
      const elegido = window.prompt(`¿Con qué resultado va esta conexión? (${opciones.join(", ")})`, opciones[0] || "");
      if (!elegido) { setConectando(null); return; }
      resultado = elegido;
    }
    setConexiones(prev => [
      ...prev.filter(c => !(c.origen_nodo_id === conectando && (c.resultado || "default") === (resultado || "default"))),
      { origen_nodo_id: conectando, destino_nodo_id: id, ...(resultado ? { resultado } : {}) },
    ]);
    setConectando(null);
  };

  const eliminarConexion = (idx: number) => {
    setConexiones(prev => prev.filter((_, i) => i !== idx));
  };

  const onMouseDownNodo = (e: React.MouseEvent, n: Nodo) => {
    if (conectando) return;
    const rect = lienzoRef.current?.getBoundingClientRect();
    if (!rect) return;
    arrastre.current = {
      id: n.id,
      offX: e.clientX - rect.left - (n.posicion?.x ?? 0),
      offY: e.clientY - rect.top - (n.posicion?.y ?? 0),
    };
    setSeleccionado(n.id);
  };

  const onMouseMove = (e: React.MouseEvent) => {
    if (!arrastre.current) return;
    const rect = lienzoRef.current?.getBoundingClientRect();
    if (!rect) return;
    const x = Math.max(0, e.clientX - rect.left - arrastre.current.offX);
    const y = Math.max(0, e.clientY - rect.top - arrastre.current.offY);
    actualizarNodo(arrastre.current.id, { posicion: { x, y } });
  };

  const onMouseUp = () => { arrastre.current = null; };

  const guardar = async () => {
    if (!userId) return;
    setGuardando(true);
    setErrores(null);
    try {
      await fetch(`${API_URL}/api/workflows/${workflowId}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user_id: userId, nodos, conexiones }),
      });
      setToast("Guardado");
      setTimeout(() => setToast(""), 2500);
    } catch {
      setToast("No se pudo guardar");
      setTimeout(() => setToast(""), 3000);
    } finally {
      setGuardando(false);
    }
  };

  const validar = async () => {
    if (!userId) return;
    await guardar();
    const data = await authFetch(`${API_URL}/api/workflows/${workflowId}/validar`).then(r => r.json());
    setErrores(data.errores || []);
  };

  const activar = async () => {
    if (!userId) return;
    setActivando(true);
    await guardar();
    try {
      const val = await authFetch(`${API_URL}/api/workflows/${workflowId}/validar`).then(r => r.json());
      setErrores(val.errores || []);
      if (!val.valido) return;
      await authFetch(`${API_URL}/api/workflows/${workflowId}/activar`, {
        method: "POST",
      });
      setWorkflow(prev => prev ? { ...prev, estado: "activo" } : prev);
      setToast("Ciclo activado");
      setTimeout(() => setToast(""), 2500);
    } finally {
      setActivando(false);
    }
  };

  const aplicarOperacion = (op: Record<string, unknown>) => {
    const tipo = op.tipo as string;
    if (tipo === "renombrar_nodo") {
      actualizarNodo(op.nodo_id as string, { nombre: op.nombre as string });
    } else if (tipo === "cambiar_roles") {
      actualizarNodo(op.nodo_id as string, { roles: op.roles as string[] });
    } else if (tipo === "cambiar_entrada") {
      actualizarNodo(op.nodo_id as string, { entrada: op.entrada as string });
    } else if (tipo === "cambiar_proceso") {
      actualizarNodo(op.nodo_id as string, { proceso: op.proceso as string });
    } else if (tipo === "cambiar_condicion_entrada") {
      actualizarNodo(op.nodo_id as string, { condicion_entrada: op.condicion_entrada as Condicion });
    } else if (tipo === "agregar_nodo") {
      const id = nuevoId(nodos);
      const nuevo: Nodo = {
        id, tipo: op.tipo_nodo as string, nombre: op.nombre as string,
        posicion: { x: 60 + (nodos.length % 3) * 220, y: 40 + Math.floor(nodos.length / 3) * 130 },
        ...(op.tipo_nodo === "decision" || op.tipo_nodo === "autorizacion" ? { resultados: ["aprobado", "rechazado"] } : {}),
        ...(op.roles ? { roles: op.roles as string[] } : {}),
      };
      setNodos(prev => [...prev, nuevo]);
    } else if (tipo === "eliminar_nodo") {
      eliminarNodo(op.nodo_id as string);
    } else if (tipo === "conectar") {
      const resultado = op.resultado as string | undefined;
      setConexiones(prev => [
        ...prev.filter(c => !(c.origen_nodo_id === op.origen_nodo_id && (c.resultado || "default") === (resultado || "default"))),
        { origen_nodo_id: op.origen_nodo_id as string, destino_nodo_id: op.destino_nodo_id as string, ...(resultado ? { resultado } : {}) },
      ]);
    } else if (tipo === "desconectar") {
      const resultado = op.resultado as string | undefined;
      setConexiones(prev => prev.filter(c => !(
        c.origen_nodo_id === op.origen_nodo_id && c.destino_nodo_id === op.destino_nodo_id
        && (resultado ? c.resultado === resultado : true)
      )));
    }
  };

  const enviarCorreccion = async () => {
    const texto = entradaCorreccion.trim();
    if (!texto || enviandoCorreccion || !userId) return;
    setEntradaCorreccion("");
    setMensajesCorreccion(prev => [...prev, { rol: "user", texto }]);
    setEnviandoCorreccion(true);
    try {
      const contexto = mensajesCorreccion.map(m => `${m.rol === "bot" ? "ASISTENTE" : "USUARIO"}: ${m.texto}`).join("\n");
      const res = await authFetch(`${API_URL}/api/workflows/${workflowId}/interpretar-correccion`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ descripcion: texto, grafo_actual: { nodos, conexiones }, contexto }),
        signal: AbortSignal.timeout(30000),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      if (data.requiere_aclaracion) {
        const pregunta = (data.preguntas || []).join(" ") || "¿Puedes darme un poco más de detalle?";
        setMensajesCorreccion(prev => [...prev, { rol: "bot", texto: pregunta }]);
      } else {
        (data.operaciones || []).forEach(aplicarOperacion);
        setErrores(null);
        setMensajesCorreccion(prev => [...prev, {
          rol: "bot",
          texto: (data.resumen || "Listo, apliqué el cambio.") + " Recuerda apretar \"Guardar\" para que quede persistido.",
        }]);
      }
    } catch {
      setMensajesCorreccion(prev => [...prev, { rol: "bot", texto: "Tuve un problema interpretando eso. No cambié nada; intenta de nuevo." }]);
    } finally {
      setEnviandoCorreccion(false);
    }
  };

  if (cargando) return (
    <div>
      <SkeletonBox height={13} width={120} style={{ marginBottom: 12 }} />
      <SkeletonBox height={20} width={220} style={{ marginBottom: 14 }} />
      <div style={{ display: "flex", gap: 14 }}>
        <Card padding={14} style={{ width: 190, flexShrink: 0 }}>
          <CascadeWrapper>
            {Array.from({ length: 9 }).map((_, i) => <SkeletonBox key={i} height={28} width="100%" style={{ marginBottom: 6 }} />)}
          </CascadeWrapper>
        </Card>
        <div style={{ position: "relative", flex: 1, minHeight: 560, background: "var(--canvas)", border: "1px solid var(--n-200)", borderRadius: "var(--r-md)" }}>
          <CascadeWrapper>
            <SkeletonBox width={168} height={60} style={{ position: "absolute", left: 60, top: 40 }} />
            <SkeletonBox width={168} height={60} style={{ position: "absolute", left: 300, top: 40 }} />
            <SkeletonBox width={168} height={60} style={{ position: "absolute", left: 540, top: 40 }} />
          </CascadeWrapper>
        </div>
        <Card padding={16} style={{ width: 240, flexShrink: 0 }}>
          <SkeletonBox height={13} width="60%" />
        </Card>
      </div>
    </div>
  );
  if (!workflow) return <div>No se encontró el workflow.</div>;

  const centro = (n: Nodo) => ({
    x: (n.posicion?.x ?? 0) + NODE_W / 2,
    y: (n.posicion?.y ?? 0) + NODE_H / 2,
  });

  // Punto donde una línea desde `centroPropio` hacia `haciaDonde` cruza el
  // borde de la tarjeta (nunca su interior) — así la flecha siempre "sale" o
  // "entra" por el perímetro real, sea cual sea la posición relativa de la
  // otra tarjeta, en vez de un punto fijo izquierda/derecha que corta en
  // diagonal por encima de tarjetas sin relación con esa conexión.
  const bordeHacia = (centroPropio: { x: number; y: number }, haciaDonde: { x: number; y: number }) => {
    const dx = haciaDonde.x - centroPropio.x;
    const dy = haciaDonde.y - centroPropio.y;
    if (dx === 0 && dy === 0) return centroPropio;
    const hw = NODE_W / 2, hh = NODE_H / 2;
    const escala = 1 / Math.max(Math.abs(dx) / hw, Math.abs(dy) / hh);
    return { x: centroPropio.x + dx * escala, y: centroPropio.y + dy * escala };
  };

  return (
    <div>
      {toast && (
        <div style={{
          position: "fixed", top: 20, right: 20, background: "var(--n-900)", color: "var(--canvas)",
          padding: "11px 16px", borderRadius: "var(--r-md)", fontSize: 13.5, fontWeight: 500, zIndex: 100,
        }}>{toast}</div>
      )}

      <button onClick={() => router.push("/settings/autorizaciones")} style={{ border: 0, background: "none", color: "var(--n-600)", cursor: "pointer", display: "inline-flex", alignItems: "center", gap: 6, marginBottom: 12, fontSize: 13.5 }}>
        <ArrowLeft size={16} /> Configuración
      </button>

      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 14 }}>
        <div>
          <h1 style={{ fontSize: 20, fontWeight: 600, color: "var(--n-900)", margin: "0 0 2px" }}>{workflow.nombre}</h1>
          <p style={{ fontSize: 13, color: "var(--n-600)", margin: 0 }}>
            {workflow.estado === "activo" ? "Ciclo activo" : "Borrador"} · arrastra los nodos; conecta desde el punto de salida (derecha) hacia el punto de entrada (izquierda) de otro nodo
          </p>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <BtnSecondary onClick={() => setNodos(prev => ordenarPorNiveles(prev, conexiones))} disabled={guardando}>Ordenar automáticamente</BtnSecondary>
          <BtnSecondary onClick={validar} disabled={guardando}>Validar</BtnSecondary>
          <BtnSecondary onClick={guardar} disabled={guardando}>{guardando ? "Guardando…" : "Guardar"}</BtnSecondary>
          {workflow.estado !== "activo" && (
            <BtnPrimary onClick={activar} disabled={activando}>{activando ? "Activando…" : "Activar"}</BtnPrimary>
          )}
        </div>
      </div>

      {errores && (
        <Card padding={14} style={{ marginBottom: 14, borderColor: errores.length ? "var(--danger)" : "var(--success)" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: errores.length ? 8 : 0 }}>
            {errores.length === 0 ? <CheckCircle2 size={17} color="var(--success)" /> : <XCircle size={17} color="var(--danger)" />}
            <strong style={{ fontSize: 13.5, color: "var(--n-900)" }}>
              {errores.length === 0 ? "Grafo válido" : `${errores.length} problema(s) de validación`}
            </strong>
          </div>
          {errores.length > 0 && (
            <ul style={{ margin: 0, paddingLeft: 20, fontSize: 13, color: "var(--danger)" }}>
              {errores.map((e, i) => <li key={i}>{e.mensaje}</li>)}
            </ul>
          )}
        </Card>
      )}

      <div style={{ display: "flex", gap: 14 }}>
        {/* Paleta */}
        <Card padding={14} style={{ width: 190, flexShrink: 0, alignSelf: "flex-start" }}>
          <div style={{ fontSize: 12, fontWeight: 600, color: "var(--n-600)", marginBottom: 10, textTransform: "uppercase", letterSpacing: 0.3 }}>Agregar nodo</div>
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            {TIPOS.map(t => (
              <button key={t.valor} onClick={() => agregarNodo(t.valor)} style={{
                display: "flex", alignItems: "center", gap: 6, textAlign: "left",
                background: "var(--surface)", border: "1px solid var(--n-200)", borderRadius: "var(--r-sm)",
                padding: "7px 9px", fontSize: 12.5, color: "var(--n-800)", cursor: "pointer",
              }}>
                <Plus size={13} /> {t.label}
              </button>
            ))}
          </div>
        </Card>

        {/* Lienzo */}
        <div
          ref={lienzoRef}
          onMouseMove={onMouseMove}
          onMouseUp={onMouseUp}
          onMouseLeave={onMouseUp}
          style={{
            position: "relative", flex: 1, minHeight: 560, background: "var(--canvas)",
            border: "1px solid var(--n-200)", borderRadius: "var(--r-md)", overflow: "auto",
            backgroundImage: "radial-gradient(var(--n-200) 1px, transparent 1px)", backgroundSize: "16px 16px",
          }}
        >
          <svg style={{ position: "absolute", top: 0, left: 0, width: "100%", height: "100%", pointerEvents: "none" }}>
            <defs>
              {Object.entries(COLOR_RESULTADO).map(([clave, color]) => (
                <marker key={clave} id={`flecha-${clave}`} markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto">
                  <path d="M0,0 L8,4 L0,8 z" fill={color} />
                </marker>
              ))}
            </defs>
            {conexiones.map((c, i) => {
              const o = nodos.find(n => n.id === c.origen_nodo_id);
              const d = nodos.find(n => n.id === c.destino_nodo_id);
              if (!o || !d) return null;
              const centroO = centro(o), centroD = centro(d);
              const p1 = bordeHacia(centroO, centroD), p2 = bordeHacia(centroD, centroO);
              const mx = (p1.x + p2.x) / 2;
              const clave = colorClaveResultado(c.resultado);
              const color = COLOR_RESULTADO[clave];
              return (
                <g key={i}>
                  <line x1={p1.x} y1={p1.y} x2={p2.x} y2={p2.y} stroke={color} strokeWidth={1.5} markerEnd={`url(#flecha-${clave})`} />
                  {c.resultado && (
                    <text x={mx} y={(p1.y + p2.y) / 2 - 4} fontSize={11} fontWeight={600} fill={color} textAnchor="middle" style={{ fontFamily: "var(--font-sans)" }}>
                      {c.resultado}
                    </text>
                  )}
                  <circle cx={mx} cy={(p1.y + p2.y) / 2} r={8} fill="transparent" pointerEvents="all" style={{ cursor: "pointer" }} onClick={() => eliminarConexion(i)} />
                </g>
              );
            })}
          </svg>

          {nodos.map(n => {
            const activo = seleccionado === n.id;
            const enConexion = conectando === n.id;
            const style: CSSProperties = {
              position: "absolute", left: n.posicion?.x ?? 0, top: n.posicion?.y ?? 0,
              width: NODE_W, minHeight: NODE_H, padding: "8px 10px",
              background: "var(--surface)", borderRadius: "var(--r-md)",
              border: `2px solid ${enConexion ? "var(--brand)" : activo ? colorNodo(n.tipo) : "var(--n-300)"}`,
              boxShadow: activo ? "var(--shadow-pop)" : "var(--shadow-card)",
              cursor: "grab", userSelect: "none",
            };
            return (
              <div key={n.id} style={style} onMouseDown={e => onMouseDownNodo(e, n)}>
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 4 }}>
                  <span style={{ width: 7, height: 7, borderRadius: "50%", background: colorNodo(n.tipo), flexShrink: 0 }} />
                  <span style={{ fontSize: 12.5, fontWeight: 600, color: "var(--n-900)", flex: 1, lineHeight: 1.3 }}>{n.nombre}</span>
                  {n.tipo !== "inicio" && n.tipo !== "fin" && (
                    <button onMouseDown={e => e.stopPropagation()} onClick={() => eliminarNodo(n.id)} style={{ border: 0, background: "none", cursor: "pointer", color: "var(--n-400)", padding: 0 }}>
                      <Trash2 size={12} />
                    </button>
                  )}
                </div>
                <div style={{ fontSize: 10.5, color: "var(--n-500)", marginTop: 3 }}>
                  {n.roles && n.roles.length > 0 ? n.roles.join(", ") : TIPOS.find(t => t.valor === n.tipo)?.label ?? n.tipo}
                </div>
                {n.tipo !== "inicio" && (
                  <button
                    onMouseDown={e => e.stopPropagation()}
                    onClick={() => completarConexionHacia(n.id)}
                    title={conectando && conectando !== n.id ? "Conectar aquí (entrada)" : "Entrada"}
                    style={{
                      position: "absolute", left: -8, top: "50%", transform: "translateY(-50%)",
                      width: 14, height: 14, borderRadius: "50%",
                      border: `1.5px solid ${conectando && conectando !== n.id ? "var(--brand)" : "var(--n-300)"}`,
                      background: conectando && conectando !== n.id ? "var(--brand-50)" : "var(--canvas)",
                      cursor: conectando && conectando !== n.id ? "pointer" : "default", padding: 0,
                    }}
                  />
                )}
                {n.tipo !== "fin" && (
                  <button
                    onMouseDown={e => e.stopPropagation()}
                    onClick={() => iniciarConexionDesde(n.id)}
                    title="Salida — clic para empezar una conexión"
                    style={{
                      position: "absolute", right: -10, top: "50%", transform: "translateY(-50%)",
                      width: 20, height: 20, borderRadius: "50%", border: "1px solid var(--n-300)",
                      background: enConexion ? "var(--brand)" : "var(--canvas)", color: enConexion ? "#fff" : "var(--n-600)",
                      display: "flex", alignItems: "center", justifyContent: "center", cursor: "pointer", padding: 0,
                    }}
                  >
                    <Link2 size={11} />
                  </button>
                )}
              </div>
            );
          })}
        </div>

        {/* Panel de propiedades */}
        <Card padding={16} style={{ width: 240, flexShrink: 0, alignSelf: "flex-start" }}>
          {!nodoSel ? (
            <div style={{ fontSize: 13, color: "var(--n-500)" }}>Selecciona un nodo para editarlo.</div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
              <Input label="Nombre" value={nodoSel.nombre} onChange={e => actualizarNodo(nodoSel.id, { nombre: e.target.value })} />

              {nodoSel.tipo !== "inicio" && nodoSel.tipo !== "fin" && (
                <>
                  <Input
                    label="Entrada (qué recibe esta etapa)"
                    value={nodoSel.entrada || ""}
                    onChange={e => actualizarNodo(nodoSel.id, { entrada: e.target.value })}
                    placeholder="Ej: la lista de ítems con sus definitivos"
                  />
                  <Input
                    label="Qué debe hacer"
                    value={nodoSel.proceso || ""}
                    onChange={e => actualizarNodo(nodoSel.id, { proceso: e.target.value })}
                    placeholder="Ej: revisar y decidir si autoriza la compra"
                  />
                </>
              )}

              {["tarea_humana", "revision", "autorizacion", "homologacion"].includes(nodoSel.tipo) && (
                <div>
                  <div style={{ fontSize: 12, fontWeight: 600, color: "var(--n-600)", marginBottom: 6 }}>Roles</div>
                  <div style={{ display: "flex", flexWrap: "wrap", gap: 5 }}>
                    {ROLES_BASE.map(r => {
                      const activo = (nodoSel.roles || []).includes(r);
                      return (
                        <button key={r} onClick={() => {
                          const roles = activo ? (nodoSel.roles || []).filter(x => x !== r) : [...(nodoSel.roles || []), r];
                          actualizarNodo(nodoSel.id, { roles });
                        }} style={{
                          fontSize: 11.5, padding: "4px 8px", borderRadius: "var(--r-sm)",
                          border: `1px solid ${activo ? "var(--brand)" : "var(--n-300)"}`,
                          background: activo ? "var(--brand-50)" : "var(--surface)",
                          color: activo ? "var(--brand)" : "var(--n-700)", cursor: "pointer",
                        }}>{r}</button>
                      );
                    })}
                  </div>
                </div>
              )}

              {["tarea_humana", "revision", "autorizacion", "homologacion"].includes(nodoSel.tipo) && (nodoSel.roles || []).map(rol => {
                const asignados = asignaciones.filter(a => a.rol_clave === rol);
                const disponibles = responsablesOrg.filter(r => r.activo && !asignados.some(a => a.responsables?.id === r.id));
                return (
                  <div key={rol}>
                    <div style={{ fontSize: 11.5, fontWeight: 600, color: "var(--n-600)", marginBottom: 6 }}>Responsables de &quot;{rol}&quot;</div>
                    <div style={{ display: "flex", flexDirection: "column", gap: 5, marginBottom: 6 }}>
                      {asignados.length === 0 && <div style={{ fontSize: 11.5, color: "var(--n-500)" }}>Nadie asignado todavía.</div>}
                      {asignados.map(a => (
                        <div key={a.id} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 6, fontSize: 11.5, padding: "4px 7px", background: "var(--surface-2)", borderRadius: "var(--r-sm)" }}>
                          <span>{a.responsables?.nombre} <span style={{ color: "var(--n-500)" }}>· {a.responsables?.email}</span></span>
                          <button onClick={() => quitarAsignacion(rol, a.responsables.id)} disabled={guardandoResponsable} style={{ border: 0, background: "none", color: "var(--n-400)", cursor: "pointer", padding: 0, flexShrink: 0 }}>
                            <Trash2 size={11} />
                          </button>
                        </div>
                      ))}
                    </div>
                    {asignandoRol === rol ? (
                      <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
                        {disponibles.length > 0 && (
                          <>
                            <select
                              defaultValue=""
                              disabled={guardandoResponsable}
                              onChange={e => { if (e.target.value) asignarExistente(rol, e.target.value); }}
                              style={{ width: "100%", padding: "5px 6px", fontSize: 11.5, borderRadius: "var(--r-sm)", border: "1px solid var(--n-300)", background: "var(--surface)", color: "var(--n-900)" }}
                            >
                              <option value="">Elegir existente…</option>
                              {disponibles.map(r => <option key={r.id} value={r.id}>{r.nombre} · {r.email}</option>)}
                            </select>
                            <div style={{ fontSize: 10, color: "var(--n-500)", marginTop: -2 }}>Se asigna al instante, no hace falta llenar nada más abajo.</div>
                          </>
                        )}
                        <div style={{ fontSize: 10.5, color: "var(--n-500)", marginTop: 4 }}>o crear uno nuevo:</div>
                        <input placeholder="Nombre" value={nuevoNombre} onChange={e => setNuevoNombre(e.target.value)} style={{ padding: "5px 6px", fontSize: 11.5, borderRadius: "var(--r-sm)", border: "1px solid var(--n-300)", background: "var(--surface)", color: "var(--n-900)" }} />
                        <input placeholder="Email" type="email" value={nuevoEmail} onChange={e => setNuevoEmail(e.target.value)} style={{ padding: "5px 6px", fontSize: 11.5, borderRadius: "var(--r-sm)", border: "1px solid var(--n-300)", background: "var(--surface)", color: "var(--n-900)" }} />
                        <div style={{ display: "flex", gap: 5 }}>
                          <BtnGhost onClick={() => { setAsignandoRol(null); setNuevoNombre(""); setNuevoEmail(""); }} size="sm">Cancelar</BtnGhost>
                          <BtnPrimary onClick={() => crearYAsignar(rol)} disabled={!nuevoNombre.trim() || !nuevoEmail.trim() || guardandoResponsable} size="sm">Crear y asignar</BtnPrimary>
                        </div>
                      </div>
                    ) : (
                      <button onClick={() => setAsignandoRol(rol)} style={{ display: "inline-flex", alignItems: "center", gap: 4, border: 0, background: "none", color: "var(--brand)", fontSize: 11.5, cursor: "pointer", padding: 0 }}>
                        <Plus size={11} /> Agregar responsable
                      </button>
                    )}
                  </div>
                );
              })}

              {nodoSel.tipo !== "inicio" && nodoSel.tipo !== "fin" && (
                <div>
                  <div style={{ fontSize: 12, fontWeight: 600, color: "var(--n-600)", marginBottom: 4 }}>
                    {nodoSel.tipo === "decision" || nodoSel.tipo === "autorizacion"
                      ? "Ramas de decisión"
                      : <>Ramas de decisión <span style={{ fontWeight: 400, color: "var(--n-500)" }}>· opcional</span></>}
                  </div>
                  <div style={{ fontSize: 10.5, color: "var(--n-500)", marginBottom: 6, lineHeight: 1.4 }}>
                    Solo si esta etapa se ramifica en varios caminos alternativos (ej: aprobado / rechazado).
                    Cada rama necesita una flecha de salida hacia otro nodo. Si el flujo simplemente
                    continúa al siguiente paso, <strong>dejalo vacío</strong>. No uses este campo
                    para describir qué datos produce la etapa (para eso está &quot;Qué debe hacer&quot;).
                  </div>
                  <Input
                    value={(nodoSel.resultados || []).join(", ")}
                    onChange={e => actualizarNodo(nodoSel.id, { resultados: e.target.value.split(",").map(s => s.trim()).filter(Boolean) })}
                    placeholder={nodoSel.tipo === "decision" || nodoSel.tipo === "autorizacion" ? "aprobado, rechazado" : "vacío = una sola salida"}
                  />
                  {nodoSel.tipo === "autorizacion" && (
                    <div style={{ fontSize: 10.5, color: "var(--n-500)", marginTop: 4, lineHeight: 1.4 }}>
                      El motor real hoy solo distingue aprobado/rechazado (&quot;con observaciones&quot; ya existe como variante de aprobado en el correo de autorización). Salidas adicionales quedan documentadas en el grafo pero no cambian el ruteo todavía.
                    </div>
                  )}
                  {!["decision", "autorizacion"].includes(nodoSel.tipo) && (nodoSel.resultados || []).length > 0 && (
                    <div style={{ fontSize: 10.5, color: "var(--n-500)", marginTop: 4, lineHeight: 1.4 }}>
                      Esta etapa todavía no tiene ejecución real conectada (solo el paso de autorización la tiene) — las ramas quedan como documentación del proceso y validan el grafo.
                    </div>
                  )}
                </div>
              )}

              {nodoSel.tipo === "decision" && (
                <div>
                  <div style={{ fontSize: 12, fontWeight: 600, color: "var(--n-600)", marginBottom: 6 }}>Condición</div>
                  <select
                    value={nodoSel.condicion_entrada?.campo ?? ""}
                    onChange={e => actualizarNodo(nodoSel.id, { condicion_entrada: { campo: e.target.value, operador: nodoSel.condicion_entrada?.operador ?? ">", valor: nodoSel.condicion_entrada?.valor ?? "" } })}
                    style={{ width: "100%", padding: "7px 8px", fontSize: 12.5, borderRadius: "var(--r-sm)", border: "1px solid var(--n-300)", background: "var(--surface)", color: "var(--n-900)", marginBottom: 6 }}
                  >
                    <option value="">Sin condición</option>
                    {CAMPOS_CONDICION.map(c => <option key={c} value={c}>{c}</option>)}
                  </select>
                  {nodoSel.condicion_entrada?.campo && (
                    <div style={{ display: "flex", gap: 6 }}>
                      <select
                        value={nodoSel.condicion_entrada?.operador ?? ">"}
                        onChange={e => actualizarNodo(nodoSel.id, { condicion_entrada: { ...nodoSel.condicion_entrada!, operador: e.target.value } })}
                        style={{ flex: 1, padding: "7px 8px", fontSize: 12.5, borderRadius: "var(--r-sm)", border: "1px solid var(--n-300)", background: "var(--surface)", color: "var(--n-900)" }}
                      >
                        {OPERADORES.map(o => <option key={o} value={o}>{o}</option>)}
                      </select>
                      <input
                        value={String(nodoSel.condicion_entrada?.valor ?? "")}
                        onChange={e => actualizarNodo(nodoSel.id, { condicion_entrada: { ...nodoSel.condicion_entrada!, valor: e.target.value } })}
                        style={{ flex: 1, padding: "7px 8px", fontSize: 12.5, borderRadius: "var(--r-sm)", border: "1px solid var(--n-300)", background: "var(--surface)", color: "var(--n-900)" }}
                      />
                    </div>
                  )}
                </div>
              )}

              <BtnGhost onClick={() => setSeleccionado(null)} size="sm">Cerrar</BtnGhost>
            </div>
          )}
        </Card>

        {/* Chat de correcciones */}
        <Card padding={14} style={{ width: 260, flexShrink: 0, display: "flex", flexDirection: "column", height: 560 }}>
          <div style={{ fontSize: 12, fontWeight: 600, color: "var(--n-600)", marginBottom: 10, textTransform: "uppercase", letterSpacing: 0.3 }}>
            Corregir por chat
          </div>
          <div style={{ flex: 1, overflowY: "auto", display: "flex", flexDirection: "column", gap: 10, marginBottom: 10 }}>
            <ChatBubbles mensajes={mensajesCorreccion} />
            {enviandoCorreccion && <TypingBubble />}
          </div>
          <div style={{ display: "flex", gap: 6 }}>
            <textarea
              value={entradaCorreccion}
              onChange={e => setEntradaCorreccion(e.target.value)}
              onKeyDown={e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); enviarCorreccion(); } }}
              placeholder="Escribe una corrección…"
              rows={2}
              disabled={enviandoCorreccion}
              style={{
                flex: 1, resize: "none", background: "var(--surface)", color: "var(--n-900)",
                border: "1px solid var(--n-300)", borderRadius: "var(--r-md)", padding: 8,
                fontFamily: "inherit", fontSize: 12.5, lineHeight: 1.4, outline: "none",
              }}
            />
            <BtnPrimary onClick={enviarCorreccion} disabled={!entradaCorreccion.trim() || enviandoCorreccion} style={{ alignSelf: "flex-end" }} size="sm">
              Enviar
            </BtnPrimary>
          </div>
        </Card>
      </div>
    </div>
  );
}
