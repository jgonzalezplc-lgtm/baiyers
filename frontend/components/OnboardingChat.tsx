"use client";
/**
 * Chat conversacional de onboarding. Antes era una máquina de fases con
 * regex (pedir_nombre → rut → nombre_usuario → logo → proceso); ahora cada
 * mensaje se manda tal cual al backend (`/api/onboarding/sesion/:id/turno`),
 * que extrae los campos con tolerancia a lenguaje natural, fuera de orden y
 * correcciones, y decide cuándo la sesión está realmente completa — la
 * verdad de la conversación vive en `onboarding_sessions`, no en este
 * componente, así que se puede recargar la página sin perder el progreso.
 *
 * Una vez que el perfil queda completo, la MISMA conversación pasa a una
 * segunda fase — configurar el proceso de compras — con exactamente la
 * misma mecánica que usa `/settings/autorizaciones` (POST
 * /api/workflows/interpretar + PropuestaWorkflowCard), en vez de mezclar la
 * extracción de perfil y de proceso en una sola cosa. Mismos componentes
 * visuales (ChatBubbles, TypingBubble) en los tres chats de Baiyer
 * (onboarding, configuración de autorizaciones, correcciones del canvas).
 *
 * Se usa tanto en /onboarding (página completa, primera vez) como flotando
 * sobre el dashboard (OnboardingFloating) para retomar sólo lo que falte.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Bot, Send } from "lucide-react";
import { createClient } from "@/lib/supabase/client";
import { authFetch } from "@/lib/authFetch";
import { camposFaltantes } from "@/lib/onboarding";
import { BtnPrimary, BtnGhost, TypingBubble } from "@/components/ui";
import { ChatBubbles, type Mensaje } from "@/components/chat/ChatBubbles";
import { PropuestaWorkflowCard, type Propuesta } from "@/components/workflow/PropuestaWorkflowCard";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface Investigacion {
  empresa: string | null;
  es_empresa_conocida?: boolean;
  pais?: string; pais_tld?: string | null;
  industria?: string;
  descripcion?: string;
  presencia?: string;
  sitio_web?: string;
  rut?: string | null;
  direccion?: string | null;
  categorias_compra_probables?: string[];
  logo_candidatos?: string[];
  generico?: boolean;
}

interface DraftCampo {
  valor: string;
  confianza: string;
  origen: string;
  confirmado: boolean;
  evidencia?: string;
}
type Draft = Record<string, DraftCampo>;

type Rol = "bot" | "user";
interface Msg { rol: Rol; texto?: string; card?: Investigacion; }

/** perfil: preguntas de empresa/RUT/nombre. transicion: perfil ya
 * confirmado, esperando que el usuario decida si configura el proceso de
 * compras ahora. proceso: misma conversación, ahora hablando de ETAPAS del
 * proceso de compras (idéntico a /settings/autorizaciones). */
type Fase = "perfil" | "transicion" | "proceso";

interface Props {
  /** Estilo compacto para panel flotante (sin header de página completa). */
  floating?: boolean;
  /** Se llama cuando terminó de guardar (o no había nada que hacer). En modo no-flotante, además navega a /dashboard. */
  onDone?: () => void;
  /** Acción externa para "Omitir por ahora" en modo flotante. */
  onSkip?: () => void;
}

const ETIQUETAS_CAMPO: Record<string, string> = {
  empresa: "Empresa", rut: "RUT", nombre_usuario: "Tu nombre", direccion: "Dirección",
};

export default function OnboardingChat({ floating, onDone, onSkip }: Props) {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [draft, setDraft] = useState<Draft>({});
  const [completo, setCompleto] = useState(false);
  const [fase, setFase] = useState<Fase>("perfil");
  const [sugerenciasPendientes, setSugerenciasPendientes] = useState<{ campo: "rut" | "direccion"; valor: string }[]>([]);
  const [propuestaWorkflow, setPropuestaWorkflow] = useState<Propuesta | null>(null);
  const [cargandoInicial, setCargandoInicial] = useState(true);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [finalizando, setFinalizando] = useState(false);

  const [investigacion, setInvestigacion] = useState<Investigacion | null>(null);
  const [logoIdx, setLogoIdx] = useState(0);
  const [logoUrlFinal, setLogoUrlFinal] = useState<string | null>(null);
  const [logoOcupado, setLogoOcupado] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const userIdRef = useRef<string | null>(null);

  // Ciclo de compras: mismo mecanismo real que /settings/autorizaciones, no
  // una preview — crea el workflow, invita responsables y permite activarlo.
  const [aInvitarWorkflow, setAInvitarWorkflow] = useState<Set<string>>(new Set());
  const [nombreWorkflow, setNombreWorkflow] = useState("Ciclo de compras");
  const [guardandoWorkflow, setGuardandoWorkflow] = useState(false);
  const emailsVistosRef = useRef<Set<string>>(new Set());
  // Contexto de la fase "proceso" — solo los turnos de esa fase, no arrastra
  // las preguntas de perfil (empresa/RUT/nombre) como contexto ruidoso.
  const procesoDesdeRef = useRef(0);

  const omitirPorAhora = () => {
    if (onSkip) {
      onSkip();
      return;
    }
    // No marca el onboarding como completo: el usuario puede retomarlo desde
    // el panel y el asistente flotante no lo interrumpe durante esta sesión.
    try { sessionStorage.setItem("baiyer-onboarding-omitido", "1"); } catch { /* ignore */ }
    router.replace("/dashboard");
  };

  // Los responsables recién detectados quedan marcados para invitar por
  // defecto; los que el usuario ya desmarcó a mano no se vuelven a marcar
  // solos en turnos siguientes.
  useEffect(() => {
    const detectados = propuestaWorkflow?.responsables_detectados || [];
    const nuevos = detectados.filter(r => r.email && !emailsVistosRef.current.has(r.email));
    if (nuevos.length === 0) return;
    nuevos.forEach(r => emailsVistosRef.current.add(r.email));
    setAInvitarWorkflow(prev => {
      const s = new Set(prev);
      nuevos.forEach(r => s.add(r.email));
      return s;
    });
  }, [propuestaWorkflow]);

  const scrollRef = useRef<HTMLDivElement>(null);
  useEffect(() => { scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" }); }, [msgs, cargandoInicial, busy]);

  const addBot = (texto?: string, card?: Investigacion) => setMsgs(m => [...m, { rol: "bot", texto, card }]);
  const addUser = (texto: string) => setMsgs(m => [...m, { rol: "user", texto }]);
  const espera = (ms: number) => new Promise(r => setTimeout(r, ms));

  const investigar = useCallback(async (correo: string, nombre?: string): Promise<Investigacion> => {
    try {
      const res = await fetch(`${API_URL}/api/onboarding/investigar-empresa`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: correo, nombre_empresa: nombre }),
      });
      return res.ok ? await res.json() : { empresa: null };
    } catch { return { empresa: null }; }
  }, []);

  // Arranque: compatibilidad con cuentas legado (ya completas, sin sesión
  // nueva) + creación/reanudación de la sesión conversacional persistida.
  useEffect(() => {
    createClient().auth.getUser().then(async ({ data }) => {
      const u = data.user;
      if (!u) { if (!floating) router.replace("/login"); return; }
      userIdRef.current = u.id;
      const m = (u.user_metadata ?? {}) as Record<string, unknown>;
      const faltan = camposFaltantes(m);

      if (floating && faltan.length === 0) { onDone?.(); return; }
      if (!floating && u.user_metadata?.onboarding_completo && faltan.length === 0) { router.replace("/dashboard"); return; }

      const correo = u.email ?? "";
      setEmail(correo);

      let sesion: { id: string; draft: Draft; mensajes: { rol: string; texto: string }[]; propuesta_workflow?: Propuesta | null };
      try {
        const res = await authFetch(`${API_URL}/api/onboarding/sesion`, { method: "POST" });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        sesion = await res.json();
        if (!sesion?.id) throw new Error("respuesta sin id de sesión");
      } catch {
        addBot("No pude iniciar tu sesión de configuración. Recarga la página o intenta de nuevo en un minuto.");
        setCargandoInicial(false);
        return;
      }
      setSessionId(sesion.id);
      setDraft(sesion.draft || {});
      setPropuestaWorkflow(sesion.propuesta_workflow ?? null);

      if ((sesion.mensajes || []).length > 0) {
        setMsgs(sesion.mensajes.map(mm => ({ rol: mm.rol === "usuario" ? "user" : "bot", texto: mm.texto })));
        setCargandoInicial(false);
        return;
      }

      // Sesión nueva: saludo + investigación automática de la empresa, igual
      // que antes, pero ahora la confirmación/corrección se hace en lenguaje
      // libre (el backend la interpreta), no con botones de fase fija.
      addBot(`¡Hola! Soy el asistente de Baiyer. Dame un segundo, estoy revisando tu empresa a partir de tu correo (${correo})…`);
      const d = await investigar(correo);
      setInvestigacion(d);
      if (d.es_empresa_conocida && d.empresa) {
        await espera(300);
        addBot(undefined, d);
        await espera(200);
        addBot("¿Es tu empresa? Cuéntame lo que haga falta corregir, o dime de una vez tu RUT, tu nombre y cómo te llamas — todo junto si quieres.");
      } else {
        await espera(300);
        addBot("No reconocí tu empresa automáticamente. Cuéntame su nombre, tu RUT y cómo te llamas — puedes darlo todo en un solo mensaje.");
      }
      setCargandoInicial(false);
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [investigar, router, floating]);

  // Toma el mensaje como parámetro (en vez de leer `input` directo) para que
  // tanto el textarea como el botón de "confirmar con un clic" de una
  // sugerencia (RUT/dirección encontrados por scraping) usen la misma
  // lógica — el backend nunca inventa un valor que no esté literalmente en
  // el mensaje, así que "confirmar con un clic" en realidad manda ese valor
  // como si el usuario lo hubiera escrito, no un simple "sí".
  const enviarMensajePerfil = async (mensaje: string) => {
    if (!mensaje || !sessionId || busy) return;
    addUser(mensaje);
    setSugerenciasPendientes([]);
    setBusy(true);
    try {
      const res = await authFetch(`${API_URL}/api/onboarding/sesion/${sessionId}/turno`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mensaje }),
        signal: AbortSignal.timeout(30000),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setDraft(data.draft || {});
      setCompleto(!!data.completo);
      setPropuestaWorkflow(data.propuesta_workflow ?? null);
      setMsgs((data.mensajes || []).map((mm: { rol: string; texto: string }) => ({ rol: mm.rol === "usuario" ? "user" : "bot", texto: mm.texto })));

      // El usuario recién dio (o corrigió) el nombre de la empresa: la
      // buscamos por nombre para traer RUT/logo — el turno de texto libre
      // no pasa por /investigar-empresa, así que sin esto nunca se
      // enriquecía con datos reales ni se ofrecía elegir logo.
      const nombreEmpresa: string | undefined = data.draft?.empresa?.valor;
      if (nombreEmpresa && nombreEmpresa !== investigacion?.empresa) {
        const d = await investigar(email, nombreEmpresa);
        setInvestigacion(d);
        setLogoIdx(0);
        setLogoUrlFinal(null);
        if (d.empresa) {
          addBot(undefined, d);
        }
        // El RUT/dirección que encuentra el scraping se muestran en la
        // tarjeta, pero eso NO llena el draft de la sesión (draft.rut solo
        // se completa con lo que el usuario escribe en el chat) — sin esto
        // el bot los volvía a pedir como si no los hubiera encontrado. Se
        // ofrece un botón de un clic en vez de pedirle al usuario que los
        // reescriba a mano.
        const nuevasSugerencias: { campo: "rut" | "direccion"; valor: string }[] = [];
        if (d.rut && !data.draft?.rut?.valor) {
          addBot(`Encontré este RUT: ${d.rut}. ¿Es correcto?`);
          nuevasSugerencias.push({ campo: "rut", valor: d.rut });
        }
        if (d.direccion && !data.draft?.direccion?.valor) {
          addBot(`Encontré esta dirección: ${d.direccion}. ¿Es correcta?`);
          nuevasSugerencias.push({ campo: "direccion", valor: d.direccion });
        }
        if (nuevasSugerencias.length) setSugerenciasPendientes(nuevasSugerencias);
      }
    } catch {
      addBot("Tuve un problema procesando eso. Puedes intentarlo de nuevo.");
    } finally {
      setBusy(false);
    }
  };

  const enviarPerfil = () => {
    const mensaje = input.trim();
    if (!mensaje) return;
    setInput("");
    enviarMensajePerfil(mensaje);
  };

  const confirmarSugerencia = (s: { campo: "rut" | "direccion"; valor: string }) => {
    enviarMensajePerfil(s.valor);
  };

  // Fase "proceso": misma llamada, mismo endpoint y mismos mensajes de error
  // que usa /settings/autorizaciones — la diferencia es que acá se sigue
  // agregando a la MISMA lista de mensajes de la conversación, en vez de un
  // hilo separado.
  const contextoProceso = () =>
    msgs.slice(procesoDesdeRef.current).map(m => `${m.rol === "bot" ? "ASISTENTE" : "USUARIO"}: ${m.texto ?? ""}`).join("\n");

  const enviarProceso = async () => {
    const mensaje = input.trim();
    if (!mensaje || busy) return;
    setInput("");
    addUser(mensaje);
    setBusy(true);
    setPropuestaWorkflow(null);
    try {
      const res = await fetch(`${API_URL}/api/workflows/interpretar`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ descripcion: mensaje, contexto: contextoProceso() }),
        signal: AbortSignal.timeout(40000),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data: Propuesta = await res.json();
      if (data.requiere_aclaracion) {
        const pregunta = data.preguntas?.length ? data.preguntas.join(" ") : "¿Puedes darme un poco más de detalle?";
        addBot(pregunta);
      } else {
        addBot(data.resumen || "Esto es lo que entendí:");
        setPropuestaWorkflow(data);
        setAInvitarWorkflow(new Set((data.responsables_detectados || []).filter(r => r.email).map(r => r.email)));
      }
    } catch (error) {
      const timeout = error instanceof DOMException && error.name === "TimeoutError";
      addBot(timeout
        ? "Está tardando más de lo esperado. No guardé nada; prueba nuevamente o ármalo visualmente desde Configuración."
        : "Tuve un problema interpretando eso. No guardé nada; puedes intentarlo de nuevo.");
    } finally {
      setBusy(false);
    }
  };

  const enviar = () => (fase === "proceso" ? enviarProceso() : enviarPerfil());

  const usarLogoCandidato = async () => {
    if (!investigacion?.logo_candidatos?.[logoIdx] || logoOcupado) return;
    setLogoOcupado(true);
    try {
      const res = await authFetch(`${API_URL}/api/onboarding/sesion/${sessionId}/logo/candidato`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url: investigacion.logo_candidatos[logoIdx] }),
      });
      if (!res.ok) throw new Error();
      const { logo_url } = await res.json();
      setLogoUrlFinal(logo_url);
      addBot("Logo guardado.");
    } catch {
      addBot("No pude guardar ese logo. Puedes subir el tuyo o seguir sin logo por ahora.");
    } finally {
      setLogoOcupado(false);
    }
  };

  const subirLogoArchivo = async (archivo: File) => {
    if (!sessionId || logoOcupado) return;
    setLogoOcupado(true);
    try {
      const form = new FormData();
      form.append("archivo", archivo);
      const res = await authFetch(`${API_URL}/api/onboarding/sesion/${sessionId}/logo/subir`, { method: "POST", body: form });
      if (!res.ok) throw new Error();
      const { logo_url } = await res.json();
      setLogoUrlFinal(logo_url);
      addBot("Tu logo quedó guardado.");
    } catch {
      addBot("No pude subir ese archivo. Prueba con un PNG/JPG de menos de 3 MB.");
    } finally {
      setLogoOcupado(false);
    }
  };

  const corregirWorkflow = () => {
    setPropuestaWorkflow(null);
    addBot("Cuéntame qué cambiarías del proceso de compra.");
  };

  const confirmarWorkflow = async () => {
    if (!propuestaWorkflow || guardandoWorkflow) return;
    setGuardandoWorkflow(true);
    try {
      const responsables = (propuestaWorkflow.responsables_detectados || []).map(r => ({
        nombre: r.nombre,
        email: r.email || null,
        roles: r.roles,
        invitar: !!r.email && aInvitarWorkflow.has(r.email),
      }));

      const creado = await authFetch(`${API_URL}/api/workflows`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          nombre: nombreWorkflow.trim() || "Ciclo de compras",
          nodos: propuestaWorkflow.nodos,
          conexiones: propuestaWorkflow.conexiones,
          origen: "conversacional",
          responsables,
        }),
      }).then(r => r.json());

      // Sin pantalla intermedia: apenas queda guardado como borrador, se
      // pasa directo al canvas — ahí se ve la validación real y se puede
      // ajustar/activar (misma decisión que en /settings/autorizaciones).
      router.push(`/settings/autorizaciones/canvas/${creado.id}`);
    } catch {
      addBot("No pude guardar el ciclo de compras. Intenta de nuevo.");
    } finally {
      setGuardandoWorkflow(false);
    }
  };

  const irAlPanel = () => {
    if (floating) { onDone?.(); return; }
    router.replace("/dashboard");
  };

  const empezarProceso = () => {
    setFase("proceso");
    procesoDesdeRef.current = msgs.length + 1;
    addBot("Cuéntame cómo funciona hoy tu proceso de compras. Puede ser informal — por ejemplo: \"Los cotizadores preparan la comparación, después la revisa mi jefe, y si es sobre $500.000 también tiene que aprobar finanzas.\"");
  };

  const ofrecerConfigurarProceso = async () => {
    // Si ya existe un ciclo de compras, no tiene sentido ofrecer crear otro
    // — eso es justo lo que generaba ciclos duplicados. Se salta directo a
    // "listo, ve a Configuración a revisarlo" y termina el onboarding.
    let tieneWorkflow = false;
    if (userIdRef.current) {
      try {
        const lista = await fetch(`${API_URL}/api/workflows?user_id=${userIdRef.current}`).then(r => r.json());
        tieneWorkflow = Array.isArray(lista) && lista.length > 0;
      } catch { /* si falla el chequeo, se asume que no tiene y se ofrece igual */ }
    }
    if (tieneWorkflow) {
      addBot("Veo que ya tienes un ciclo de compras configurado — puedes revisarlo o ajustarlo cuando quieras desde Configuración.");
      setFase("proceso");
      irAlPanel();
      return;
    }
    setFase("transicion");
    addBot("¿Pasamos a configurar el proceso de compras? Te sirve para automatizar quién autoriza cada compra.");
  };

  // Confirma la sesión en el backend (perfil organizacional canónico) y
  // además hace backfill de user_metadata para no romper el resto de la app
  // que hoy lee empresa/rut/nombre_usuario/proceso_compra desde ahí.
  const confirmarYGuardar = async () => {
    if (!sessionId || finalizando) return;
    setFinalizando(true);
    try {
      const res = await authFetch(`${API_URL}/api/onboarding/sesion/${sessionId}/confirmar`, { method: "POST" });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        addBot(body.detail || "No pude confirmar tu perfil. Intenta de nuevo.");
        setFinalizando(false);
        return;
      }

      const { data: userData } = await createClient().auth.getUser();
      const prev = (userData.user?.user_metadata ?? {}) as Record<string, unknown>;
      const procesoTexto = draft.proceso_compra_texto?.valor?.trim() || (typeof prev.proceso_compra === "string" ? prev.proceso_compra : null);
      const { data, error } = await createClient().auth.updateUser({
        data: {
          ...prev,
          onboarding_completo: true,
          empresa: draft.empresa?.valor ?? prev.empresa ?? null,
          nombre_usuario: draft.nombre_usuario?.valor ?? prev.nombre_usuario ?? null,
          rut: draft.rut?.valor ?? prev.rut ?? null,
          industria: investigacion?.industria ?? (typeof prev.industria === "string" ? prev.industria : null),
          pais: investigacion?.pais ?? investigacion?.pais_tld ?? (typeof prev.pais === "string" ? prev.pais : null),
          logo_url: logoUrlFinal ?? (typeof prev.logo_url === "string" ? prev.logo_url : null),
          sitio_web: investigacion?.sitio_web ?? (typeof prev.sitio_web === "string" ? prev.sitio_web : null),
          categorias_default: investigacion?.categorias_compra_probables?.length ? investigacion.categorias_compra_probables.slice(0, 20) : (prev.categorias_default ?? []),
          proceso_compra: procesoTexto,
        },
      });
      if (error) throw error;

      if (data.user?.id) {
        fetch(`${API_URL}/api/procurement-profile/generar`, {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            user_id: data.user.id,
            empresa: draft.empresa?.valor ?? null,
            dominio: investigacion?.sitio_web ? investigacion.sitio_web.replace(/^https?:\/\//, "").replace(/^www\./, "") : null,
            industria: investigacion?.industria ?? null,
            pais: investigacion?.pais ?? null,
            categorias_probables: investigacion?.categorias_compra_probables ?? [],
            descripcion_actividad: investigacion?.descripcion ?? null,
            origen: "onboarding",
          }),
        }).catch(() => {});
      }

      addBot(`¡Listo, ${draft.nombre_usuario?.valor || ""}! Configuré tu cuenta de ${draft.empresa?.valor || "tu empresa"}.`);
      router.refresh();
      setFinalizando(false);
      await espera(400);
      await ofrecerConfigurarProceso();
    } catch (e) {
      addBot(`Hubo un problema guardando tu configuración: ${(e as Error).message || "error desconocido"}. Puedes completarlo luego en Configuración.`);
      setFinalizando(false);
    }
  };

  const entradaDeshabilitada = cargandoInicial || busy || (fase === "perfil" && completo) || fase === "transicion";

  return (
    <div style={{ flex: 1, display: "flex", flexDirection: "column", minHeight: 0 }}>
      <div ref={scrollRef} style={{ flex: 1, overflowY: "auto", padding: floating ? "16px 14px" : "28px 16px", minHeight: 0 }}>
        <div style={{ maxWidth: floating ? "100%" : 640, margin: "0 auto", display: "flex", flexDirection: "column", gap: 14 }}>
          <ChatBubbles mensajes={msgs.map((m): Mensaje => ({
            rol: m.rol,
            texto: m.texto,
            extra: m.card ? (
              <EmpresaCard
                d={m.card} logoIdx={logoIdx} logoUrlFinal={logoUrlFinal} logoOcupado={logoOcupado}
                onLogoError={() => setLogoIdx(x => x + 1)}
                onUsarLogo={usarLogoCandidato}
                onSubirArchivo={() => fileInputRef.current?.click()}
              />
            ) : undefined,
          }))} />

          {Object.keys(draft).length > 0 && fase === "perfil" && (
            <div style={{ marginLeft: 36, display: "flex", flexWrap: "wrap", gap: 6 }}>
              {Object.entries(draft).filter(([campo]) => ETIQUETAS_CAMPO[campo]).map(([campo, entrada]) => (
                <span key={campo} style={{
                  fontSize: 11.5, padding: "3px 9px", borderRadius: 999,
                  background: entrada.confirmado ? "var(--brand-50)" : "var(--n-100)",
                  color: entrada.confirmado ? "var(--brand)" : "var(--n-500)",
                  border: `1px solid ${entrada.confirmado ? "var(--brand-100)" : "var(--n-200)"}`,
                }}>
                  {ETIQUETAS_CAMPO[campo]}: {entrada.valor}
                </span>
              ))}
            </div>
          )}

          {propuestaWorkflow && propuestaWorkflow.etapas?.length > 0 && (
            <PropuestaWorkflowCard
              propuesta={propuestaWorkflow}
              aInvitar={aInvitarWorkflow}
              onToggleInvitar={(email, activo) => {
                setAInvitarWorkflow(prev => {
                  const s = new Set(prev);
                  if (activo) s.add(email); else s.delete(email);
                  return s;
                });
              }}
              nombreWorkflow={nombreWorkflow}
              onNombreWorkflowChange={setNombreWorkflow}
              onCorregir={corregirWorkflow}
              onConfirmar={confirmarWorkflow}
              cargando={guardandoWorkflow}
            />
          )}

          {fase === "perfil" && sugerenciasPendientes.length > 0 && (
            <div style={{ marginLeft: 36, display: "flex", flexWrap: "wrap", gap: 8 }}>
              {sugerenciasPendientes.map(s => (
                <BtnPrimary key={s.campo} onClick={() => confirmarSugerencia(s)} disabled={busy} size="sm">
                  Sí, {s.campo === "rut" ? "ese es el RUT" : "esa es la dirección"}
                </BtnPrimary>
              ))}
            </div>
          )}

          {fase === "perfil" && completo && (
            <div style={{ marginLeft: 36 }}>
              <BtnPrimary onClick={confirmarYGuardar} disabled={finalizando}>
                {finalizando ? "Guardando…" : "Confirmar y continuar"}
              </BtnPrimary>
            </div>
          )}

          {fase === "transicion" && (
            <div style={{ marginLeft: 36, display: "flex", gap: 8 }}>
              <BtnPrimary onClick={empezarProceso} size="sm">Sí, configurémoslo</BtnPrimary>
              <BtnGhost onClick={irAlPanel} size="sm">Ahora no</BtnGhost>
            </div>
          )}

          {(cargandoInicial || busy) && <TypingBubble icon={Bot} />}
        </div>
      </div>

      <input
        ref={fileInputRef} type="file" accept="image/png,image/jpeg,image/webp,image/svg+xml" style={{ display: "none" }}
        onChange={e => { const f = e.target.files?.[0]; if (f) subirLogoArchivo(f); e.target.value = ""; }}
      />

      <div style={{ borderTop: "1px solid var(--n-200)", padding: floating ? "10px 12px" : "14px 16px", background: "var(--surface)", flexShrink: 0 }}>
        <div style={{ maxWidth: floating ? "100%" : 640, margin: "0 auto", display: "flex", gap: 8, alignItems: "flex-end", flexWrap: floating ? "wrap" : "nowrap" }}>
          <textarea
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={e => { if (e.key === "Enter" && !e.shiftKey && !busy) { e.preventDefault(); enviar(); } }}
            placeholder="Escribe lo que quieras contarme…"
            rows={2}
            autoFocus
            disabled={entradaDeshabilitada}
            style={{
              flex: 1, minWidth: floating ? 120 : undefined, resize: "none",
              background: "var(--canvas)", color: "var(--n-900)",
              border: "1px solid var(--n-300)", borderRadius: "var(--r-md)",
              padding: "10px 14px", fontFamily: "inherit", fontSize: 14, lineHeight: 1.5, outline: "none",
            }}
          />
          <BtnPrimary onClick={enviar} disabled={busy || entradaDeshabilitada || !input.trim()}>
            <Send size={16} />
          </BtnPrimary>
          {fase === "perfil" && !completo && (
            <button onClick={omitirPorAhora} style={{ fontSize: 12.5, color: "var(--n-500)", background: "none", border: "none", cursor: "pointer", padding: "4px 2px", textDecoration: "underline", whiteSpace: "nowrap" }}>
              Omitir por ahora
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

function EmpresaCard({ d, logoIdx, logoUrlFinal, logoOcupado, onLogoError, onUsarLogo, onSubirArchivo }: {
  d: Investigacion; logoIdx: number; logoUrlFinal: string | null; logoOcupado: boolean;
  onLogoError: () => void; onUsarLogo: () => void; onSubirArchivo: () => void;
}) {
  const logo = logoUrlFinal ?? d.logo_candidatos?.[logoIdx];
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10, marginTop: 10, paddingTop: 12, borderTop: "1px solid var(--n-100)" }}>
      <div style={{ display: "flex", gap: 14, alignItems: "flex-start" }}>
        {logo ? (
          <img src={logo} alt="logo" width={52} height={52} onError={onLogoError}
            style={{ objectFit: "contain", borderRadius: 8, border: "1px solid var(--n-200)", background: "#fff", flexShrink: 0, padding: 4 }} />
        ) : (
          <div style={{
            width: 52, height: 52, borderRadius: 8, flexShrink: 0,
            background: "var(--brand-50)", color: "var(--brand)",
            display: "inline-flex", alignItems: "center", justifyContent: "center", fontSize: 22, fontWeight: 600,
          }}>{d.empresa?.charAt(0).toUpperCase() ?? "?"}</div>
        )}
        <div style={{ minWidth: 0 }}>
          <div style={{ fontSize: 15, fontWeight: 600, color: "var(--n-900)" }}>{d.empresa}</div>
          <div style={{ fontSize: 13, color: "var(--brand)", margin: "3px 0", fontWeight: 500 }}>
            {d.industria}{d.pais ? ` · ${d.pais}` : ""}
          </div>
          {d.descripcion && <div style={{ fontSize: 12.5, color: "var(--n-600)", lineHeight: 1.55 }}>{d.descripcion}</div>}
          {d.rut && (
            <div style={{ fontSize: 12, color: "var(--n-500)", marginTop: 6, fontFamily: "var(--font-mono)", fontVariantNumeric: "tabular-nums" }}>
              RUT: {d.rut}
            </div>
          )}
        </div>
      </div>
      {!logoUrlFinal && (
        <div style={{ display: "flex", gap: 8 }}>
          <button onClick={onUsarLogo} disabled={logoOcupado || !d.logo_candidatos?.[logoIdx]} className="btn-swiss-secondary" style={{ fontSize: 12 }}>
            {logoOcupado ? "…" : "Usar este logo"}
          </button>
          <button onClick={onSubirArchivo} disabled={logoOcupado} className="btn-swiss-secondary" style={{ fontSize: 12 }}>
            Subir mi logo
          </button>
        </div>
      )}
    </div>
  );
}
