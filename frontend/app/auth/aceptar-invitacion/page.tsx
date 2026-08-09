"use client";
/**
 * Aceptar invitación (Fase C del multi-usuario).
 *
 * Supabase envía el correo de invitación con los tokens en el FRAGMENTO de
 * la URL (`#access_token=...&refresh_token=...`), no en el query string
 * (`?code=`) — ese formato es el de OAuth/`/auth/callback`, no el de
 * `invite_user_by_email()`. El fragmento nunca llega al servidor y
 * `useSearchParams()` no lo lee, así que hay que parsearlo a mano y armar
 * la sesión con `setSession()`. Se mantiene el camino `?code=` como
 * respaldo por si algún día cambia el tipo de link. Luego pedimos a la
 * persona que setee su contraseña — su membresía ya fue creada por el
 * backend cuando el admin la invitó.
 */
import { Suspense, useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { createClient } from "@/lib/supabase/client";
import { BtnPrimary, Card, Input, Spinner } from "@/components/ui";

function AceptarInner() {
  const params = useSearchParams();
  const yaCorrio = useRef(false);

  const [fase, setFase] = useState<"cargando" | "password" | "guardando" | "listo" | "error">("cargando");
  const [nombreOrg, setNombreOrg] = useState<string>("");
  const [email, setEmail] = useState<string>("");
  const [password, setPassword] = useState("");
  const [password2, setPassword2] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    if (yaCorrio.current) return;
    yaCorrio.current = true;

    const code = params.get("code");
    const hash = new URLSearchParams(window.location.hash.replace(/^#/, ""));
    const accessToken = hash.get("access_token");
    const refreshToken = hash.get("refresh_token");
    const supabase = createClient();

    (async () => {
      if (accessToken && refreshToken) {
        const { error } = await supabase.auth.setSession({ access_token: accessToken, refresh_token: refreshToken });
        if (error) { setFase("error"); setError("El enlace de invitación expiró o ya fue usado."); return; }
      } else if (code) {
        const { error } = await supabase.auth.exchangeCodeForSession(code);
        if (error) {
          // Puede ser que el link ya se haya consumido; probamos la sesión igual.
          const { data } = await supabase.auth.getSession();
          if (!data.session) { setFase("error"); setError("El enlace de invitación expiró o ya fue usado."); return; }
        }
      }

      const { data } = await supabase.auth.getUser();
      if (!data.user) { setFase("error"); setError("No pudimos leer tu sesión. Volvé a abrir el enlace del correo."); return; }
      setEmail(data.user.email ?? "");
      const meta = (data.user.user_metadata ?? {}) as Record<string, unknown>;
      setNombreOrg(typeof meta.organizacion_nombre === "string" ? meta.organizacion_nombre : "");
      setFase("password");
    })();
  }, [params]);

  const guardar = async () => {
    if (password.length < 8) { setError("La contraseña debe tener al menos 8 caracteres."); return; }
    if (password !== password2) { setError("Las contraseñas no coinciden."); return; }
    setFase("guardando"); setError("");
    const supabase = createClient();
    const { error: e } = await supabase.auth.updateUser({ password });
    if (e) { setFase("password"); setError(e.message); return; }
    setFase("listo");
    setTimeout(() => { window.location.replace("/dashboard"); }, 900);
  };

  if (fase === "cargando") return (
    <div style={{ minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center", padding: 20 }}>
      <Spinner label="Validando tu invitación…" />
    </div>
  );

  if (fase === "error") return (
    <div style={{ minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center", padding: 20 }}>
      <Card padding={28} style={{ maxWidth: 420, width: "100%" }}>
        <h1 style={{ fontSize: 20, fontWeight: 600, color: "var(--n-900)", margin: "0 0 8px" }}>No pudimos validar la invitación</h1>
        <p style={{ fontSize: 13.5, color: "var(--n-600)", margin: 0 }}>{error || "Pide al admin de tu empresa que te reenvíe la invitación."}</p>
      </Card>
    </div>
  );

  return (
    <div style={{ minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center", padding: 20 }}>
      <Card padding={28} style={{ maxWidth: 420, width: "100%" }}>
        <h1 style={{ fontSize: 22, fontWeight: 600, color: "var(--n-900)", margin: "0 0 6px" }}>
          Bienvenido{nombreOrg ? ` a ${nombreOrg}` : ""}
        </h1>
        <p style={{ fontSize: 13.5, color: "var(--n-600)", margin: "0 0 20px" }}>
          Elige una contraseña para tu cuenta en Baiyer{email ? ` — entrarás como ${email}` : ""}.
        </p>
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <Input label="Contraseña" type="password" value={password} onChange={e => setPassword(e.target.value)} placeholder="Al menos 8 caracteres" />
          <Input label="Repetir contraseña" type="password" value={password2} onChange={e => setPassword2(e.target.value)} />
          {error && <div style={{ fontSize: 13, color: "var(--danger)" }}>{error}</div>}
          <BtnPrimary onClick={guardar} disabled={fase === "guardando" || !password || !password2} style={{ width: "100%" }}>
            {fase === "guardando" ? "Guardando…" : fase === "listo" ? "Entrando…" : "Entrar a Baiyer"}
          </BtnPrimary>
        </div>
      </Card>
    </div>
  );
}

export default function AceptarInvitacionPage() {
  return (
    <Suspense fallback={<div style={{ minHeight: "100vh" }} />}>
      <AceptarInner />
    </Suspense>
  );
}
