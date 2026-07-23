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
      else { setEmpresa(val); addBot(`Anotado: ${val}. No encontré más detalle, pero podemos seguir.`); setFase("rut"); await espera(400); preguntarRut(val); }
      return;
    }

    if (fase === "confirmar_empresa") {
      // Si escribió algo, re-busca con ese nombre; si no, confirma
      if (val) {
        addUser(val); setInput(""); setBusy(true);
        const d = await investigar(email, val);
        setBusy(false);
        if (d.es_empresa_conocida && d.empresa) await revelarEmpresa(d);
        else { setEmpresa(val); addBot(`Ok, usaré "${val}".`); setFase("rut"); await espera(300); preguntarRut(val); }
      }
      return;
    }

    if (fase === "rut") {
      addUser(val || "No lo sé"); setRut(val); setInput("");
      addBot("Perfecto.");
      setFase("nombre_usuario");
      await espera(300);
      addBot(`¿Y tú cómo te llamas?${nombreUsuario ? ` (¿"${nombreUsuario}"?)` : ""}`);
      return;
    }

    if (fase === "nombre_usuario") {
      const nom = val || nombreUsuario;
      if (!nom) return;
      addUser(nom); setNombreUsuario(nom); setInput("");
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
    await createClient().auth.updateUser({
      data: {
        onboarding_completo: true,
        empresa: empresa.trim() || null,
        nombre_usuario: nombreUsuario.trim() || null,
        industria: inv?.industria ?? null,
        rut: rut.trim() || null,
        logo_url: inv?.logo_candidatos?.[logoIdx] ?? null,
        sitio_web: inv?.sitio_web ?? null,
        pais: inv?.pais ?? inv?.pais_tld ?? null,
        categorias_default: cats,
        proceso_compra: proceso.trim() || null,
      },
    });
    await espera(900);
    router.replace("/dashboard");
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
    <div style={{ minHeight: "100vh", background: "var(--bg-base)", display: "flex", flexDirection: "column" }}>
      <div style={{ borderBottom: "1px solid var(--border-default)", padding: "14px 20px" }}>
        <span className="label" style={{ color: "var(--accent)", fontWeight: 800 }}>BAIYER · CONFIGURACIÓN</span>
      </div>

      {/* Chat */}
      <div ref={scrollRef} style={{ flex: 1, overflowY: "auto", padding: "24px 16px" }}>
        <div style={{ maxWidth: 560, margin: "0 auto", display: "flex", flexDirection: "column", gap: 12 }}>
          {msgs.map((m, i) => (
            <div key={i} style={{ display: "flex", justifyContent: m.rol === "user" ? "flex-end" : "flex-start" }}>
              <div style={{
                maxWidth: "85%",
                background: m.rol === "user" ? "var(--accent)" : "var(--bg-surface)",
                color: m.rol === "user" ? "#fff" : "var(--text-primary)",
                border: m.rol === "user" ? "none" : "1px solid var(--border-default)",
                padding: m.card ? 14 : "10px 14px", fontSize: 13, lineHeight: 1.5,
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
      <div style={{ borderTop: "1px solid var(--border-default)", padding: "12px 16px", background: "var(--bg-base)" }}>
        <div style={{ maxWidth: 560, margin: "0 auto", display: "flex", gap: 8, alignItems: "center" }}>
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
                style={{ flex: 1, background: "var(--bg-surface)", border: "1px solid var(--border-default)", padding: "10px 12px", fontSize: 13, color: "var(--text-primary)", fontFamily: "var(--font-mono)", outline: "none" }}
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
    <div style={{ display: "flex", gap: 12, alignItems: "flex-start", marginTop: 8, paddingTop: 10, borderTop: "1px solid var(--border-subtle)" }}>
      {logo && (
        <img src={logo} alt="logo" width={48} height={48} onError={onLogoError}
          style={{ objectFit: "contain", border: "1px solid var(--border-subtle)", background: "#fff", flexShrink: 0 }} />
      )}
      <div style={{ minWidth: 0 }}>
        <div style={{ fontSize: 15, fontWeight: 800 }}>{d.empresa}</div>
        <div className="label" style={{ color: "var(--accent)", margin: "2px 0" }}>{d.industria}{d.pais ? ` · ${d.pais}` : ""}</div>
        {d.descripcion && <div style={{ fontSize: 11, color: "var(--text-secondary)", lineHeight: 1.5 }}>{d.descripcion}</div>}
        {d.rut && <div className="label" style={{ color: "var(--text-muted)", marginTop: 4 }}>RUT: {d.rut}</div>}
      </div>
    </div>
  );
}

function TypingDots() {
  return (
    <div style={{ display: "flex", gap: 5, padding: "8px 14px" }}>
      {[0, 1, 2].map(i => <div key={i} style={{ width: 7, height: 7, borderRadius: "50%", background: "var(--text-muted)", animation: "pulse 1s infinite", animationDelay: `${i * 0.15}s` }} />)}
      <style>{`@keyframes pulse { 0%,100% { opacity:.3 } 50% { opacity:1 } }`}</style>
    </div>
  );
}
