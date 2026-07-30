"use client";
/**
 * Chat conversacional que junta los datos de perfil requeridos (empresa, RUT,
 * nombre, industria). Se usa tanto en /onboarding (página completa, primera vez)
 * como flotando sobre el dashboard (OnboardingFloating) para retomar sólo lo que
 * falte sin repetir la conversación completa.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { createClient } from "@/lib/supabase/client";
import { camposFaltantes, type CampoRequerido } from "@/lib/onboarding";

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

type Rol = "bot" | "user";
interface Msg { rol: Rol; texto?: string; card?: Investigacion; logoIdx?: number; }
type Fase = "cargando" | "pedir_nombre" | "confirmar_empresa" | "rut" | "nombre_usuario" | "logo" | "proceso" | "fin" | "nada";

interface Props {
  /** Estilo compacto para panel flotante (sin header de página completa). */
  floating?: boolean;
  /** Se llama cuando terminó de guardar (o no había nada que hacer). En modo no-flotante, además navega a /dashboard. */
  onDone?: () => void;
  /** Botón "Omitir por ahora" (sólo modo flotante). */
  onSkip?: () => void;
}

export default function OnboardingChat({ floating, onDone, onSkip }: Props) {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [inv, setInv] = useState<Investigacion | null>(null);
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [fase, setFase] = useState<Fase>("cargando");
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [logoIdx, setLogoIdx] = useState(0);

  // Datos que se van juntando
  const [empresa, setEmpresa] = useState("");
  const [rut, setRut] = useState("");
  const [nombreUsuario, setNombreUsuario] = useState("");
  const [cats, setCats] = useState<string[]>([]);

  // true = flujo completo (empresa desconocida, incluye logo/proceso). false = sólo faltan rut/nombre.
  const [modoCompleto, setModoCompleto] = useState(true);
  const metaExistenteRef = useRef<Record<string, unknown>>({});
  const faltanRef = useRef<CampoRequerido[]>([]);

  const scrollRef = useRef<HTMLDivElement>(null);
  useEffect(() => { scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" }); }, [msgs, fase]);

  const esConfirmacion = (t: string): boolean =>
    /^(s[ií]|si+|ok|correcto|exacto|ese|esa|eso|claro|dale|ya|sep|sip|confirmo|está bien|esta bien|así es|asi es|afirmativo|yeap?|yes|yep|sí,?\s*es)$/i.test(t.trim());

  const extraer = (texto: string, campo: "rut" | "nombre" | "empresa"): string => {
    const t = texto.trim();
    if (!t) return "";
    if (campo === "rut") {
      const m = t.match(/(\d{1,3}\.?\d{3}\.?\d{3}-[\dkK])/i);
      return m ? m[1] : t;
    }
    if (campo === "nombre") {
      return t
        .replace(/^(me llamo|mi nombre es|mi nombre completo es|soy|me dicen)\s+/i, "")
        .replace(/[.!,]+$/, "")
        .trim();
    }
    if (campo === "empresa") {
      return t
        .replace(/^(se llama|la empresa es|mi empresa es|nuestra empresa es|somos|es|trabajo en|estoy en)\s+/i, "")
        .replace(/[.!,]+$/, "")
        .trim();
    }
    return t;
  };

  const addBot = (texto?: string, card?: Investigacion) => setMsgs(m => [...m, { rol: "bot", texto, card }]);
  const addUser = (texto: string) => setMsgs(m => [...m, { rol: "user", texto }]);
  const espera = (ms: number) => new Promise(r => setTimeout(r, ms));

  const aplicar = (d: Investigacion) => {
    setInv(d); setLogoIdx(0);
    if (d.empresa) setEmpresa(d.empresa);
    if (d.rut) setRut(d.rut);
    if (d.categorias_compra_probables?.length) setCats(d.categorias_compra_probables);
  };

  const investigar = useCallback(async (correo: string, nombre?: string): Promise<Investigacion> => {
    try {
      const res = await fetch(`${API_URL}/api/onboarding/investigar-empresa`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: correo, nombre_empresa: nombre }),
      });
      return res.ok ? await res.json() : { empresa: null };
    } catch { return { empresa: null }; }
  }, []);

  // Guarda lo recolectado, mezclado con lo que ya existía en user_metadata
  // (para no borrar datos de una sesión de onboarding anterior).
  const guardar = useCallback(async (proceso?: string) => {
    setFase("fin");
    if (!floating) addBot(`¡Listo, ${nombreUsuario || ""}! Configuré tu cuenta de ${empresa || "tu empresa"}. Te llevo al dashboard…`);
    const prev = metaExistenteRef.current;
    const logoUrl = inv?.logo_candidatos?.[logoIdx] ?? null;
    const logoSeguro = logoUrl && logoUrl.length < 500 && logoUrl.startsWith("http") ? logoUrl : null;
    try {
      const empresaFinal = empresa.trim() || (typeof prev.empresa === "string" ? prev.empresa : null);
      const industriaFinal = inv?.industria ?? (typeof prev.industria === "string" ? prev.industria : null);
      const paisFinal = inv?.pais ?? inv?.pais_tld ?? (typeof prev.pais === "string" ? prev.pais : null);
      const categoriasFinal = cats.length ? cats.slice(0, 20) : (prev.categorias_default ?? []);
      const { data, error } = await createClient().auth.updateUser({
        data: {
          ...prev,
          onboarding_completo: true,
          empresa: empresaFinal,
          nombre_usuario: nombreUsuario.trim() || (typeof prev.nombre_usuario === "string" ? prev.nombre_usuario : null),
          industria: industriaFinal,
          rut: rut.trim() || (typeof prev.rut === "string" ? prev.rut : null),
          logo_url: logoSeguro ?? (typeof prev.logo_url === "string" ? prev.logo_url : null),
          sitio_web: inv?.sitio_web ?? (typeof prev.sitio_web === "string" ? prev.sitio_web : null),
          pais: paisFinal,
          categorias_default: categoriasFinal,
          proceso_compra: (proceso ?? "").trim() || (typeof prev.proceso_compra === "string" ? prev.proceso_compra : null),
        },
      });
      if (error) throw error;

      // Genera/actualiza el perfil de procurement (prior inicial para búsqueda
      // e identificación) — no bloquea el onboarding si falla.
      if (data.user?.id) {
        fetch(`${API_URL}/api/procurement-profile/generar`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            user_id: data.user.id,
            empresa: empresaFinal,
            dominio: inv?.sitio_web ? inv.sitio_web.replace(/^https?:\/\//, "").replace(/^www\./, "") : null,
            industria: industriaFinal,
            pais: paisFinal,
            categorias_probables: categoriasFinal,
            descripcion_actividad: inv?.descripcion ?? null,
            origen: "onboarding",
          }),
        }).catch(() => {});
      }

      router.refresh();
      if (floating) { onDone?.(); return; }
      await espera(600);
      router.replace("/dashboard");
    } catch (e) {
      if (!floating) {
        addBot(`Hubo un problema guardando tu configuración: ${(e as Error).message || "error desconocido"}. Igual te llevo al dashboard, puedes completar tus datos en Configuración.`);
        await espera(1500);
        router.replace("/dashboard");
      } else {
        addBot(`No pude guardar: ${(e as Error).message || "error desconocido"}. Puedes completarlo luego en Configuración.`);
        await espera(1500);
        onDone?.();
      }
    }
  }, [empresa, nombreUsuario, rut, inv, logoIdx, cats, floating, onDone, router]);

  // Decide el siguiente paso una vez que la empresa quedó determinada.
  const siguienteTrasEmpresa = useCallback(async (empNombre: string) => {
    if (faltanRef.current.includes("rut")) {
      setFase("rut");
      await espera(300);
      preguntarRut(empNombre);
    } else if (faltanRef.current.includes("nombre_usuario")) {
      setFase("nombre_usuario");
      await espera(300);
      addBot(`¿Y tú cómo te llamas?${nombreUsuario ? ` (¿"${nombreUsuario}"?)` : ""}`);
    } else if (modoCompleto) {
      setFase("logo");
      await espera(300);
      addBot(`¿Este es el logo de tu empresa?`, inv ?? undefined);
    } else {
      await guardar();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nombreUsuario, modoCompleto, inv, guardar]);

  // Muestra el reporte de la empresa encontrada y pasa a confirmar
  const revelarEmpresa = async (d: Investigacion) => {
    aplicar(d);
    await espera(400); addBot(undefined, d);
    await espera(600); addBot(`Se dedica a ${d.industria ?? "—"}${d.pais ? ` en ${d.pais}` : ""}. ¿Es tu empresa? Si el nombre no es exacto, corrígelo.`);
    setFase("confirmar_empresa");
  };

  // Arranque
  useEffect(() => {
    createClient().auth.getUser().then(async ({ data }) => {
      const u = data.user;
      if (!u) { if (!floating) router.replace("/login"); return; }
      const m = (u.user_metadata ?? {}) as Record<string, unknown>;
      metaExistenteRef.current = m;
      const faltan = camposFaltantes(m);
      faltanRef.current = faltan;

      if (floating && faltan.length === 0) { onDone?.(); return; }
      if (!floating && u.user_metadata?.onboarding_completo && faltan.length === 0) { router.replace("/dashboard"); return; }

      const correo = u.email ?? "";
      setEmail(correo);
      const nombreYaGuardado = typeof m.nombre_usuario === "string" ? m.nombre_usuario : "";
      const primer = (nombreYaGuardado || u.user_metadata?.full_name || correo.split("@")[0] || "").split(/[.\s]/)[0];
      setNombreUsuario(primer ? primer.charAt(0).toUpperCase() + primer.slice(1) : "");
      if (typeof m.empresa === "string") setEmpresa(m.empresa);
      if (typeof m.rut === "string") setRut(m.rut);

      const necesitaEmpresa = faltan.includes("empresa") || faltan.includes("industria");
      setModoCompleto(necesitaEmpresa);

      if (necesitaEmpresa) {
        addBot(floating
          ? `¡Hola! Para terminar de configurar tu cuenta, dame un segundo, estoy revisando tu empresa a partir de tu correo (${correo})…`
          : `¡Hola! Soy el asistente de Baiyer. Dame un segundo, estoy revisando tu empresa a partir de tu correo (${correo})…`);
        const d = await investigar(correo);
        if (d.es_empresa_conocida && d.empresa) {
          await revelarEmpresa(d);
        } else {
          aplicar(d);
          await espera(500);
          addBot("Tu correo es genérico, así que no pude detectarla sola. ¿Cómo se llama tu empresa? La busco por ti.");
          setFase("pedir_nombre");
        }
      } else if (faltan.includes("rut")) {
        addBot(`¡Hola${nombreYaGuardado ? ` ${nombreYaGuardado}` : ""}! Antes de seguir, necesito un dato más de tu perfil.`);
        await espera(300);
        setFase("rut");
        preguntarRut(m.empresa as string || "tu empresa");
      } else if (faltan.includes("nombre_usuario")) {
        addBot("¡Hola! Antes de seguir, ¿cómo te llamas?");
        setFase("nombre_usuario");
      } else {
        onDone?.();
      }
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [investigar, router, floating]);

  // Enviar (según fase)
  const enviar = async () => {
    const val = input.trim();

    if (fase === "pedir_nombre") {
      if (!val) return;
      addUser(val); setInput(""); setBusy(true);
      const d = await investigar(email, val);
      setBusy(false);
      if (d.es_empresa_conocida && d.empresa) await revelarEmpresa(d);
      else { const emp = extraer(val, "empresa"); setEmpresa(emp); addBot(`Anotado: ${emp}. No encontré más detalle, pero podemos seguir.`); await siguienteTrasEmpresa(emp); }
      return;
    }

    if (fase === "confirmar_empresa") {
      // Si escribió algo, re-busca con ese nombre; si no, confirma
      if (val) {
        addUser(val); setInput(""); setBusy(true);
        const d = await investigar(email, val);
        setBusy(false);
        if (d.es_empresa_conocida && d.empresa) await revelarEmpresa(d);
        else { const emp = extraer(val, "empresa"); setEmpresa(emp); addBot(`Ok, usaré "${emp}".`); await siguienteTrasEmpresa(emp); }
      }
      return;
    }

    if (fase === "rut") {
      addUser(val || "No lo sé");
      const rutLimpio = val && esConfirmacion(val) && rut ? rut : extraer(val, "rut");
      setRut(rutLimpio); setInput("");
      addBot("Perfecto.");
      if (faltanRef.current.includes("nombre_usuario")) {
        setFase("nombre_usuario");
        await espera(300);
        addBot(`¿Y tú cómo te llamas?${nombreUsuario ? ` (¿"${nombreUsuario}"?)` : ""}`);
      } else if (modoCompleto) {
        setFase("nombre_usuario");
        await espera(300);
        addBot(`¿Y tú cómo te llamas?${nombreUsuario ? ` (¿"${nombreUsuario}"?)` : ""}`);
      } else {
        await guardar();
      }
      return;
    }

    if (fase === "nombre_usuario") {
      const confirma = val && esConfirmacion(val) && nombreUsuario;
      const nom = confirma ? nombreUsuario : extraer(val || nombreUsuario, "nombre");
      if (!nom) return;
      addUser(val || nombreUsuario); setNombreUsuario(nom); setInput("");
      if (modoCompleto) {
        setFase("logo");
        await espera(300);
        addBot(`Encantado, ${nom}. ¿Este es el logo de tu empresa?`, inv ?? undefined);
      } else {
        await guardar();
      }
      return;
    }

    if (fase === "proceso") {
      addUser(val || "—"); setInput("");
      await guardar(val);
      return;
    }
  };

  const preguntarRut = (emp: string) => {
    addBot(`¿Cuál es el RUT de ${emp}?${rut ? ` (encontré ${rut}, confírmalo o corrígelo)` : " (si no lo tienes a mano, puedes omitirlo)"}`);
  };

  // Al confirmar empresa
  const confirmarEmpresa = async () => {
    addUser("Sí, es correcta");
    await siguienteTrasEmpresa(empresa || inv?.empresa || "tu empresa");
  };

  // Cortar el ping-pong si el bot no encuentra la empresa: usa lo que haya
  // tipeado el usuario (o el nombre ya anotado, o "Mi empresa") y sigue.
  const saltarBusquedaEmpresa = async () => {
    const val = input.trim();
    const emp = val ? extraer(val, "empresa") : (empresa || "Mi empresa");
    addUser(val ? `Es "${emp}", no busques más` : "Sigamos sin buscar la empresa");
    setEmpresa(emp);
    setInput("");
    addBot(`Ok, uso "${emp}" tal cual. Podrás afinar los detalles después en Configuración.`);
    await siguienteTrasEmpresa(emp);
  };

  // Logo
  const respLogo = async (ok: boolean) => {
    addUser(ok ? "Sí, es mi logo" : "Lo subo después");
    setFase("proceso");
    await espera(300);
    addBot("Última pregunta 👇 ¿Cómo funciona la compra en tu empresa? Cuéntame quién cotiza, quién autoriza y cómo se decide. (Con tu ritmo, en una frase basta.)");
  };

  // ── Input activo según fase ──
  const inputTexto = fase === "pedir_nombre" || fase === "confirmar_empresa" || fase === "rut" || fase === "nombre_usuario" || fase === "proceso";
  const placeholder =
    fase === "pedir_nombre" ? "Nombre de tu empresa…" :
    fase === "confirmar_empresa" ? "Corrige el nombre (o pulsa Sí)…" :
    fase === "rut" ? "99.999.999-9 (o deja vacío)…" :
    fase === "nombre_usuario" ? (nombreUsuario || "Tu nombre…") :
    fase === "proceso" ? "Ej: yo cotizo y mi jefe autoriza sobre $500.000…" : "";

  return (
    <div style={{ height: "100%", display: "flex", flexDirection: "column", minHeight: 0 }}>
      {/* Chat */}
      <div ref={scrollRef} style={{ flex: 1, overflowY: "auto", padding: floating ? "16px 14px" : "28px 16px", minHeight: 0 }}>
        <div style={{ maxWidth: floating ? "100%" : 640, margin: "0 auto", display: "flex", flexDirection: "column", gap: 14 }}>
          {msgs.map((m, i) => (
            <div key={i} style={{
              display: "flex",
              gap: 10,
              justifyContent: m.rol === "user" ? "flex-end" : "flex-start",
              alignItems: "flex-start",
            }}>
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
                {m.card && <EmpresaCard d={m.card} logoIdx={logoIdx} onLogoError={() => setLogoIdx(x => x + 1)} />}
              </div>
            </div>
          ))}
          {(fase === "cargando" || busy) && <TypingDots />}
        </div>
      </div>

      {/* Barra de acción */}
      <div style={{
        borderTop: "1px solid var(--n-200)",
        padding: floating ? "10px 12px" : "14px 16px",
        background: "var(--surface)",
        flexShrink: 0,
      }}>
        <div style={{ maxWidth: floating ? "100%" : 640, margin: "0 auto", display: "flex", gap: 8, alignItems: "center", flexWrap: floating ? "wrap" : "nowrap" }}>
          {fase === "confirmar_empresa" && (
            <button onClick={confirmarEmpresa} disabled={busy} className="btn-swiss-primary" style={{ whiteSpace: "nowrap" }}>Sí, es correcta ✓</button>
          )}
          {fase === "logo" && (
            <>
              <button onClick={() => respLogo(true)} className="btn-swiss-primary" style={{ flex: 1 }}>Sí, es mi logo</button>
              <button onClick={() => respLogo(false)} className="btn-swiss-secondary">Subir después</button>
            </>
          )}
          {inputTexto && (
            <>
              <input
                value={input}
                onChange={e => setInput(e.target.value)}
                onKeyDown={e => { if (e.key === "Enter" && !busy) enviar(); }}
                placeholder={placeholder}
                autoFocus
                style={{
                  flex: 1, minWidth: floating ? 120 : undefined, background: "var(--canvas)",
                  border: "1px solid var(--n-300)", borderRadius: "var(--r-md)",
                  padding: "10px 14px", fontSize: 14,
                  color: "var(--n-900)", fontFamily: "var(--font-sans)",
                  outline: "none",
                }}
              />
              {(fase === "pedir_nombre" || fase === "confirmar_empresa") && (
                <button onClick={saltarBusquedaEmpresa} disabled={busy} className="btn-swiss-secondary" style={{ whiteSpace: "nowrap" }}>
                  Seguir sin buscar
                </button>
              )}
              <button onClick={enviar} disabled={busy} className="btn-swiss-primary" style={{ whiteSpace: "nowrap" }}>
                {busy ? "…" : (fase === "rut" || fase === "proceso") && !input.trim() ? "Omitir" : "Enviar"}
              </button>
            </>
          )}
          {floating && onSkip && fase !== "fin" && (
            <button onClick={onSkip} style={{
              fontSize: 12.5, color: "var(--n-500)", background: "none", border: "none",
              cursor: "pointer", padding: "4px 2px", textDecoration: "underline",
            }}>
              Omitir por ahora
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

function EmpresaCard({ d, logoIdx, onLogoError }: { d: Investigacion; logoIdx: number; onLogoError: () => void }) {
  const logo = d.logo_candidatos?.[logoIdx];
  return (
    <div style={{
      display: "flex", gap: 14, alignItems: "flex-start",
      marginTop: 10, paddingTop: 12, borderTop: "1px solid var(--n-100)",
    }}>
      {logo ? (
        <img src={logo} alt="logo" width={52} height={52} onError={onLogoError}
          style={{ objectFit: "contain", borderRadius: 8, border: "1px solid var(--n-200)", background: "#fff", flexShrink: 0, padding: 4 }} />
      ) : (
        <div style={{
          width: 52, height: 52, borderRadius: 8, flexShrink: 0,
          background: "var(--brand-50)", color: "var(--brand)",
          display: "inline-flex", alignItems: "center", justifyContent: "center",
          fontSize: 22, fontWeight: 600,
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
  );
}

function TypingDots() {
  return (
    <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
      <span style={{
        width: 28, height: 28, borderRadius: 8, flexShrink: 0,
        background: "var(--brand-50)", color: "var(--brand)",
        display: "inline-flex", alignItems: "center", justifyContent: "center",
        fontSize: 14, fontWeight: 700,
      }}>B</span>
      <div style={{
        background: "var(--surface)", border: "1px solid var(--n-200)",
        borderRadius: "16px 16px 16px 4px", padding: "12px 16px",
        display: "flex", gap: 5, alignItems: "center",
        boxShadow: "var(--shadow-card)",
      }}>
        {[0, 1, 2].map(i => (
          <span key={i} style={{
            width: 7, height: 7, borderRadius: "50%", background: "var(--n-400)",
            animation: `pulseDot 1.2s ease-in-out ${i * 0.15}s infinite`,
          }} />
        ))}
        <style>{`@keyframes pulseDot { 0%,60%,100% { opacity:.3; transform: scale(.85) } 30% { opacity:1; transform: scale(1) } }`}</style>
      </div>
    </div>
  );
}
