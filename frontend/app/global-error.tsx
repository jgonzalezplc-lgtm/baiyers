"use client";
/**
 * Último resorte: si el root layout mismo crashea, error.tsx no se muestra;
 * Next dispara global-error.tsx. Debe traer su propio <html> y <body>.
 */
import { useEffect } from "react";

export default function GlobalRootError({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  useEffect(() => { console.error("[GlobalRootError]", error); }, [error]);

  return (
    <html lang="es">
      <body style={{
        margin: 0, minHeight: "100vh", background: "#faf9f6", color: "#211d18",
        display: "flex", alignItems: "center", justifyContent: "center", padding: 24,
        fontFamily: "system-ui, -apple-system, sans-serif",
      }}>
        <div style={{ maxWidth: 480, textAlign: "center" }}>
          <div style={{
            width: 48, height: 48, borderRadius: 12, background: "#f6e6df", color: "#9a3f28",
            display: "inline-flex", alignItems: "center", justifyContent: "center",
            fontSize: 26, marginBottom: 16,
          }}>!</div>
          <h1 style={{ fontSize: 22, fontWeight: 600, margin: "0 0 8px" }}>La app tuvo un problema</h1>
          <p style={{ fontSize: 14, color: "#635d52", margin: "0 0 20px", lineHeight: 1.6 }}>
            Recarga la página; si sigue ocurriendo, borra las cookies del sitio y vuelve a entrar.
          </p>
          <pre style={{
            background: "#f1efea", padding: 12, borderRadius: 10, textAlign: "left",
            fontSize: 11.5, color: "#635d52", overflow: "auto", marginBottom: 16,
          }}>{error.message}{error.digest ? `\n(digest: ${error.digest})` : ""}</pre>
          <button
            onClick={reset}
            style={{
              background: "#136b76", color: "#fff", border: "none",
              padding: "10px 18px", borderRadius: 10, fontSize: 14, fontWeight: 600, cursor: "pointer",
            }}
          >
            Reintentar
          </button>
        </div>
      </body>
    </html>
  );
}
