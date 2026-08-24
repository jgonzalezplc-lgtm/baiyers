"use client";
import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowLeft, Bot, Send, LayoutGrid, Trash2, Plus, ChevronDown, ChevronRight } from "lucide-react";
import { createClient } from "@/lib/supabase/client";
import { authFetch } from "@/lib/authFetch";
import { BtnPrimary, BtnSecondary, BtnGhost, Card, TypingBubble, CascadeWrapper, SkeletonBox } from "@/components/ui";
import { ChatBubbles, type Mensaje } from "@/components/chat/ChatBubbles";
import { PropuestaWorkflowCard, type Propuesta } from "@/components/workflow/PropuestaWorkflowCard";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface WorkflowExistente {
  id: string;
  nombre: string;
  estado: string;
  version: number;
  created_at?: string;
  updated_at?: string;
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
  responsables: ResponsableInfo & { usuario_baiyer_id?: string | null; estado_onboarding?: string };
}

interface WorkflowDetalle extends WorkflowExistente {
  roles?: { clave: string; nombre: string }[];
  responsables?: AsignacionRol[];
}

const ESTADO_LABEL: Record<string, string> = { activo: "Activo", borrador: "Borrador", archivado: "Archivado" };

const ONBOARDING_BADGE: Record<string, { label: string; bg: string; fg: string }> = {
  activo: { label: "Activo", bg: "var(--success-bg, #e6f4ea)", fg: "var(--success, #1e7e34)" },
  invitacion_pendiente: { label: "Invitación pendiente", bg: "var(--warning-bg, #fff4e0)", fg: "var(--warning, #b26a00)" },
  sin_vincular: { label: "Sin vincular", bg: "var(--n-100)", fg: "var(--n-500)" },
};

export default function ConfiguracionAutorizacionesPage() {
  const router = useRouter();
  const [userId, setUserId] = useState<string | null>(null);
  const [cargandoInicial, setCargandoInicial] = useState(true);
  const [workflowsExistentes, setWorkflowsExistentes] = useState<WorkflowExistente[]>([]);
  const [principal, setPrincipal] = useState<WorkflowDetalle | null>(null);
  const [responsablesOrg, setResponsablesOrg] = useState<ResponsableInfo[]>([]);
  const [mostrarOtros, setMostrarOtros] = useState(false);
  const [mostrarChatNuevo, setMostrarChatNuevo] = useState(false);
  const [asignandoRol, setAsignandoRol] = useState<string | null>(null);
  const [nuevoNombre, setNuevoNombre] = useState("");
  const [nuevoEmail, setNuevoEmail] = useState("");
  const [guardandoResponsable, setGuardandoResponsable] = useState(false);
  const [confirmandoEliminar, setConfirmandoEliminar] = useState<string | null>(null);
  const [eliminando, setEliminando] = useState<string | null>(null);
  const [toast, setToast] = useState("");

  const [mensajes, setMensajes] = useState<Mensaje[]>([
    { rol: "bot", texto: "Cuéntame cómo funciona hoy tu proceso de compras. Puede ser informal — por ejemplo: \"Los cotizadores preparan la comparación, después la revisa mi jefe, y si es sobre $500.000 también tiene que aprobar finanzas.\"" },
  ]);
  const [entrada, setEntrada] = useState("");
  const [cargando, setCargando] = useState(false);
  const [propuesta, setPropuesta] = useState<Propuesta | null>(null);
  const [nombreWorkflow, setNombreWorkflow] = useState("Ciclo de compras");
  const [creandoEnBlanco, setCreandoEnBlanco] = useState(false);
  const [aInvitar, setAInvitar] = useState<Set<string>>(new Set());
  const finRef = useRef<HTMLDivElement>(null);

  const avisar = (texto: string) => {
    setToast(texto);
    setTimeout(() => setToast(""), 3500);
  };

  // Trae la lista completa y refresca el detalle del ciclo cuyo id se pasa
  // (o null para dejarlo sin elegir). Nunca recalcula "cuál es el principal"
  // por su cuenta — eso solo pasa en elegirPrincipal(), para que asignar o
  // quitar una persona no salte a otro ciclo en medio de la edición.
  //
  // Importante: un fallo de red/timeout al refrescar NUNCA borra lo que ya
  // había en pantalla — solo un 404 real (el ciclo ya no existe) limpia el
  // principal. Antes, cualquier error de fetch caía a `null` y la tarjeta
  // recién asignada "desaparecía" aunque el cambio sí se hubiera guardado.
  const cargarDetalle = async (uid: string, workflowId: string | null) => {
    let arr = workflowsExistentes;
    try {
      const lista: WorkflowExistente[] = await authFetch(`${API_URL}/api/workflows`).then(r => r.json());
      arr = Array.isArray(lista) ? lista : [];
      setWorkflowsExistentes(arr);
    } catch {
      avisar("No pudimos actualizar la lista de ciclos — intenta de nuevo.");
    }

    if (!workflowId) {
      setPrincipal(null);
      return arr;
    }

    try {
      const res = await authFetch(`${API_URL}/api/workflows/${workflowId}`);
      if (res.status === 404) {
        setPrincipal(null);
        return arr;
      }
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const detalle: WorkflowDetalle = await res.json();
      setPrincipal(detalle);
      const org: ResponsableInfo[] = await authFetch(`${API_URL}/api/workflows/responsables/listar`).then(r => r.json());
      setResponsablesOrg(Array.isArray(org) ? org : []);
    } catch {
      avisar("El cambio se guardó, pero no pudimos refrescar la vista — intenta recargar la página.");
    }
    return arr;
  };

  // Elige el ciclo principal (activo, o el borrador más reciente) — solo se
  // llama al montar la página o después de eliminar un ciclo, nunca tras
  // asignar/quitar una persona del ciclo que ya se está viendo.
  const elegirPrincipal = async (uid: string) => {
    const lista: WorkflowExistente[] = await authFetch(`${API_URL}/api/workflows`).then(r => r.json()).catch(() => []);
    const arr = Array.isArray(lista) ? lista : [];
    const candidato = arr.find(w => w.estado === "activo") || arr.find(w => w.estado === "borrador") || arr[0] || null;
    await cargarDetalle(uid, candidato?.id ?? null);
  };

  useEffect(() => {
    createClient().auth.getUser().then(async ({ data }) => {
      const uid = data.user?.id ?? null;
      setUserId(uid);
      if (uid) await elegirPrincipal(uid);
      setCargandoInicial(false);
    });
  }, []);

  useEffect(() => {
    finRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [mensajes, propuesta]);

  const contextoAcumulado = () =>
    mensajes.map(m => `${m.rol === "bot" ? "ASISTENTE" : "USUARIO"}: ${m.texto}`).join("\n");

  const enviar = async () => {
    const texto = entrada.trim();
    if (!texto || cargando) return;
    setEntrada("");
    setMensajes(prev => [...prev, { rol: "user", texto }]);
    setCargando(true);
    setPropuesta(null);
    try {
      const res = await authFetch(`${API_URL}/api/workflows/interpretar`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ descripcion: texto, contexto: contextoAcumulado() }),
        signal: AbortSignal.timeout(40000),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data: Propuesta = await res.json();
      if (data.requiere_aclaracion) {
        const pregunta = data.preguntas.length
          ? data.preguntas.join(" ")
          : "¿Puedes darme un poco más de detalle?";
        setMensajes(prev => [...prev, { rol: "bot", texto: pregunta }]);
      } else {
        setMensajes(prev => [...prev, { rol: "bot", texto: data.resumen || "Esto es lo que entendí:" }]);
        setPropuesta(data);
        setAInvitar(new Set((data.responsables_detectados || []).filter(r => r.email).map(r => r.email)));
      }
    } catch (error) {
      const timeout = error instanceof DOMException && error.name === "TimeoutError";
      setMensajes(prev => [...prev, { rol: "bot", texto: timeout
        ? "Está tardando más de lo esperado. No guardé nada; prueba nuevamente o ármalo visualmente."
        : "Tuve un problema interpretando eso. No guardé nada; puedes intentarlo de nuevo." }]);
    } finally {
      setCargando(false);
    }
  };

  const corregir = () => {
    setPropuesta(null);
    setMensajes(prev => [...prev, { rol: "bot", texto: "Cuéntame qué cambiarías." }]);
  };

  const confirmar = async () => {
    if (!propuesta || !userId) return;
    setCargando(true);
    try {
      const responsables = (propuesta.responsables_detectados || []).map(r => ({
        nombre: r.nombre,
        email: r.email || null,
        roles: r.roles,
        invitar: !!r.email && aInvitar.has(r.email),
      }));

      const creado = await authFetch(`${API_URL}/api/workflows`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          nombre: nombreWorkflow.trim() || "Ciclo de compras",
          nodos: propuesta.nodos,
          conexiones: propuesta.conexiones,
          origen: "conversacional",
          responsables,
        }),
      }).then(r => r.json());

      router.push(`/settings/autorizaciones/canvas/${creado.id}`);
    } catch {
      setMensajes(prev => [...prev, { rol: "bot", texto: "No pude guardar el workflow. Intenta de nuevo." }]);
    } finally {
      setCargando(false);
    }
  };

  const empezarEnBlanco = async () => {
    if (!userId) return;
    setCreandoEnBlanco(true);
    try {
      const nodos = [
        { id: "inicio", tipo: "inicio", nombre: "Inicio", posicion: { x: 60, y: 40 } },
        { id: "fin", tipo: "fin", nombre: "Fin", posicion: { x: 60, y: 200 } },
      ];
      const creado = await authFetch(`${API_URL}/api/workflows`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ nombre: "Ciclo de compras", nodos, conexiones: [], origen: "visual" }),
      }).then(r => r.json());
      router.push(`/settings/autorizaciones/canvas/${creado.id}`);
    } catch {
      setCreandoEnBlanco(false);
    }
  };

  const asignarExistente = async (rol: string, responsableId: string) => {
    if (!userId || !principal) return;
    setGuardandoResponsable(true);
    try {
      const res = await authFetch(`${API_URL}/api/workflows/responsables/${responsableId}/roles`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ workflow_id: principal.id, rol_clave: rol }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        avisar(body.detail || "No se pudo asignar el responsable");
        return;
      }
      await cargarDetalle(userId, principal.id);
      setAsignandoRol(null);
      const nombre = responsablesOrg.find(r => r.id === responsableId)?.nombre || "Responsable";
      avisar(`${nombre} asignado a "${rol}"`);
    } finally {
      setGuardandoResponsable(false);
    }
  };

  const crearYAsignar = async (rol: string) => {
    if (!userId || !principal || !nuevoNombre.trim() || !nuevoEmail.trim()) return;
    setGuardandoResponsable(true);
    try {
      const creado = await authFetch(`${API_URL}/api/workflows/responsables`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ nombre: nuevoNombre.trim(), email: nuevoEmail.trim() }),
      }).then(r => r.json());
      await authFetch(`${API_URL}/api/workflows/responsables/${creado.id}/roles`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ workflow_id: principal.id, rol_clave: rol }),
      });
      let mensajeInvitacion = "";
      try {
        const inv = await authFetch(`${API_URL}/api/organizacion/invitar`, {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ email: nuevoEmail.trim(), responsable_id: creado.id }),
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
      avisar(mensajeInvitacion);
      await cargarDetalle(userId, principal.id);
      setAsignandoRol(null); setNuevoNombre(""); setNuevoEmail("");
    } finally {
      setGuardandoResponsable(false);
    }
  };

  const quitarAsignacion = async (rol: string, responsableId: string) => {
    if (!userId || !principal) return;
    setGuardandoResponsable(true);
    try {
      await authFetch(`${API_URL}/api/workflows/responsables/${responsableId}/roles/${principal.id}/${rol}`, { method: "DELETE" });
      await cargarDetalle(userId, principal.id);
    } finally {
      setGuardandoResponsable(false);
    }
  };

  const eliminarCiclo = async (id: string) => {
    if (!userId) return;
    setEliminando(id);
    try {
      const res = await authFetch(`${API_URL}/api/workflows/${id}`, { method: "DELETE" });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        avisar(body.detail || "No se pudo eliminar el ciclo");
        return;
      }
      setConfirmandoEliminar(null);
      await elegirPrincipal(userId);
    } finally {
      setEliminando(null);
    }
  };

  if (cargandoInicial) {
    return (
      <div style={{ maxWidth: 640, margin: "0 auto" }}>
        <SkeletonBox height={13} width={120} style={{ marginBottom: 16 }} />
        <SkeletonBox height={26} width={320} style={{ marginBottom: 8 }} />
        <SkeletonBox height={13} width={400} style={{ marginBottom: 20 }} />
        <CascadeWrapper>
          <Card padding={18}><SkeletonBox height={60} width="100%" /></Card>
          <Card padding={18} style={{ marginTop: 16 }}><SkeletonBox height={70} width="100%" /></Card>
        </CascadeWrapper>
      </div>
    );
  }

  const otrosWorkflows = workflowsExistentes.filter(w => w.id !== principal?.id);
  const asignaciones = principal?.responsables || [];
  const roles = principal?.roles || [];

  const mostrarChat = mostrarChatNuevo || !principal;

  return (
    <div style={{ maxWidth: 640, margin: "0 auto" }}>
      <button onClick={() => router.push("/settings")} style={{ border: 0, background: "none", color: "var(--n-600)", cursor: "pointer", display: "inline-flex", alignItems: "center", gap: 6, marginBottom: 16, fontSize: 13.5 }}>
        <ArrowLeft size={16} /> Configuración
      </button>

      {toast && (
        <div style={{ marginBottom: 14, padding: "9px 13px", borderRadius: "var(--r-md)", background: "var(--surface-2)", color: "var(--n-800)", fontSize: 12.5 }}>
          {toast}
        </div>
      )}

      {principal && !mostrarChat && (
        <>
          <div style={{ marginBottom: 20, display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 12 }}>
            <div>
              <h1 style={{ fontSize: 22, fontWeight: 600, color: "var(--n-900)", margin: "0 0 4px" }}>{principal.nombre}</h1>
              <p style={{ fontSize: 13.5, color: "var(--n-600)", margin: 0 }}>
                {ESTADO_LABEL[principal.estado] ?? principal.estado} · quién está a cargo de cada rol y si ya se sumó a Baiyer.
              </p>
            </div>
            <BtnSecondary onClick={() => router.push(`/settings/autorizaciones/canvas/${principal.id}`)} size="sm">
              Editar el grafo
            </BtnSecondary>
          </div>

          <CascadeWrapper>
            {roles.length === 0 && (
              <Card padding={18} style={{ marginBottom: 12 }}>
                <div style={{ fontSize: 13, color: "var(--n-500)" }}>Este ciclo todavía no tiene roles definidos — ábrelo en el editor visual para agregarlos.</div>
              </Card>
            )}
            {roles.map(rol => {
              const asignados = asignaciones.filter(a => a.rol_clave === rol.clave);
              const disponibles = responsablesOrg.filter(r => r.activo && !asignados.some(a => a.responsables?.id === r.id));
              return (
                <Card key={rol.clave} padding={16} style={{ marginBottom: 12 }}>
                  <div style={{ fontSize: 13.5, fontWeight: 600, color: "var(--n-900)", marginBottom: 10 }}>{rol.nombre}</div>

                  <div style={{ display: "flex", flexDirection: "column", gap: 6, marginBottom: 8 }}>
                    {asignados.length === 0 && <div style={{ fontSize: 12.5, color: "var(--n-500)" }}>Nadie asignado todavía.</div>}
                    {asignados.map(a => {
                      const estado = a.responsables?.estado_onboarding || "sin_vincular";
                      const badge = ONBOARDING_BADGE[estado] || ONBOARDING_BADGE.sin_vincular;
                      return (
                        <div key={a.id} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8, padding: "7px 10px", background: "var(--surface-2)", borderRadius: "var(--r-sm)" }}>
                          <div style={{ minWidth: 0 }}>
                            <div style={{ fontSize: 13, color: "var(--n-900)" }}>{a.responsables?.nombre}</div>
                            <div style={{ fontSize: 11.5, color: "var(--n-500)" }}>{a.responsables?.email || "sin email"}</div>
                          </div>
                          <div style={{ display: "flex", alignItems: "center", gap: 8, flexShrink: 0 }}>
                            <span style={{ fontSize: 11, fontWeight: 600, padding: "3px 8px", borderRadius: "var(--r-pill)", background: badge.bg, color: badge.fg, whiteSpace: "nowrap" }}>
                              {badge.label}
                            </span>
                            <button onClick={() => quitarAsignacion(rol.clave, a.responsables.id)} disabled={guardandoResponsable} style={{ border: 0, background: "none", color: "var(--n-400)", cursor: "pointer", padding: 0 }} title="Quitar">
                              <Trash2 size={13} />
                            </button>
                          </div>
                        </div>
                      );
                    })}
                  </div>

                  {asignandoRol === rol.clave ? (
                    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                      {disponibles.length > 0 && (
                        <>
                          <select
                            defaultValue=""
                            disabled={guardandoResponsable}
                            onChange={e => { if (e.target.value) asignarExistente(rol.clave, e.target.value); }}
                            style={{ width: "100%", padding: "6px 8px", fontSize: 12.5, borderRadius: "var(--r-sm)", border: "1px solid var(--n-300)", background: "var(--surface)", color: "var(--n-900)" }}
                          >
                            <option value="">Elegir persona existente…</option>
                            {disponibles.map(r => <option key={r.id} value={r.id}>{r.nombre} · {r.email}</option>)}
                          </select>
                          <div style={{ fontSize: 11, color: "var(--n-500)" }}>o crear una persona nueva:</div>
                        </>
                      )}
                      <input placeholder="Nombre" value={nuevoNombre} onChange={e => setNuevoNombre(e.target.value)} style={{ padding: "6px 8px", fontSize: 12.5, borderRadius: "var(--r-sm)", border: "1px solid var(--n-300)", background: "var(--surface)", color: "var(--n-900)" }} />
                      <input placeholder="Email" type="email" value={nuevoEmail} onChange={e => setNuevoEmail(e.target.value)} style={{ padding: "6px 8px", fontSize: 12.5, borderRadius: "var(--r-sm)", border: "1px solid var(--n-300)", background: "var(--surface)", color: "var(--n-900)" }} />
                      <div style={{ display: "flex", gap: 6 }}>
                        <BtnGhost onClick={() => { setAsignandoRol(null); setNuevoNombre(""); setNuevoEmail(""); }} size="sm">Cancelar</BtnGhost>
                        <BtnPrimary onClick={() => crearYAsignar(rol.clave)} disabled={!nuevoNombre.trim() || !nuevoEmail.trim() || guardandoResponsable} size="sm">Crear e invitar</BtnPrimary>
                      </div>
                    </div>
                  ) : (
                    <button onClick={() => setAsignandoRol(rol.clave)} style={{ display: "inline-flex", alignItems: "center", gap: 4, border: 0, background: "none", color: "var(--brand)", fontSize: 12.5, cursor: "pointer", padding: 0 }}>
                      <Plus size={13} /> Agregar persona
                    </button>
                  )}
                </Card>
              );
            })}
          </CascadeWrapper>

          {otrosWorkflows.length > 0 && (
            <div style={{ marginTop: 8, marginBottom: 16 }}>
              <button
                onClick={() => setMostrarOtros(v => !v)}
                style={{ display: "inline-flex", alignItems: "center", gap: 4, border: 0, background: "none", color: "var(--n-600)", fontSize: 12.5, cursor: "pointer", padding: 0 }}
              >
                {mostrarOtros ? <ChevronDown size={14} /> : <ChevronRight size={14} />} Otros ciclos ({otrosWorkflows.length})
              </button>
              {mostrarOtros && (
                <Card padding={0} style={{ marginTop: 8 }}>
                  {otrosWorkflows.map((w, i) => (
                    <div key={w.id} style={{ padding: "10px 14px", borderBottom: i === otrosWorkflows.length - 1 ? "none" : "1px solid var(--n-100)" }}>
                      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 10 }}>
                        <div style={{ minWidth: 0 }}>
                          <div style={{ fontSize: 13, fontWeight: 500, color: "var(--n-900)" }}>{w.nombre}</div>
                          <div style={{ fontSize: 11.5, color: "var(--n-500)", marginTop: 2 }}>v{w.version} · {ESTADO_LABEL[w.estado] ?? w.estado}</div>
                        </div>
                        <div style={{ display: "flex", alignItems: "center", gap: 10, flexShrink: 0 }}>
                          <button onClick={() => router.push(`/settings/autorizaciones/canvas/${w.id}`)} style={{ border: 0, background: "none", color: "var(--brand)", fontSize: 12, cursor: "pointer" }}>Abrir</button>
                          {confirmandoEliminar === w.id ? (
                            <>
                              <button onClick={() => eliminarCiclo(w.id)} disabled={eliminando === w.id} style={{ border: 0, background: "none", color: "var(--error, #c0392b)", fontSize: 12, cursor: "pointer" }}>
                                {eliminando === w.id ? "Eliminando…" : "Confirmar"}
                              </button>
                              <button onClick={() => setConfirmandoEliminar(null)} style={{ border: 0, background: "none", color: "var(--n-500)", fontSize: 12, cursor: "pointer" }}>Cancelar</button>
                            </>
                          ) : (
                            <button onClick={() => setConfirmandoEliminar(w.id)} style={{ border: 0, background: "none", color: "var(--n-400)", cursor: "pointer" }} title="Eliminar">
                              <Trash2 size={13} />
                            </button>
                          )}
                        </div>
                      </div>
                    </div>
                  ))}
                </Card>
              )}
            </div>
          )}

          <button
            onClick={() => setMostrarChatNuevo(true)}
            style={{ display: "inline-flex", alignItems: "center", gap: 6, border: 0, background: "none", color: "var(--n-500)", fontSize: 12.5, cursor: "pointer" }}
          >
            + Crear un ciclo nuevo
          </button>
        </>
      )}

      {mostrarChat && (
      <>
      <div style={{ marginBottom: 20 }}>
        <h1 style={{ fontSize: 22, fontWeight: 600, color: "var(--n-900)", margin: "0 0 4px" }}>Ciclo de compras y autorizaciones</h1>
        <p style={{ fontSize: 13.5, color: "var(--n-600)", margin: 0 }}>Cuéntaselo a Baiyer en tus palabras. Después puedes ajustarlo visualmente.</p>
      </div>

      {principal && (
        <button
          onClick={() => setMostrarChatNuevo(false)}
          style={{ display: "inline-flex", alignItems: "center", gap: 6, marginBottom: 16, border: 0, background: "none", color: "var(--n-600)", fontSize: 12.5, cursor: "pointer" }}
        >
          <ArrowLeft size={13} /> Volver a &quot;{principal.nombre}&quot;
        </button>
      )}

      <div style={{ display: "flex", flexDirection: "column", gap: 12, marginBottom: 16 }}>
        <ChatBubbles mensajes={mensajes} />

        {propuesta && (
          <PropuestaWorkflowCard
            propuesta={propuesta}
            aInvitar={aInvitar}
            onToggleInvitar={(email, activo) => {
              setAInvitar(prev => {
                const s = new Set(prev);
                if (activo) s.add(email); else s.delete(email);
                return s;
              });
            }}
            nombreWorkflow={nombreWorkflow}
            onNombreWorkflowChange={setNombreWorkflow}
            onCorregir={corregir}
            onConfirmar={confirmar}
            cargando={cargando}
          />
        )}

        {cargando && !propuesta && (
          <div style={{ marginLeft: 36 }}><TypingBubble icon={Bot} /></div>
        )}
        <div ref={finRef} />
      </div>

      {mensajes.length === 1 && (
        <button
          onClick={empezarEnBlanco}
          disabled={creandoEnBlanco || !userId}
          style={{
            display: "inline-flex", alignItems: "center", gap: 6, marginBottom: 12,
            border: 0, background: "none", color: "var(--n-500)", fontSize: 12.5, cursor: "pointer",
          }}
        >
          <LayoutGrid size={13} /> {creandoEnBlanco ? "Creando…" : "¿Prefieres armarlo visualmente? Empezar en blanco →"}
        </button>
      )}

      <div style={{ display: "flex", gap: 10 }}>
        <textarea
          value={entrada}
          onChange={e => setEntrada(e.target.value)}
          onKeyDown={e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); enviar(); } }}
          placeholder="Escribe acá…"
          rows={2}
          disabled={cargando}
          style={{
            flex: 1, resize: "none", background: "var(--surface)", color: "var(--n-900)",
            border: "1px solid var(--n-300)", borderRadius: "var(--r-md)", padding: 12,
            fontFamily: "inherit", fontSize: 14, lineHeight: 1.5, outline: "none",
          }}
        />
        <BtnPrimary onClick={enviar} disabled={!entrada.trim() || cargando} style={{ alignSelf: "flex-end" }}>
          <Send size={16} />
        </BtnPrimary>
      </div>
      </>
      )}
    </div>
  );
}
