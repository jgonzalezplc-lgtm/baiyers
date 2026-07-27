"use client";
/**
 * Error boundary global: si algo crashea (SSR o cliente) se ve este mensaje
 * en vez de pantalla en negro. Sin esto, un crash silencioso no muestra nada
 * y el usuario cree que la app está caída.
 */
import { useEffect } from "react";

export default function GlobalError({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  useEffect(() => { console.error("[GlobalError]", error); }, [error]);

  return (
    <div style={{
      minHeight: "100vh", background: "#faf9f6", color: "#211d18",
      display: "flex", alignItems: "center", justifyContent: "center", padding: 24,
      fontFamily: "system-ui, -apple-system, sans-serif",
    }}>
      <div style={{ maxWidth: 480, textAlign: "center" }}>
        <div style={{
          width: 48, height: 48, borderRadius: 12, background: "#f6e6df", color: "#9a3f28",
          display: "inline-flex", alignItems: "center", justifyContent: "center",
          fontSize: 26, marginBottom: 16,
        }}>!</div>
        <h1 style={{ fontSize: 22, fontWeight: 600, margin: "0 0 8px", letterSpacing: "-0.015em" }}>
          Algo salió mal
        </h1>
        <p style={{ fontSize: 14, color: "#635d52", margin: "0 0 20px", lineHeight: 1.6 }}>
          La aplicación tuvo un problema al cargar esta pantalla. Prueba recargar; si sigue
          fallando, cierra sesión y vuelve a entrar.
        </p>
        <details style={{ background: "#f1efea", padding: 12, borderRadius: 10, textAlign: "left", marginBottom: 20, fontSize: 12.5, color: "#635d52" }}>
          <summary style={{ cursor: "pointer", fontWeight: 500 }}>Detalles técnicos</summary>
          <pre style={{ whiteSpace: "pre-wrap", wordBreak: "break-word", marginTop: 8, fontSize: 11.5 }}>
            {error.message}
            {error.digest ? `\n(digest: ${error.digest})` : ""}
          </pre>
        </details>
        <div style={{ display: "flex", gap: 8, justifyContent: "center" }}>
          <button
            onClick={reset}
            style={{
              background: "#136b76", color: "#fff", border: "none",
              padding: "10px 18px", borderRadius: 10, fontSize: 14, fontWeight: 600,
              cursor: "pointer", fontFamily: "inherit",
            }}
          >
            Reintentar
          </button>
          <a
            href="/login"
            style={{
              background: "#fff", color: "#45403a", border: "1px solid #d8d4cb",
              padding: "10px 18px", borderRadius: 10, fontSize: 14, fontWeight: 600,
              textDecoration: "none", fontFamily: "inherit",
            }}
          >
            Ir al login
          </a>
        </div>
      </div>
    </div>
  );
}
