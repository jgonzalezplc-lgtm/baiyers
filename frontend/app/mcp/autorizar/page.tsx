"use client";

import { Suspense, useEffect, useRef, useState, type CSSProperties, type FormEvent } from "react";
import { useSearchParams } from "next/navigation";
import { createClient } from "@/lib/supabase/client";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface AuthorizationPreview {
  client_name: string;
  scopes: string[];
}

interface CuentaActiva {
  email: string;
  accessToken: string;
}

function GoogleIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 48 48" aria-hidden="true">
      <path fill="#4285F4" d="M45.12 24.5c0-1.56-.14-3.06-.4-4.5H24v8.51h11.84a10.13 10.13 0 0 1-4.4 6.65v5.52h7.11c4.16-3.83 6.57-9.47 6.57-16.18z" />
      <path fill="#34A853" d="M24 46c5.94 0 10.92-1.97 14.56-5.33l-7.11-5.52c-1.97 1.32-4.49 2.1-7.45 2.1-5.73 0-10.58-3.87-12.31-9.07H4.34v5.7A21.99 21.99 0 0 0 24 46z" />
      <path fill="#FBBC05" d="M11.69 28.18a13.2 13.2 0 0 1 0-8.36v-5.7H4.34a22 22 0 0 0 0 19.76z" />
      <path fill="#EA4335" d="M24 10.75c3.23 0 6.13 1.11 8.41 3.29l6.31-6.31C34.91 4.18 29.93 2 24 2 15.4 2 7.96 6.94 4.34 14.12l7.35 5.7c1.73-5.2 6.58-9.07 12.31-9.07z" />
    </svg>
  );
}

function MicrosoftIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true">
      <path fill="#f25022" d="M1 1h6.5v6.5H1z" />
      <path fill="#7fba00" d="M8.5 1H15v6.5H8.5z" />
      <path fill="#00a4ef" d="M1 8.5h6.5V15H1z" />
      <path fill="#ffb900" d="M8.5 8.5H15V15H8.5z" />
    </svg>
  );
}

function describirPermisos(scopes: string[]): string[] {
  const descripciones: string[] = [];
  if (scopes.some(scope => scope.endsWith(":read") || scope === "data:read")) {
    descripciones.push("Consultar datos de compras de tu organización.");
  }
  if (scopes.some(scope => scope.endsWith(":write"))) {
    descripciones.push("Crear o actualizar listas, cotizaciones y documentos cuando lo pidas.");
  }
  if (scopes.some(scope => scope.endsWith(":send") || scope === "mail:sync")) {
    descripciones.push("Sincronizar o enviar comunicaciones sólo con tu confirmación.");
  }
  if (scopes.some(scope => scope.startsWith("approvals:") && scope !== "approvals:read")) {
    descripciones.push("Solicitar o registrar decisiones de aprobación asignadas a tu cuenta.");
  }
  if (scopes.some(scope => ["suppliers:block", "suppliers:merge", "invoices:pay"].includes(scope))) {
    descripciones.push("Ejecutar acciones sensibles únicamente después de una confirmación explícita.");
  }
  return descripciones.length ? descripciones : ["Usar los permisos MCP indicados en esta solicitud."];
}

async function enviarConsentimiento(requestId: string, action: "allow" | "deny", accessToken?: string) {
  const response = await fetch(`${API_URL}/api/mcp/oauth/consent/session`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
    },
    body: JSON.stringify({ request_id: requestId, action }),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok || !data.redirect_url) {
    throw new Error(typeof data.detail === "string" ? data.detail : "No pudimos completar la autorización.");
  }
  window.location.replace(data.redirect_url);
}

export default function MCPAutorizarPage() {
  return (
    <Suspense fallback={<PantallaCargando />}>
      <MCPAutorizarContent />
    </Suspense>
  );
}

function MCPAutorizarContent() {
  const params = useSearchParams();
  const requestId = params.get("request") || "";
  const [preview, setPreview] = useState<AuthorizationPreview | null>(null);
  const [cuenta, setCuenta] = useState<CuentaActiva | null>(null);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [cargando, setCargando] = useState(true);
  const [enviando, setEnviando] = useState(false);
  const [error, setError] = useState("");
  const autoContinuado = useRef(false);
  const supabase = createClient();

  useEffect(() => {
    let vigente = true;
    if (!requestId) {
      setError("La solicitud no contiene un identificador válido.");
      setCargando(false);
      return;
    }

    Promise.all([
      fetch(`${API_URL}/api/mcp/oauth/request/${encodeURIComponent(requestId)}`).then(async response => {
        if (!response.ok) throw new Error("Esta solicitud expiró o ya fue utilizada.");
        return response.json() as Promise<AuthorizationPreview>;
      }),
      supabase.auth.getSession(),
    ]).then(([solicitud, sessionResult]) => {
      if (!vigente) return;
      setPreview(solicitud);
      const session = sessionResult.data.session;
      if (session) {
        setCuenta({
          email: session.user.email || "Cuenta Baiyer",
          accessToken: session.access_token,
        });
      }
      if (params.get("oauth_error")) {
        setError("No se pudo iniciar sesión con ese proveedor. Puedes intentarlo de nuevo o usar tu correo.");
      }
      setCargando(false);
    }).catch(err => {
      if (!vigente) return;
      setError(err instanceof Error ? err.message : "No pudimos cargar la solicitud.");
      setCargando(false);
    });

    return () => { vigente = false; };
  }, [requestId]); // eslint-disable-line react-hooks/exhaustive-deps

  // Después de volver desde Google o Microsoft, la sesión ya está verificada.
  // Completa la autorización sin exigir un segundo clic.
  useEffect(() => {
    if (!cuenta || !preview || cargando || autoContinuado.current) return;
    if (sessionStorage.getItem("baiyer_mcp_auto_authorize") !== requestId) return;
    autoContinuado.current = true;
    sessionStorage.removeItem("baiyer_mcp_auto_authorize");
    setEnviando(true);
    enviarConsentimiento(requestId, "allow", cuenta.accessToken).catch(err => {
      setError(err instanceof Error ? err.message : "No pudimos completar la autorización.");
      setEnviando(false);
    });
  }, [cuenta, preview, cargando, requestId]);

  const continuarConProveedor = async (provider: "google" | "azure") => {
    setError("");
    setEnviando(true);
    sessionStorage.setItem("baiyer_mcp_auto_authorize", requestId);
    const next = `/mcp/autorizar?request=${encodeURIComponent(requestId)}`;
    const { error: oauthError } = await supabase.auth.signInWithOAuth({
      provider,
      options: {
        ...(provider === "azure" ? { scopes: "openid profile email" } : {}),
        redirectTo: `${window.location.origin}/auth/callback?next=${encodeURIComponent(next)}`,
      },
    });
    if (oauthError) {
      sessionStorage.removeItem("baiyer_mcp_auto_authorize");
      setError(`No se pudo iniciar con ${provider === "google" ? "Google" : "Microsoft"}: ${oauthError.message}`);
      setEnviando(false);
    }
  };

  const continuarConPassword = async (event: FormEvent) => {
    event.preventDefault();
    setError("");
    setEnviando(true);
    const { data, error: loginError } = await supabase.auth.signInWithPassword({ email, password });
    if (loginError || !data.session) {
      setError("El correo o la contraseña no son correctos.");
      setEnviando(false);
      return;
    }
    setCuenta({ email: data.user.email || email, accessToken: data.session.access_token });
    try {
      await enviarConsentimiento(requestId, "allow", data.session.access_token);
    } catch (err) {
      setError(err instanceof Error ? err.message : "No pudimos completar la autorización.");
      setEnviando(false);
    }
  };

  const autorizarCuentaActiva = async () => {
    if (!cuenta) return;
    setError("");
    setEnviando(true);
    try {
      await enviarConsentimiento(requestId, "allow", cuenta.accessToken);
    } catch (err) {
      setError(err instanceof Error ? err.message : "No pudimos completar la autorización.");
      setEnviando(false);
    }
  };

  const usarOtraCuenta = async () => {
    await supabase.auth.signOut({ scope: "local" });
    setCuenta(null);
    setError("");
  };

  const cancelar = async () => {
    setEnviando(true);
    setError("");
    try {
      await enviarConsentimiento(requestId, "deny");
    } catch (err) {
      setError(err instanceof Error ? err.message : "No pudimos cancelar la solicitud.");
      setEnviando(false);
    }
  };

  if (cargando) return <PantallaCargando />;

  return (
    <main style={{ minHeight: "100vh", background: "var(--bg-base)", display: "grid", placeItems: "center", padding: 20 }}>
      <section style={{ width: "100%", maxWidth: 460, background: "var(--bg-surface)", border: "1px solid var(--border-default)" }}>
        <header style={{ padding: "24px 26px 20px", borderBottom: "1px solid var(--border-default)" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 9, marginBottom: 22 }}>
            <span style={{ width: 28, height: 28, display: "grid", placeItems: "center", background: "var(--accent)", color: "white", fontSize: 14, fontWeight: 800 }}>B</span>
            <span style={{ fontSize: 15, fontWeight: 700, color: "var(--text-primary)" }}>Baiyer</span>
          </div>
          <span className="label" style={{ color: "var(--accent)", display: "block", marginBottom: 6 }}>CONEXIÓN MCP SEGURA</span>
          <h1 style={{ fontSize: 21, lineHeight: 1.25, color: "var(--text-primary)", margin: "0 0 8px", letterSpacing: "-0.02em" }}>
            Conectar {preview?.client_name || "tu asistente"} con Baiyer
          </h1>
          <p style={{ fontSize: 12, lineHeight: 1.6, color: "var(--text-secondary)", margin: 0 }}>
            Usa la misma forma con la que creaste tu cuenta. No necesitas generar ni copiar tokens.
          </p>
        </header>

        <div style={{ padding: "22px 26px 26px" }}>
          {preview && (
            <div style={{ background: "var(--bg-base)", border: "1px solid var(--border-default)", padding: "13px 14px", marginBottom: 18 }}>
              <div className="label" style={{ color: "var(--text-muted)", marginBottom: 8 }}>ESTA CONEXIÓN PODRÁ</div>
              <ul style={{ margin: 0, paddingLeft: 18, fontSize: 11, lineHeight: 1.65, color: "var(--text-secondary)" }}>
                {describirPermisos(preview.scopes).map(item => <li key={item}>{item}</li>)}
              </ul>
              <details style={{ marginTop: 9, fontSize: 10, color: "var(--text-muted)" }}>
                <summary style={{ cursor: "pointer" }}>Ver permisos técnicos</summary>
                <div style={{ marginTop: 6, fontFamily: "var(--font-mono)", wordBreak: "break-word" }}>{preview.scopes.join(" · ")}</div>
              </details>
            </div>
          )}

          {error && (
            <div role="alert" style={{ background: "var(--fill-error)", border: "1px solid var(--border-accent)", padding: "10px 12px", fontSize: 11, lineHeight: 1.5, color: "var(--text-error)", marginBottom: 16 }}>
              {error}
            </div>
          )}

          {!preview ? (
            <a href="/" className="btn-swiss-secondary" style={{ width: "100%", justifyContent: "center", textDecoration: "none" }}>
              Volver a Baiyer
            </a>
          ) : cuenta ? (
            <div>
              <div style={{ border: "1px solid var(--border-default)", padding: "12px 14px", marginBottom: 12, display: "flex", justifyContent: "space-between", gap: 12, alignItems: "center" }}>
                <div>
                  <div className="label" style={{ color: "var(--text-muted)", marginBottom: 4 }}>CUENTA BAIYER</div>
                  <div style={{ fontSize: 12, fontWeight: 700, color: "var(--text-primary)", overflowWrap: "anywhere" }}>{cuenta.email}</div>
                </div>
                <span style={{ fontSize: 9, color: "var(--text-success)", border: "1px solid var(--text-success)", padding: "3px 6px", whiteSpace: "nowrap" }}>SESIÓN ACTIVA</span>
              </div>
              <button className="btn-swiss-primary" style={{ width: "100%", justifyContent: "center", marginBottom: 8 }} onClick={autorizarCuentaActiva} disabled={enviando}>
                {enviando ? "Conectando…" : `Autorizar conexión con ${cuenta.email}`}
              </button>
              <button className="btn-swiss-secondary" style={{ width: "100%", justifyContent: "center" }} onClick={usarOtraCuenta} disabled={enviando}>
                Usar otra cuenta
              </button>
            </div>
          ) : (
            <div>
              <button className="btn-swiss-secondary" style={{ width: "100%", justifyContent: "center", gap: 8, marginBottom: 8 }} onClick={() => continuarConProveedor("google")} disabled={enviando}>
                <GoogleIcon /> Continuar y autorizar con Google
              </button>
              <button className="btn-swiss-secondary" style={{ width: "100%", justifyContent: "center", gap: 8 }} onClick={() => continuarConProveedor("azure")} disabled={enviando}>
                <MicrosoftIcon /> Continuar y autorizar con Outlook / Microsoft
              </button>

              <div style={{ display: "flex", alignItems: "center", gap: 10, margin: "18px 0" }}>
                <div style={{ height: 1, flex: 1, background: "var(--border-default)" }} />
                <span className="label" style={{ color: "var(--text-muted)" }}>O CON CORREO Y CONTRASEÑA</span>
                <div style={{ height: 1, flex: 1, background: "var(--border-default)" }} />
              </div>

              <form onSubmit={continuarConPassword} style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                <label style={{ fontSize: 11, color: "var(--text-secondary)" }}>
                  Correo
                  <input type="email" autoComplete="email" required value={email} onChange={event => setEmail(event.target.value)} placeholder="tu@empresa.cl" style={inputStyle} />
                </label>
                <label style={{ fontSize: 11, color: "var(--text-secondary)" }}>
                  Contraseña
                  <input type="password" autoComplete="current-password" required value={password} onChange={event => setPassword(event.target.value)} placeholder="••••••••" style={inputStyle} />
                </label>
                <button type="submit" className="btn-swiss-primary" style={{ width: "100%", justifyContent: "center", marginTop: 2 }} disabled={enviando}>
                  {enviando ? "Conectando…" : "Ingresar y autorizar"}
                </button>
              </form>
            </div>
          )}

          {preview && (
            <button onClick={cancelar} disabled={enviando || !requestId} style={{ width: "100%", marginTop: 10, padding: 8, border: 0, background: "transparent", color: "var(--text-muted)", fontFamily: "inherit", fontSize: 10, cursor: "pointer" }}>
              Cancelar conexión
            </button>
          )}
          <p style={{ margin: "10px 0 0", fontSize: 9, lineHeight: 1.55, color: "var(--text-muted)", textAlign: "center" }}>
            Puedes revocar este acceso cuando quieras desde Baiyer → MCP → Conexiones.
          </p>
        </div>
      </section>
    </main>
  );
}

function PantallaCargando() {
  return (
    <div style={{ minHeight: "100vh", background: "var(--bg-base)", display: "grid", placeItems: "center" }}>
      <div style={{ fontSize: 11, color: "var(--text-muted)", letterSpacing: "0.06em" }}>PREPARANDO CONEXIÓN SEGURA…</div>
    </div>
  );
}

const inputStyle: CSSProperties = {
  display: "block",
  width: "100%",
  height: 40,
  marginTop: 5,
  padding: "0 11px",
  background: "var(--bg-surface)",
  color: "var(--text-primary)",
  border: "1px solid var(--border-default)",
  borderRadius: 0,
  fontFamily: "inherit",
  fontSize: 12,
  outline: "none",
};
