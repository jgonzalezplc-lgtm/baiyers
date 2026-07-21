"use client";
/**
 * Onboarding inteligente (estilo Ploy): al crear la cuenta, investiga la empresa
 * desde el dominio del correo y acompaña la configuración confirmando empresa,
 * logo, RUT, dirección e industria. Guarda el perfil en user_metadata.
 */
import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { createClient } from "@/lib/supabase/client";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const CATEGORIAS: { key: string; label: string }[] = [
  { key: "industrial", label: "Industrial" }, { key: "construccion", label: "Construcción" },
  { key: "carpinteria", label: "Carpintería / Madera" }, { key: "electrico", label: "Eléctrico" },
  { key: "electronica", label: "Electrónica" }, { key: "mecanico", label: "Mecánico" },
  { key: "hidraulico", label: "Hidráulico" }, { key: "neumatico", label: "Neumático" },
  { key: "tuberias_valvulas", label: "Tuberías y válvulas" }, { key: "insumos_medicos", label: "Insumos médicos" },
  { key: "consumible", label: "Consumible" }, { key: "servicio", label: "Servicio" },
];

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

type Paso = "investigando" | "empresa" | "datos" | "categorias" | "guardando";

export default function OnboardingPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [inv, setInv] = useState<Investigacion | null>(null);
  const [paso, setPaso] = useState<Paso>("investigando");
  const [logoIdx, setLogoIdx] = useState(0);

  // Campos editables
  const [empresa, setEmpresa] = useState("");
  const [rut, setRut] = useState("");
  const [direccion, setDireccion] = useState("");
  const [cats, setCats] = useState<Set<string>>(new Set());

  const investigar = useCallback(async (correo: string) => {
    try {
      const res = await fetch(`${API_URL}/api/onboarding/investigar-empresa`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: correo }),
      });
      const d: Investigacion = res.ok ? await res.json() : {};
      setInv(d);
      setEmpresa(d.empresa ?? correo.split("@")[1]?.split(".")[0] ?? "");
      setRut(d.rut ?? "");
      setDireccion(d.direccion ?? "");
      setCats(new Set(d.categorias_compra_probables ?? []));
    } catch {
      setInv({ empresa: null });
    }
    setPaso("empresa");
  }, []);

  useEffect(() => {
    createClient().auth.getUser().then(({ data }) => {
      const correo = data.user?.email ?? "";
      // Si ya hizo onboarding, al dashboard
      if (data.user?.user_metadata?.onboarding_completo) { router.replace("/dashboard"); return; }
      setEmail(correo);
      if (correo) investigar(correo); else router.replace("/login");
    });
  }, [investigar, router]);

  const toggleCat = (k: string) => setCats(prev => {
    const n = new Set(prev); n.has(k) ? n.delete(k) : n.add(k); return n;
  });

  const finalizar = async () => {
    setPaso("guardando");
    const supabase = createClient();
    await supabase.auth.updateUser({
      data: {
        onboarding_completo: true,
        empresa: empresa.trim(),
        industria: inv?.industria ?? null,
        rut: rut.trim() || null,
        direccion: direccion.trim() || null,
        logo_url: inv?.logo_candidatos?.[logoIdx] ?? null,
        sitio_web: inv?.sitio_web ?? null,
        pais: inv?.pais ?? inv?.pais_tld ?? null,
        categorias_default: Array.from(cats),
      },
    });
    router.replace("/dashboard");
  };

  const logo = inv?.logo_candidatos?.[logoIdx];
  const dominio = email.split("@")[1] ?? "";

  return (
    <div style={{ minHeight: "100vh", background: "var(--bg-base)", display: "flex", alignItems: "center", justifyContent: "center", padding: 20 }}>
      <div style={{ width: "100%", maxWidth: 460 }}>
        <div className="section-rule" style={{ marginBottom: 20 }} />

        {/* Paso investigando */}
        {paso === "investigando" && (
          <div style={{ textAlign: "center", padding: "40px 0" }}>
            <div style={{ display: "flex", gap: 6, justifyContent: "center", marginBottom: 20 }}>
              {[0, 1, 2].map(i => <div key={i} style={{ width: 8, height: 8, background: "var(--accent)", opacity: 0.3 + i * 0.35, animation: "pulse 1s infinite" }} />)}
            </div>
            <div style={{ fontSize: 15, fontWeight: 700, color: "var(--text-primary)", marginBottom: 6 }}>
              Investigando <strong>{dominio}</strong>…
            </div>
            <div style={{ fontSize: 12, color: "var(--text-muted)" }}>
              Buscando tu empresa para configurar tu cuenta con contexto real.
            </div>
          </div>
        )}

        {/* Paso confirmar empresa */}
        {paso === "empresa" && (
          <div>
            <div className="label" style={{ color: "var(--text-muted)", marginBottom: 8 }}>PASO 1 DE 3 · TU EMPRESA</div>
            {inv?.empresa && !inv?.generico ? (
              <>
                <h1 style={{ fontSize: 22, fontWeight: 700, margin: "0 0 4px", letterSpacing: "-0.02em" }}>¿Eres tú?</h1>
                <p style={{ fontSize: 12, color: "var(--text-secondary)", marginBottom: 18 }}>
                  Encontré esto a partir de <strong>{dominio}</strong>. Confírmalo o corrígelo.
                </p>
                <div style={{ border: "1px solid var(--border-default)", background: "var(--bg-surface)", padding: 18, display: "flex", gap: 14, alignItems: "flex-start", marginBottom: 16 }}>
                  {logo && (
                    <img src={logo} alt="logo" width={56} height={56}
                      onError={() => { if (inv?.logo_candidatos && logoIdx < inv.logo_candidatos.length - 1) setLogoIdx(logoIdx + 1); }}
                      style={{ objectFit: "contain", border: "1px solid var(--border-subtle)", background: "#fff", flexShrink: 0 }} />
                  )}
                  <div style={{ minWidth: 0 }}>
                    <div style={{ fontSize: 16, fontWeight: 800, color: "var(--text-primary)" }}>{inv.empresa}</div>
                    <div className="label" style={{ color: "var(--accent)", margin: "2px 0 6px" }}>
                      {inv.industria}{inv.pais ? ` · ${inv.pais}` : ""}
                    </div>
                    {inv.descripcion && <div style={{ fontSize: 11, color: "var(--text-secondary)", lineHeight: 1.5 }}>{inv.descripcion}</div>}
                    {inv.presencia && <div className="label" style={{ color: "var(--text-muted)", marginTop: 6 }}>Presencia: {inv.presencia}</div>}
                  </div>
                </div>
              </>
            ) : (
              <>
                <h1 style={{ fontSize: 22, fontWeight: 700, margin: "0 0 4px" }}>Cuéntame de tu empresa</h1>
                <p style={{ fontSize: 12, color: "var(--text-secondary)", marginBottom: 18 }}>
                  Tu correo es genérico, así que no pude detectarla sola. Escribe el nombre.
                </p>
              </>
            )}

            <label className="label" style={{ color: "var(--text-muted)", display: "block", marginBottom: 4 }}>Nombre de la empresa</label>
            <input value={empresa} onChange={e => setEmpresa(e.target.value)}
              style={inputSt} placeholder="Ej: Constructora Andes SpA" />

            <div style={{ display: "flex", gap: 8, marginTop: 20 }}>
              <button onClick={() => setPaso("datos")} disabled={!empresa.trim()}
                className="btn-swiss-primary" style={{ flex: 1 }}>
                Sí, continuar →
              </button>
            </div>
          </div>
        )}

        {/* Paso datos: RUT + dirección */}
        {paso === "datos" && (
          <div>
            <div className="label" style={{ color: "var(--text-muted)", marginBottom: 8 }}>PASO 2 DE 3 · DATOS DE FACTURACIÓN</div>
            <h1 style={{ fontSize: 22, fontWeight: 700, margin: "0 0 4px" }}>Confirma RUT y dirección</h1>
            <p style={{ fontSize: 12, color: "var(--text-secondary)", marginBottom: 18 }}>
              {rut || direccion ? "Los busqué automáticamente — revísalos por si acaso." : "No los encontré automáticamente. Complétalos (opcional)."}
            </p>

            <label className="label" style={{ color: "var(--text-muted)", display: "block", marginBottom: 4 }}>RUT de la empresa</label>
            <input value={rut} onChange={e => setRut(e.target.value)} style={{ ...inputSt, marginBottom: 14 }} placeholder="99.999.999-9" />

            <label className="label" style={{ color: "var(--text-muted)", display: "block", marginBottom: 4 }}>Dirección</label>
            <input value={direccion} onChange={e => setDireccion(e.target.value)} style={inputSt} placeholder="Av. Ejemplo 123, Santiago" />

            <div style={{ display: "flex", gap: 8, marginTop: 20 }}>
              <button onClick={() => setPaso("empresa")} className="btn-swiss-secondary">Atrás</button>
              <button onClick={() => setPaso("categorias")} className="btn-swiss-primary" style={{ flex: 1 }}>Continuar →</button>
            </div>
          </div>
        )}

        {/* Paso categorías */}
        {paso === "categorias" && (
          <div>
            <div className="label" style={{ color: "var(--text-muted)", marginBottom: 8 }}>PASO 3 DE 3 · QUÉ SUELES COMPRAR</div>
            <h1 style={{ fontSize: 22, fontWeight: 700, margin: "0 0 4px" }}>Orientemos tus búsquedas</h1>
            <p style={{ fontSize: 12, color: "var(--text-secondary)", marginBottom: 18 }}>
              Según tu industria ({inv?.industria ?? "—"}) sugerí estas categorías. Ajústalas: tus búsquedas partirán orientadas a ellas.
            </p>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 8 }}>
              {CATEGORIAS.map(c => {
                const on = cats.has(c.key);
                return (
                  <button key={c.key} onClick={() => toggleCat(c.key)} className="label"
                    style={{
                      color: on ? "var(--text-inverse)" : "var(--text-secondary)",
                      background: on ? "var(--bg-inverse)" : "var(--bg-base)",
                      border: `1px solid ${on ? "var(--border-strong)" : "var(--border-default)"}`,
                      padding: "6px 12px", cursor: "pointer", fontFamily: "var(--font-mono)",
                    }}>
                    {on ? "✓ " : ""}{c.label}
                  </button>
                );
              })}
            </div>
            <div style={{ display: "flex", gap: 8, marginTop: 20 }}>
              <button onClick={() => setPaso("datos")} className="btn-swiss-secondary">Atrás</button>
              <button onClick={finalizar} className="btn-swiss-primary" style={{ flex: 1 }}>Finalizar y entrar →</button>
            </div>
          </div>
        )}

        {paso === "guardando" && (
          <div style={{ textAlign: "center", padding: "40px 0", fontSize: 13, color: "var(--text-muted)" }}>
            Configurando tu cuenta…
          </div>
        )}
      </div>
      <style>{`@keyframes pulse { 0%,100% { opacity: .3 } 50% { opacity: 1 } }`}</style>
    </div>
  );
}

const inputSt: React.CSSProperties = {
  width: "100%", boxSizing: "border-box", background: "var(--bg-surface)",
  border: "1px solid var(--border-default)", padding: "10px 12px", fontSize: 13,
  color: "var(--text-primary)", fontFamily: "var(--font-mono)", outline: "none",
};
