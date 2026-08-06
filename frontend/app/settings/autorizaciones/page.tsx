"use client";
import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowLeft, Bot, Send, CheckCircle2, XCircle, LayoutGrid } from "lucide-react";
import { createClient } from "@/lib/supabase/client";
import { BtnPrimary, BtnSecondary, Card, Input, TypingBubble, CascadeWrapper, SkeletonBox } from "@/components/ui";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface Mensaje {
  rol: "bot" | "user";
  texto: string;
}

interface Etapa {
  nombre: string;
  tipo: string;
  roles: string[];
}

interface ReglaAutorizacion {
  hasta: number | null;
  desde: number | null;
  descripcion: string;
}

interface ResponsableDetectado {
  nombre: string;
  email: string;
  roles: string[];
}

interface Propuesta {
  resumen: string;
  etapas: Etapa[];
  reglas_autorizacion: ReglaAutorizacion[];
  requiere_aclaracion: boolean;
  preguntas: string[];
  nodos: Record<string, unknown>[];
  conexiones: Record<string, unknown>[];
  responsables_detectados: ResponsableDetectado[];
}

const TIPO_LABEL: Record<string, string> = {
  tarea_humana: "Tarea", revision: "Revisión", autorizacion: "Autorización",
  homologacion: "Homologación", emision_oc: "Emisión de OC",
  compra_sin_oc: "Compra sin OC", espera_documento: "Espera de documento",
  accion_automatica: "Acción automática",
};

function fmtCLP(n: number) {
  return `$${Math.round(n).toLocaleString("es-CL")}`;
}

export default function ConfiguracionAutorizacionesPage() {
  const router = useRouter();
  const [userId, setUserId] = useState<string | null>(null);
  const [cargandoInicial, setCargandoInicial] = useState(true);
  const [mensajes, setMensajes] = useState<Mensaje[]>([
    { rol: "bot", texto: "Cuéntame cómo funciona hoy tu proceso de compras. Puede ser informal — por ejemplo: \"Los cotizadores preparan la comparación, después la revisa mi jefe, y si es sobre $500.000 también tiene que aprobar finanzas.\"" },
  ]);
  const [entrada, setEntrada] = useState("");
  const [cargando, setCargando] = useState(false);
  const [propuesta, setPropuesta] = useState<Propuesta | null>(null);
  const [nombreWorkflow, setNombreWorkflow] = useState("Ciclo de compras");
  const [workflowGuardado, setWorkflowGuardado] = useState<{ id: string; estado: string } | null>(null);
  const [errores, setErrores] = useState<{ codigo: string; mensaje: string }[]>([]);
  const [activando, setActivando] = useState(false);
  const [creandoEnBlanco, setCreandoEnBlanco] = useState(false);
  // Emails de responsables detectados que el usuario deja marcados para
  // invitar al confirmar. Un email vacío nunca entra acá (los responsables
  // sin email se crean sin invitar).
  const [aInvitar, setAInvitar] = useState<Set<string>>(new Set());
  const finRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    createClient().auth.getUser().then(({ data }) => {
      setUserId(data.user?.id ?? null);
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
      const res = await fetch(`${API_URL}/api/workflows/interpretar`, {
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
        // Por defecto se marcan todos los responsables con email — el
        // usuario puede desmarcar los que no quiera invitar todavía.
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
      // Responsables listos para el backend: se marca `invitar` solo para
      // los que tienen email Y el usuario dejó el checkbox activo.
      const responsables = (propuesta.responsables_detectados || []).map(r => ({
        nombre: r.nombre,
        email: r.email || null,
        roles: r.roles,
        invitar: !!r.email && aInvitar.has(r.email),
      }));

      const creado = await fetch(`${API_URL}/api/workflows`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          user_id: userId,
          nombre: nombreWorkflow.trim() || "Ciclo de compras",
          nodos: propuesta.nodos,
          conexiones: propuesta.conexiones,
          origen: "conversacional",
          responsables,
        }),
      }).then(r => r.json());

      const validacion = await fetch(`${API_URL}/api/workflows/${creado.id}/validar?user_id=${userId}`).then(r => r.json());
      setErrores(validacion.errores || []);
      setWorkflowGuardado({ id: creado.id, estado: creado.estado });
      setPropuesta(null);

      const enviadas = (creado.invitaciones || []).filter((i: { estado: string }) => i.estado === "invitado");
      const yaMiembro = (creado.invitaciones || []).filter((i: { estado: string }) => i.estado === "ya_miembro");
      const errorInv = (creado.invitaciones || []).filter((i: { estado: string }) => i.estado === "error");
      let extra = "";
      if (enviadas.length) extra += ` Enviamos ${enviadas.length} invitación${enviadas.length === 1 ? "" : "es"} por correo.`;
      if (yaMiembro.length) extra += ` ${yaMiembro.length} ya era miembro.`;
      if (errorInv.length) extra += ` ${errorInv.length} invitación${errorInv.length === 1 ? "" : "es"} fallaron — revisa la lista de responsables.`;
      setMensajes(prev => [...prev, { rol: "bot", texto: (validacion.valido
        ? "Quedó guardado como borrador y validado correctamente."
        : "Quedó guardado como borrador, pero hay algunos detalles que revisar antes de activarlo.") + extra }]);
    } catch {
      setMensajes(prev => [...prev, { rol: "bot", texto: "No pude guardar el workflow. Intenta de nuevo." }]);
    } finally {
      setCargando(false);
    }
  };

  const activar = async () => {
    if (!workflowGuardado || !userId) return;
    setActivando(true);
    try {
      await fetch(`${API_URL}/api/workflows/${workflowGuardado.id}/activar`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user_id: userId }),
      });
      setWorkflowGuardado(prev => prev ? { ...prev, estado: "activo" } : prev);
    } catch {
      setMensajes(prev => [...prev, { rol: "bot", texto: "No se pudo activar. Revisa la validación e intenta de nuevo." }]);
    } finally {
      setActivando(false);
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
      const creado = await fetch(`${API_URL}/api/workflows`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user_id: userId, nombre: "Ciclo de compras", nodos, conexiones: [], origen: "visual" }),
      }).then(r => r.json());
      router.push(`/settings/autorizaciones/canvas/${creado.id}`);
    } catch {
      setCreandoEnBlanco(false);
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

  return (
    <div style={{ maxWidth: 640, margin: "0 auto" }}>
      <button onClick={() => router.push("/settings")} style={{ border: 0, background: "none", color: "var(--n-600)", cursor: "pointer", display: "inline-flex", alignItems: "center", gap: 6, marginBottom: 16, fontSize: 13.5 }}>
        <ArrowLeft size={16} /> Configuración
      </button>

      <div style={{ marginBottom: 20 }}>
        <h1 style={{ fontSize: 22, fontWeight: 600, color: "var(--n-900)", margin: "0 0 4px" }}>Ciclo de compras y autorizaciones</h1>
        <p style={{ fontSize: 13.5, color: "var(--n-600)", margin: 0 }}>Cuéntaselo a Baiyer en tus palabras. Después puedes ajustarlo visualmente.</p>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: 12, marginBottom: 16 }}>
        {mensajes.map((m, i) => (
          <div key={i} style={{ display: "flex", justifyContent: m.rol === "user" ? "flex-end" : "flex-start", gap: 8 }}>
            {m.rol === "bot" && (
              <span style={{ width: 28, height: 28, borderRadius: 8, flexShrink: 0, background: "var(--brand-50)", color: "var(--brand)", display: "inline-flex", alignItems: "center", justifyContent: "center" }}>
                <Bot size={16} strokeWidth={1.75} />
              </span>
            )}
            <div style={{
              maxWidth: "80%", padding: "10px 14px", fontSize: 14, lineHeight: 1.5,
              background: m.rol === "user" ? "var(--brand)" : "var(--surface)",
              color: m.rol === "user" ? "#fff" : "var(--n-900)",
              border: m.rol === "user" ? "none" : "1px solid var(--n-200)",
              borderRadius: m.rol === "user" ? "16px 16px 4px 16px" : "16px 16px 16px 4px",
              boxShadow: m.rol === "bot" ? "var(--shadow-card)" : "none",
            }}>
              {m.texto}
            </div>
          </div>
        ))}

        {propuesta && (
          <Card padding={18} style={{ marginLeft: 36 }}>
            <div style={{ display: "flex", flexDirection: "column", gap: 10, marginBottom: 14 }}>
              {propuesta.etapas.map((e, i) => (
                <div key={i} style={{ display: "flex", alignItems: "center", gap: 10, fontSize: 13.5 }}>
                  <span style={{
                    width: 22, height: 22, borderRadius: "50%", flexShrink: 0,
                    background: "var(--brand-50)", color: "var(--brand)", fontSize: 11, fontWeight: 600,
                    display: "inline-flex", alignItems: "center", justifyContent: "center",
                  }}>{i + 1}</span>
                  <div>
                    <strong style={{ color: "var(--n-900)" }}>{e.nombre}</strong>
                    <span style={{ color: "var(--n-500)" }}> · {TIPO_LABEL[e.tipo] ?? e.tipo} · {e.roles.join(", ")}</span>
                  </div>
                </div>
              ))}
              {propuesta.reglas_autorizacion.length > 1 && (
                <div style={{ marginTop: 4, paddingTop: 10, borderTop: "1px dashed var(--n-200)" }}>
                  <div style={{ fontSize: 12.5, color: "var(--n-500)", marginBottom: 6 }}>Reglas por monto:</div>
                  {propuesta.reglas_autorizacion.map((r, i) => (
                    <div key={i} style={{ fontSize: 13, color: "var(--n-700)", marginBottom: 3 }}>
                      {r.hasta != null ? `Hasta ${fmtCLP(r.hasta)}` : `Desde ${fmtCLP(r.desde ?? 0)}`}: {r.descripcion}
                    </div>
                  ))}
                </div>
              )}
              {(propuesta.responsables_detectados || []).length > 0 && (
                <div style={{ marginTop: 4, paddingTop: 10, borderTop: "1px dashed var(--n-200)" }}>
                  <div style={{ fontSize: 12.5, color: "var(--n-500)", marginBottom: 6 }}>
                    Personas detectadas · desmarca para no invitar
                  </div>
                  {(propuesta.responsables_detectados || []).map((r, i) => {
                    const puedeInvitar = !!r.email;
                    const activo = puedeInvitar && aInvitar.has(r.email);
                    return (
                      <label key={`${r.email || r.nombre}-${i}`} style={{
                        display: "flex", alignItems: "center", gap: 8, padding: "5px 0",
                        fontSize: 13, color: "var(--n-800)",
                        cursor: puedeInvitar ? "pointer" : "default", opacity: puedeInvitar ? 1 : 0.65,
                      }}>
                        <input
                          type="checkbox"
                          checked={activo}
                          disabled={!puedeInvitar}
                          onChange={e => {
                            if (!puedeInvitar) return;
                            setAInvitar(prev => {
                              const s = new Set(prev);
                              if (e.target.checked) s.add(r.email); else s.delete(r.email);
                              return s;
                            });
                          }}
                        />
                        <div style={{ flex: 1 }}>
                          <div><strong style={{ color: "var(--n-900)" }}>{r.nombre || "(sin nombre)"}</strong>
                            {r.email && <span style={{ color: "var(--n-500)" }}> · {r.email}</span>}
                          </div>
                          <div style={{ fontSize: 11.5, color: "var(--n-500)" }}>
                            {r.roles.join(", ")}
                            {!r.email && " · sin email, no se puede invitar"}
                          </div>
                        </div>
                      </label>
                    );
                  })}
                </div>
              )}
            </div>
            <Input label="Nombre de este ciclo" value={nombreWorkflow} onChange={e => setNombreWorkflow(e.target.value)} />
            <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
              <BtnSecondary onClick={corregir} style={{ flex: 1 }}>Quiero corregir</BtnSecondary>
              <BtnPrimary onClick={confirmar} disabled={cargando} style={{ flex: 1 }}>
                {cargando ? "Guardando…" : "Sí, guardar como borrador"}
              </BtnPrimary>
            </div>
          </Card>
        )}

        {workflowGuardado && (
          <Card padding={18} style={{ marginLeft: 36 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
              {errores.length === 0 ? (
                <CheckCircle2 size={18} color="var(--success)" />
              ) : (
                <XCircle size={18} color="var(--danger)" />
              )}
              <strong style={{ fontSize: 14, color: "var(--n-900)" }}>
                {workflowGuardado.estado === "activo" ? "Ciclo activo" : "Guardado como borrador"}
              </strong>
            </div>
            {errores.length > 0 && (
              <ul style={{ margin: "0 0 12px", paddingLeft: 20, fontSize: 13, color: "var(--danger)" }}>
                {errores.map((e, i) => <li key={i}>{e.mensaje}</li>)}
              </ul>
            )}
            <div style={{ display: "flex", gap: 8 }}>
              <BtnSecondary onClick={() => router.push(`/settings/autorizaciones/canvas/${workflowGuardado.id}`)} style={{ flex: 1 }}>
                Ajustar visualmente
              </BtnSecondary>
              {workflowGuardado.estado !== "activo" && (
                <BtnPrimary onClick={activar} disabled={activando || errores.length > 0} style={{ flex: 1 }}>
                  {activando ? "Activando…" : "Activar este ciclo"}
                </BtnPrimary>
              )}
            </div>
          </Card>
        )}

        {cargando && !propuesta && (
          <div style={{ marginLeft: 36 }}><TypingBubble icon={Bot} /></div>
        )}
        <div ref={finRef} />
      </div>

      {!workflowGuardado && mensajes.length === 1 && (
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

      {!workflowGuardado && (
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
      )}
    </div>
  );
}
