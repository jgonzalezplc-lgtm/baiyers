"use client";
import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowLeft, Bot, Send, LayoutGrid } from "lucide-react";
import { createClient } from "@/lib/supabase/client";
import { authFetch } from "@/lib/authFetch";
import { BtnPrimary, Card, TypingBubble, CascadeWrapper, SkeletonBox } from "@/components/ui";
import { ChatBubbles, type Mensaje } from "@/components/chat/ChatBubbles";
import { PropuestaWorkflowCard, type Propuesta } from "@/components/workflow/PropuestaWorkflowCard";
import { WorkflowGuardadoCard } from "@/components/workflow/WorkflowGuardadoCard";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

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

      const validacion = await authFetch(`${API_URL}/api/workflows/${creado.id}/validar`).then(r => r.json());
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
      await authFetch(`${API_URL}/api/workflows/${workflowGuardado.id}/activar`, {
        method: "POST",
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

        {workflowGuardado && (
          <WorkflowGuardadoCard
            workflow={workflowGuardado}
            errores={errores}
            activando={activando}
            onActivar={activar}
            onAjustarVisualmente={() => router.push(`/settings/autorizaciones/canvas/${workflowGuardado.id}`)}
          />
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
