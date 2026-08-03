"use client";
import { useEffect, useRef, useState, type CSSProperties } from "react";
import { useRouter, useParams } from "next/navigation";
import { ArrowLeft, Trash2, Plus, Link2, CheckCircle2, XCircle } from "lucide-react";
import { createClient } from "@/lib/supabase/client";
import { BtnPrimary, BtnSecondary, BtnGhost, Card, Input, Spinner } from "@/components/ui";

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
      await fetch(`${API_URL}/api/workflows/responsables/${responsableId}/roles`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user_id: userId, workflow_id: workflowId, rol_clave: rol }),
      });
      await cargarWorkflow(userId);
      setAsignandoRol(null);
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

  const iniciarConexion = (id: string) => {
    if (conectando === id) { setConectando(null); return; }
    if (conectando) {
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
    } else {
      setConectando(id);
    }
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
    const data = await fetch(`${API_URL}/api/workflows/${workflowId}/validar?user_id=${userId}`).then(r => r.json());
    setErrores(data.errores || []);
  };

  const activar = async () => {
    if (!userId) return;
    setActivando(true);
    await guardar();
    try {
      const val = await fetch(`${API_URL}/api/workflows/${workflowId}/validar?user_id=${userId}`).then(r => r.json());
      setErrores(val.errores || []);
      if (!val.valido) return;
      await fetch(`${API_URL}/api/workflows/${workflowId}/activar`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user_id: userId }),
      });
      setWorkflow(prev => prev ? { ...prev, estado: "activo" } : prev);
      setToast("Ciclo activado");
      setTimeout(() => setToast(""), 2500);
    } finally {
      setActivando(false);
    }
  };

  if (cargando) return <Spinner label="Cargando workflow…" />;
  if (!workflow) return <div>No se encontró el workflow.</div>;

  const centro = (n: Nodo) => ({
    x: (n.posicion?.x ?? 0) + NODE_W / 2,
    y: (n.posicion?.y ?? 0) + NODE_H / 2,
  });

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
            {workflow.estado === "activo" ? "Ciclo activo" : "Borrador"} · arrastra los nodos, usa el ícono de enlace para conectar
          </p>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
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
              <marker id="flecha" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto">
                <path d="M0,0 L8,4 L0,8 z" fill="var(--n-500)" />
              </marker>
            </defs>
            {conexiones.map((c, i) => {
              const o = nodos.find(n => n.id === c.origen_nodo_id);
              const d = nodos.find(n => n.id === c.destino_nodo_id);
              if (!o || !d) return null;
              const p1 = centro(o), p2 = centro(d);
              const mx = (p1.x + p2.x) / 2;
              return (
                <g key={i}>
                  <line x1={p1.x} y1={p1.y} x2={p2.x} y2={p2.y} stroke="var(--n-500)" strokeWidth={1.5} markerEnd="url(#flecha)" />
                  {c.resultado && (
                    <text x={mx} y={(p1.y + p2.y) / 2 - 4} fontSize={11} fill="var(--n-700)" textAnchor="middle" style={{ fontFamily: "var(--font-sans)" }}>
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
                <button
                  onMouseDown={e => e.stopPropagation()}
                  onClick={() => iniciarConexion(n.id)}
                  title="Conectar desde aquí"
                  style={{
                    position: "absolute", right: -10, top: "50%", transform: "translateY(-50%)",
                    width: 20, height: 20, borderRadius: "50%", border: "1px solid var(--n-300)",
                    background: enConexion ? "var(--brand)" : "var(--canvas)", color: enConexion ? "#fff" : "var(--n-600)",
                    display: "flex", alignItems: "center", justifyContent: "center", cursor: "pointer", padding: 0,
                  }}
                >
                  <Link2 size={11} />
                </button>
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
                          <select
                            defaultValue=""
                            onChange={e => { if (e.target.value) asignarExistente(rol, e.target.value); }}
                            style={{ width: "100%", padding: "5px 6px", fontSize: 11.5, borderRadius: "var(--r-sm)", border: "1px solid var(--n-300)", background: "var(--surface)", color: "var(--n-900)" }}
                          >
                            <option value="">Elegir existente…</option>
                            {disponibles.map(r => <option key={r.id} value={r.id}>{r.nombre} · {r.email}</option>)}
                          </select>
                        )}
                        <div style={{ fontSize: 10.5, color: "var(--n-500)" }}>o crear uno nuevo:</div>
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
                  <div style={{ fontSize: 12, fontWeight: 600, color: "var(--n-600)", marginBottom: 6 }}>
                    Salidas (out) {nodoSel.tipo !== "decision" && nodoSel.tipo !== "autorizacion" && <span style={{ fontWeight: 400, color: "var(--n-500)" }}>· opcional</span>}
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
                      Esta etapa todavía no tiene ejecución real conectada (solo el paso de autorización la tiene) — las salidas quedan como documentación del proceso y validan el grafo.
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
      </div>
    </div>
  );
}
