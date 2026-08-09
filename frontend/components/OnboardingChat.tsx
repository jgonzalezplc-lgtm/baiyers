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
 * Se usa tanto en /onboarding (página completa, primera vez) como flotando
 * sobre el dashboard (OnboardingFloating) para retomar sólo lo que falte.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { createClient } from "@/lib/supabase/client";
import { authFetch } from "@/lib/authFetch";
import { camposFaltantes } from "@/lib/onboarding";
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

interface Props {
  /** Estilo compacto para panel flotante (sin header de página completa). */
  floating?: boolean;
  /** Se llama cuando terminó de guardar (o no había nada que hacer). En modo no-flotante, además navega a /dashboard. */
  onDone?: () => void;
  /** Botón "Omitir por ahora" (sólo modo flotante). */
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

  // Ciclo de compras (Fase 3): mismo mecanismo real que /settings/autorizaciones,
  // no una preview — crea el workflow, invita responsables y permite activarlo.
  const [aInvitarWorkflow, setAInvitarWorkflow] = useState<Set<string>>(new Set());
  const [nombreWorkflow, setNombreWorkflow] = useState("Ciclo de compras");
  const [guardandoWorkflow, setGuardandoWorkflow] = useState(false);
  const emailsVistosRef = useRef<Set<string>>(new Set());

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
        addBot("¿Es tu empresa? Cuéntame lo que haga falta corregir, o dime de una vez tu RUT, tu nombre y cómo funciona la compra en tu empresa — todo junto si quieres.");
      } else {
        await espera(300);
        addBot("No reconocí tu empresa automáticamente. Cuéntame su nombre, tu RUT y cómo te llamas — puedes darlo todo en un solo mensaje.");
      }
      setCargandoInicial(false);
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [investigar, router, floating]);

  const enviar = async () => {
    const mensaje = input.trim();
    if (!mensaje || !sessionId || busy) return;
    setInput("");
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
        if (d.direccion && !draft.direccion?.valor) {
          addBot(`Encontré esta dirección: ${d.direccion}. ¿La confirmas o la corriges?`);
        }
      }
    } catch {
      addUser(mensaje);
      addBot("Tuve un problema procesando eso. Puedes intentarlo de nuevo.");
    } finally {
      setBusy(false);
    }
  };

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
      if (floating) { onDone?.(); return; }
      await espera(600);
      router.replace("/dashboard");
    } catch (e) {
      addBot(`Hubo un problema guardando tu configuración: ${(e as Error).message || "error desconocido"}. Puedes completarlo luego en Configuración.`);
      setFinalizando(false);
    }
  };

  return (
    <div style={{ flex: 1, display: "flex", flexDirection: "column", minHeight: 0 }}>
      <div ref={scrollRef} style={{ flex: 1, overflowY: "auto", padding: floating ? "16px 14px" : "28px 16px", minHeight: 0 }}>
        <div style={{ maxWidth: floating ? "100%" : 640, margin: "0 auto", display: "flex", flexDirection: "column", gap: 14 }}>
          {msgs.map((m, i) => (
            <div key={i} style={{ display: "flex", gap: 10, justifyContent: m.rol === "user" ? "flex-end" : "flex-start", alignItems: "flex-start" }}>
              {m.rol === "bot" && (
                <span style={{
                  width: 28, height: 28, borderRadius: 8, flexShrink: 0,
                  background: "var(--brand-50)", color: "var(--brand)",
                  display: "inline-flex", alignItems: "center", justifyContent: "center",
                  fontSize: 14, fontWeight: 700, marginTop: 2,
                }}>B</span>
              )}
              <div style={{
                maxWidth: "78%",
                background: m.rol === "user" ? "var(--brand)" : "var(--surface)",
                color: m.rol === "user" ? "#fff" : "var(--n-900)",
                border: m.rol === "user" ? "none" : "1px solid var(--n-200)",
                borderRadius: m.rol === "user" ? "16px 16px 4px 16px" : "16px 16px 16px 4px",
                boxShadow: m.rol === "bot" ? "var(--shadow-card)" : "none",
                padding: m.card ? 16 : "10px 14px",
                fontSize: 14, lineHeight: 1.55,
              }}>
                {m.texto}
                {m.card && (
                  <EmpresaCard
                    d={m.card} logoIdx={logoIdx} logoUrlFinal={logoUrlFinal} logoOcupado={logoOcupado}
                    onLogoError={() => setLogoIdx(x => x + 1)}
                    onUsarLogo={usarLogoCandidato}
                    onSubirArchivo={() => fileInputRef.current?.click()}
                  />
                )}
              </div>
            </div>
          ))}

          {Object.keys(draft).length > 0 && (
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

          {completo && (
            <div style={{ marginLeft: 36 }}>
              <button onClick={confirmarYGuardar} disabled={finalizando} className="btn-swiss-primary">
                {finalizando ? "Guardando…" : "Confirmar y continuar"}
              </button>
            </div>
          )}

          {(cargandoInicial || busy) && <TypingDots />}
        </div>
      </div>

      <input
        ref={fileInputRef} type="file" accept="image/png,image/jpeg,image/webp,image/svg+xml" style={{ display: "none" }}
        onChange={e => { const f = e.target.files?.[0]; if (f) subirLogoArchivo(f); e.target.value = ""; }}
      />

      <div style={{ borderTop: "1px solid var(--n-200)", padding: floating ? "10px 12px" : "14px 16px", background: "var(--surface)", flexShrink: 0 }}>
        <div style={{ maxWidth: floating ? "100%" : 640, margin: "0 auto", display: "flex", gap: 8, alignItems: "center", flexWrap: floating ? "wrap" : "nowrap" }}>
          <input
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={e => { if (e.key === "Enter" && !busy) enviar(); }}
            placeholder="Escribe lo que quieras contarme…"
            autoFocus
            disabled={cargandoInicial || completo}
            style={{
              flex: 1, minWidth: floating ? 120 : undefined, background: "var(--canvas)",
              border: "1px solid var(--n-300)", borderRadius: "var(--r-md)",
              padding: "10px 14px", fontSize: 14, color: "var(--n-900)", fontFamily: "var(--font-sans)", outline: "none",
            }}
          />
          <button onClick={enviar} disabled={busy || cargandoInicial || completo || !input.trim()} className="btn-swiss-primary" style={{ whiteSpace: "nowrap" }}>
            {busy ? "…" : "Enviar"}
          </button>
          {floating && onSkip && !completo && (
            <button onClick={onSkip} style={{ fontSize: 12.5, color: "var(--n-500)", background: "none", border: "none", cursor: "pointer", padding: "4px 2px", textDecoration: "underline" }}>
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

function TypingDots() {
  return (
    <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
      <span style={{
        width: 28, height: 28, borderRadius: 8, flexShrink: 0,
        background: "var(--brand-50)", color: "var(--brand)",
        display: "inline-flex", alignItems: "center", justifyContent: "center", fontSize: 14, fontWeight: 700,
      }}>B</span>
      <div style={{
        background: "var(--surface)", border: "1px solid var(--n-200)",
        borderRadius: "16px 16px 16px 4px", padding: "12px 16px",
        display: "flex", gap: 5, alignItems: "center", boxShadow: "var(--shadow-card)",
      }}>
        {[0, 1, 2].map(i => (
          <span key={i} style={{ width: 7, height: 7, borderRadius: "50%", background: "var(--n-400)", animation: `pulseDot 1.2s ease-in-out ${i * 0.15}s infinite` }} />
        ))}
        <style>{`@keyframes pulseDot { 0%,60%,100% { opacity:.3; transform: scale(.85) } 30% { opacity:1; transform: scale(1) } }`}</style>
      </div>
    </div>
  );
}
