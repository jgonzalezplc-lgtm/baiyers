"use client";
import { useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export default function MCPAutorizarPage() {
  const searchParams = useSearchParams();
  const [status, setStatus] = useState<"loading" | "success" | "error">("loading");
  const [clientName, setClientName] = useState("");

  const CLIENT_NAMES: Record<string, string> = {
    "claude-desktop": "Claude Desktop",
    "claude-ai": "Claude.ai",
    "chatgpt": "ChatGPT",
    "gemini": "Google Gemini",
    "cursor": "Cursor IDE",
  };

  useEffect(() => {
    const clientId = searchParams.get("client_id") || "";
    const redirectUri = searchParams.get("redirect_uri") || "";
    const responseType = searchParams.get("response_type") || "";
    const scope = searchParams.get("scope") || "read";
    const state = searchParams.get("state") || "";
    const codeChallenge = searchParams.get("code_challenge") || "";

    setClientName(CLIENT_NAMES[clientId] || clientId);

    // Redirect to backend OAuth authorize endpoint
    if (clientId && redirectUri) {
      const params = new URLSearchParams({
        client_id: clientId,
        redirect_uri: redirectUri,
        response_type: responseType || "code",
        scope,
        state,
        code_challenge: codeChallenge,
        code_challenge_method: "S256",
      });
      window.location.href = `${API_URL}/api/mcp/oauth/authorize?${params.toString()}`;
    } else {
      setStatus("error");
    }
  }, [searchParams]);

  return (
    <div style={{ minHeight: "100vh", background: "#060610", display: "flex", alignItems: "center", justifyContent: "center", padding: 20 }}>
      <div style={{ background: "#0a0a18", border: "1px solid #1a1a2e", borderRadius: 12, padding: 40, maxWidth: 400, width: "100%", textAlign: "center" }}>
        <div style={{ fontSize: 22, fontWeight: 800, color: "#6366f1", marginBottom: 4 }}>Claria</div>
        <div style={{ fontSize: 11, color: "#475569", textTransform: "uppercase", letterSpacing: "0.1em", marginBottom: 32 }}>Cotizador Inteligente</div>

        {status === "loading" && (
          <>
            <div style={{ width: 40, height: 40, border: "3px solid #1a1a2e", borderTop: "3px solid #6366f1", borderRadius: "50%", margin: "0 auto 16px", animation: "spin 1s linear infinite" }} />
            <div style={{ fontSize: 13, color: "#94a3b8" }}>Redirigiendo a la pagina de autorizacion...</div>
            {clientName && <div style={{ fontSize: 11, color: "#475569", marginTop: 8 }}>Solicitud de: {clientName}</div>}
          </>
        )}

        {status === "error" && (
          <>
            <div style={{ fontSize: 32, marginBottom: 16 }}>⚠️</div>
            <div style={{ fontSize: 14, fontWeight: 700, color: "#f1f5f9", marginBottom: 8 }}>Parametros invalidos</div>
            <div style={{ fontSize: 12, color: "#475569", marginBottom: 20 }}>
              Faltan parametros requeridos para la autorizacion OAuth.
            </div>
            <a href="/integraciones" style={{ display: "inline-block", background: "#6366f1", color: "#fff", padding: "10px 24px", borderRadius: 6, fontSize: 12, fontWeight: 700, textDecoration: "none" }}>
              Ir a Integraciones
            </a>
          </>
        )}

        <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
      </div>
    </div>
  );
}
