"use client";
/**
 * Onboarding conversacional (estilo Ploy): tras verificar el correo, investiga la
 * empresa en background y va revelando lo encontrado como un chat, pidiendo al
 * usuario confirmar/completar: empresa, RUT, su nombre, logo y proceso de compra.
 * Guarda todo el perfil en user_metadata.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { createClient } from "@/lib/supabase/client";

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
type Fase = "cargando" | "pedir_nombre" | "confirmar_empresa" | "rut" | "nombre_usuario" | "logo" | "proceso" | "fin";

export default function OnboardingChatPage() {
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
      if (!u) { router.replace("/login"); return; }
      if (u.user_metadata?.onboarding_completo) { router.replace("/dashboard"); return; }
      const correo = u.email ?? "";
      setEmail(correo);
      const primer = (u.user_metadata?.full_name || correo.split("@")[0] || "").split(/[.\s]/)[0];
      setNombreUsuario(primer ? primer.charAt(0).toUpperCase() + primer.slice(1) : "");

      addBot(`¡Hola! Soy el asistente de Baiyer. Dame un segundo, estoy revisando tu empresa a partir de tu correo (${correo})…`);
      const d = await investigar(correo);
      if (d.es_empresa_conocida && d.empresa) {
        await revelarEmpresa(d);
      } else {
        aplicar(d);
        await espera(500);
        addBot("Tu correo es genérico, así que no pude detectarla sola. ¿Cómo se llama tu empresa? La busco por ti.");
        setFase("pedir_nombre");
      }
    });
  }, [investigar, router]);

  // Enviar (según fase)
  const enviar = async () => {
    const val = input.trim();

    if (fase === "pedir_nombre") {
      if (!val) return;
      addUser(val); setInput(""); setBusy(true);
      const d = await investigar(email, val);
      setBusy(false);
      if (d.es_empresa_conocida && d.empresa) await revelarEmpresa(d);
      else { const emp = extraer(val, "empresa"); setEmpresa(emp); addBot(`Anotado: ${emp}. No encontré más detalle, pero podemos seguir.`); setFase("rut"); await espera(400); preguntarRut(emp); }
      return;
    }

    if (fase === "confirmar_empresa") {
      // Si escribió algo, re-busca con ese nombre; si no, confirma
      if (val) {
        addUser(val); setInput(""); setBusy(true);
        const d = await investigar(email, val);
        setBusy(false);
        if (d.es_empresa_conocida && d.empresa) await revelarEmpresa(d);
        else { const emp = extraer(val, "empresa"); setEmpresa(emp); addBot(`Ok, usaré "${emp}".`); setFase("rut"); await espera(300); preguntarRut(emp); }
      }
      return;
    }

    if (fase === "rut") {
      addUser(val || "No lo sé");
      const rutLimpio = val && esConfirmacion(val) && rut ? rut : extraer(val, "rut");
      setRut(rutLimpio); setInput("");
      addBot("Perfecto.");
      setFase("nombre_usuario");
      await espera(300);
      addBot(`¿Y tú cómo te llamas?${nombreUsuario ? ` (¿"${nombreUsuario}"?)` : ""}`);
      return;
    }

    if (fase === "nombre_usuario") {
      const confirma = val && esConfirmacion(val) && nombreUsuario;
      const nom = confirma ? nombreUsuario : extraer(val || nombreUsuario, "nombre");
      if (!nom) return;
      addUser(val || nombreUsuario); setNombreUsuario(nom); setInput("");
      setFase("logo");
      await espera(300);
      addBot(`Encantado, ${nom}. ¿Este es el logo de tu empresa?`, inv ?? undefined);
      return;
    }

    if (fase === "proceso") {
      addUser(val || "—"); setInput("");
      await finalizar(val);
      return;
    }
  };

  const preguntarRut = (emp: string) => {
    setFase("rut");
    addBot(`¿Cuál es el RUT de ${emp}?${rut ? ` (encontré ${rut}, confírmalo o corrígelo)` : " (si no lo tienes a mano, puedes omitirlo)"}`);
  };

  // Al confirmar empresa
  const confirmarEmpresa = async () => {
    addUser("Sí, es correcta");
    setFase("rut");
    await espera(300);
    preguntarRut(empresa || inv?.empresa || "tu empresa");
  };

  // Logo
  const respLogo = async (ok: boolean) => {
    addUser(ok ? "Sí, es mi logo" : "Lo subo después");
    setFase("proceso");
    await espera(300);
    addBot("Última pregunta 👇 ¿Cómo funciona la compra en tu empresa? Cuéntame quién cotiza, quién autoriza y cómo se decide. (Con tu ritmo, en una frase basta.)");
  };

  const finalizar = async (proceso: string) => {
    setFase("fin");
    addBot(`¡Listo, ${nombreUsuario || ""}! Configuré tu cuenta de ${empresa || "tu empresa"}. Te llevo al dashboard…`);
    // Datos a guardar en user_metadata. Los logos scrapeados a veces vienen
    // enormes (data URLs, favicons con ?params); si el metadata excede el
    // límite de Supabase, todo el updateUser falla y el usuario ve una ventana
    // de error. Filtramos y limitamos por seguridad.
    const logoUrl = inv?.logo_candidatos?.[logoIdx] ?? null;
    const logoSeguro = logoUrl && logoUrl.length < 500 && logoUrl.startsWith("http") ? logoUrl : null;
    try {
      const { error } = await createClient().auth.updateUser({
        data: {
          onboarding_completo: true,
          empresa: empresa.trim() || null,
          nombre_usuario: nombreUsuario.trim() || null,
          industria: inv?.industria ?? null,
          rut: rut.trim() || null,
          logo_url: logoSeguro,
          sitio_web: inv?.sitio_web ?? null,
          pais: inv?.pais ?? inv?.pais_tld ?? null,
          categorias_default: (cats || []).slice(0, 20),
          proceso_compra: proceso.trim() || null,
        },
      });
      if (error) throw error;
      // Refresca la cookie del servidor con la sesión actualizada antes de
      // navegar. Sin esto, el AppShellServer puede leer una copia vieja.
      router.refresh();
      await espera(600);
      router.replace("/dashboard");
    } catch (e) {
      addBot(`Hubo un problema guardando tu configuración: ${(e as Error).message || "error desconocido"}. Igual te llevo al dashboard, puedes completar tus datos en Configuración.`);
      await espera(1500);
      router.replace("/dashboard");
    }
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
    <div style={{ minHeight: "100vh", background: "var(--canvas)", display: "flex", flexDirection: "column" }}>
      {/* Header con marca */}
      <div style={{
        borderBottom: "1px solid var(--n-200)",
        padding: "14px 24px",
        background: "var(--surface)",
        display: "flex", alignItems: "center", gap: 10,
      }}>
        <span style={{
          width: 28, height: 28, borderRadius: 8,
          background: "var(--brand)", color: "#fff",
          display: "inline-flex", alignItems: "center", justifyContent: "center",
          fontSize: 15, fontWeight: 700,
        }}>B</span>
        <div>
          <div style={{ fontSize: 14, fontWeight: 600, color: "var(--n-900)", letterSpacing: "-0.015em" }}>Baiyer</div>
          <div style={{ fontSize: 12, color: "var(--n-500)" }}>Configuración de tu cuenta</div>
        </div>
      </div>

      {/* Chat */}
      <div ref={scrollRef} style={{ flex: 1, overflowY: "auto", padding: "28px 16px" }}>
        <div style={{ maxWidth: 640, margin: "0 auto", display: "flex", flexDirection: "column", gap: 14 }}>
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
        padding: "14px 16px",
        background: "var(--surface)",
      }}>
        <div style={{ maxWidth: 640, margin: "0 auto", display: "flex", gap: 8, alignItems: "center" }}>
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
                  flex: 1, background: "var(--canvas)",
                  border: "1px solid var(--n-300)", borderRadius: "var(--r-md)",
                  padding: "10px 14px", fontSize: 14,
                  color: "var(--n-900)", fontFamily: "var(--font-sans)",
                  outline: "none",
                }}
              />
              <button onClick={enviar} disabled={busy} className="btn-swiss-primary" style={{ whiteSpace: "nowrap" }}>
                {busy ? "…" : (fase === "rut" || fase === "proceso") && !input.trim() ? "Omitir" : "Enviar"}
              </button>
            </>
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
