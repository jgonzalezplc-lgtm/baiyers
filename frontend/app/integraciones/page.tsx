"use client";
import { useState, useEffect } from "react";
import { createClient } from "@/lib/supabase/client";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface MCPConnection {
  id: string;
  client_id: string;
  scopes: string[];
  connected_at: string;
  last_used_at?: string;
}

interface AuditEntry {
  id: string;
  tool_name: string;
  params: Record<string, unknown>;
  result_preview: string;
  called_at: string;
}

const KNOWN_CLIENTS: Record<string, { name: string; description: string }> = {
  "claude-desktop": { name: "Claude Desktop", description: "Anthropic Claude para escritorio" },
  "claude-ai": { name: "Claude.ai", description: "Claude en el navegador" },
  "chatgpt": { name: "ChatGPT Plugin", description: "OpenAI ChatGPT via plugin" },
  "gemini": { name: "Google Gemini", description: "Google Gemini AI" },
  "cursor": { name: "Cursor IDE", description: "Editor de código con IA" },
};

const TOOL_LABELS: Record<string, string> = {
  cotizar_item: "Cotizar Item",
  buscar_proveedores: "Buscar Proveedores",
  emitir_oc: "Emitir OC",
  consultar_gastos: "Consultar Gastos",
  crear_recurrencia: "Crear Recurrencia",
  historico_precios: "Historial Precios",
  crear_proyecto: "Crear Proyecto",
  generar_reporte: "Generar Reporte",
};

export default function IntegracionesPage() {
  const [userId, setUserId] = useState("");
  const [mcpToken, setMcpToken] = useState("");
  const [connections, setConnections] = useState<MCPConnection[]>([]);
  const [auditLog, setAuditLog] = useState<AuditEntry[]>([]);
  const [tab, setTab] = useState<"conexiones" | "audit" | "docs">("conexiones");
  const [revoking, setRevoking] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    createClient().auth.getUser().then(({ data: { user } }) => {
      if (user) setUserId(user.id);
    });
  }, []);

  useEffect(() => {
    if (!mcpToken) return;
    Promise.all([
      fetch(`${API_URL}/api/mcp/connections`, { headers: { Authorization: `Bearer ${mcpToken}` } }).then(r => r.json()),
      fetch(`${API_URL}/api/mcp/audit?limit=20`, { headers: { Authorization: `Bearer ${mcpToken}` } }).then(r => r.json()),
    ]).then(([conn, audit]) => {
      setConnections(conn.connections || []);
      setAuditLog(audit.logs || []);
    }).catch(() => {});
  }, [mcpToken]);

  const handleRevoke = async (clientId: string) => {
    if (!mcpToken) return;
    setRevoking(clientId);
    try {
      await fetch(`${API_URL}/api/mcp/oauth/revoke?client_id=${encodeURIComponent(clientId)}`, {
        method: "DELETE", headers: { Authorization: `Bearer ${mcpToken}` },
      });
      setConnections(prev => prev.filter(c => c.client_id !== clientId));
    } finally { setRevoking(null); }
  };

  const copyConfig = () => {
    navigator.clipboard.writeText(JSON.stringify({
      mcpServers: { "claria-cotizador": { command: "npx", args: ["-y", "@claria/mcp-server"], env: { CLARIA_TOKEN: mcpToken || "<tu-token-aqui>", CLARIA_USER_ID: userId } } }
    }, null, 2));
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const tabBtn = (active: boolean): React.CSSProperties => ({
    padding: "8px 16px", fontSize: 11, fontWeight: active ? 700 : 400,
    color: active ? "var(--accent)" : "var(--text-muted)", background: "none", border: "none",
    borderBottom: active ? "2px solid var(--accent)" : "2px solid transparent",
    cursor: "pointer", fontFamily: "var(--font-mono)", letterSpacing: "0.04em",
  });

  const inputSt: React.CSSProperties = {
    background: "var(--bg-base)", border: "1px solid var(--border-default)",
    padding: "8px 12px", color: "var(--text-primary)", fontSize: 11,
    fontFamily: "var(--font-mono)", outline: "none", width: "100%",
  };

  return (
    <>
      <div style={{ marginBottom: 28 }}>
        <div className="section-rule" style={{ marginBottom: 16 }} />
        <span style={{ fontSize: 10, fontWeight: 700, color: "var(--text-muted)", letterSpacing: "0.06em", display: "block", marginBottom: 6 }}>
          INTEGRACIONES · MODEL CONTEXT PROTOCOL
        </span>
        <h1 style={{ fontSize: 26, fontWeight: 700, color: "var(--text-primary)", margin: "0 0 6px", letterSpacing: "-0.02em" }}>MCP</h1>
        <p style={{ fontSize: 12, color: "var(--text-secondary)", margin: 0 }}>Conecta Claude, ChatGPT y otros LLMs con tu cuenta Claria.</p>
      </div>

      {!mcpToken && (
        <div style={{ background: "var(--bg-surface)", border: "1px solid var(--border-default)", borderLeft: "3px solid var(--accent)", padding: "20px", marginBottom: 24 }}>
          <div style={{ fontSize: 12, fontWeight: 700, color: "var(--text-primary)", marginBottom: 6 }}>Conectar con tu cuenta</div>
          <p style={{ fontSize: 11, color: "var(--text-secondary)", marginBottom: 14 }}>Genera un token de acceso o pega uno existente.</p>
          <input type="text" placeholder="Pegar token MCP..." style={inputSt} onChange={e => setMcpToken(e.target.value)} />
        </div>
      )}

      <div style={{ borderBottom: "1px solid var(--border-default)", marginBottom: 24, display: "flex", gap: 4 }}>
        {(["conexiones", "audit", "docs"] as const).map(t => (
          <button key={t} style={tabBtn(tab === t)} onClick={() => setTab(t)}>
            {t === "conexiones" ? "CONEXIONES" : t === "audit" ? "ACTIVIDAD" : "CONFIGURACIÓN"}
          </button>
        ))}
      </div>

      {tab === "conexiones" && (
        <div>
          <div style={{ fontSize: 9, fontWeight: 700, color: "var(--text-muted)", letterSpacing: "0.06em", marginBottom: 14 }}>CLIENTES DISPONIBLES</div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(240px, 1fr))", gap: 1, border: "1px solid var(--border-default)", marginBottom: 28 }}>
            {Object.entries(KNOWN_CLIENTS).map(([id, client]) => {
              const connected = connections.find(c => c.client_id === id);
              return (
                <div key={id} style={{ background: "var(--bg-surface)", borderRight: "1px solid var(--border-default)", borderBottom: "1px solid var(--border-default)", padding: "16px" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 8 }}>
                    <div style={{ fontSize: 12, fontWeight: 700, color: "var(--text-primary)" }}>{client.name}</div>
                    {connected
                      ? <span style={{ fontSize: 9, fontWeight: 700, color: "var(--text-success)", border: "1px solid var(--text-success)", padding: "2px 7px" }}>CONECTADO</span>
                      : <span style={{ fontSize: 9, color: "var(--text-muted)", border: "1px solid var(--border-default)", padding: "2px 7px" }}>NO CONECTADO</span>
                    }
                  </div>
                  <div style={{ fontSize: 11, color: "var(--text-secondary)", marginBottom: 14 }}>{client.description}</div>
                  {connected ? (
                    <div style={{ display: "flex", gap: 8 }}>
                      <button onClick={copyConfig} className="btn-swiss-secondary" style={{ flex: 1, fontSize: 10, padding: "5px 10px" }}>
                        {copied ? "Copiado ✓" : "Copiar config"}
                      </button>
                      <button onClick={() => handleRevoke(id)} disabled={revoking === id} style={{ fontSize: 10, color: "var(--text-error)", background: "none", border: "1px solid var(--text-error)", padding: "5px 10px", cursor: "pointer", fontFamily: "inherit" }}>
                        {revoking === id ? "..." : "Revocar"}
                      </button>
                    </div>
                  ) : (
                    <a href={`${API_URL}/api/mcp/oauth/authorize?client_id=${id}&redirect_uri=${encodeURIComponent(typeof window !== "undefined" ? window.location.origin + "/integraciones" : "")}&response_type=code&scope=read+write&state=${id}`}
                      className="btn-swiss-primary" style={{ display: "block", textAlign: "center", fontSize: 10, textDecoration: "none", padding: "6px 10px" }}>
                      Conectar
                    </a>
                  )}
                </div>
              );
            })}
          </div>

          {connections.length > 0 && (
            <div>
              <div style={{ fontSize: 9, fontWeight: 700, color: "var(--text-muted)", letterSpacing: "0.06em", marginBottom: 14 }}>DETALLES DE CONEXIONES</div>
              <div style={{ border: "1px solid var(--border-default)", background: "var(--bg-surface)" }}>
                {connections.map((conn, i) => (
                  <div key={conn.id} style={{ padding: "14px 16px", borderBottom: i < connections.length - 1 ? "1px solid var(--border-subtle)" : "none", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                    <div>
                      <div style={{ fontSize: 12, fontWeight: 700, color: "var(--text-primary)", marginBottom: 2 }}>
                        {KNOWN_CLIENTS[conn.client_id]?.name || conn.client_id}
                      </div>
                      <div style={{ fontSize: 10, color: "var(--text-muted)" }}>
                        Scopes: {conn.scopes.join(", ")} · Conectado: {new Date(conn.connected_at).toLocaleDateString("es-CL")}
                        {conn.last_used_at && ` · Último uso: ${new Date(conn.last_used_at).toLocaleDateString("es-CL")}`}
                      </div>
                    </div>
                    <button onClick={() => handleRevoke(conn.client_id)} disabled={revoking === conn.client_id} style={{ fontSize: 10, color: "var(--text-error)", background: "none", border: "1px solid var(--text-error)", padding: "5px 10px", cursor: "pointer", fontFamily: "inherit" }}>
                      {revoking === conn.client_id ? "Revocando..." : "Revocar"}
                    </button>
                  </div>
                ))}
              </div>
            </div>
          )}
          {connections.length === 0 && mcpToken && (
            <div style={{ textAlign: "center", padding: "40px 0", color: "var(--text-muted)", fontSize: 12 }}>
              Sin conexiones activas — conecta tu primer cliente arriba
            </div>
          )}
        </div>
      )}

      {tab === "audit" && (
        auditLog.length === 0 ? (
          <div style={{ textAlign: "center", padding: "40px 0", color: "var(--text-muted)", fontSize: 12 }}>Sin actividad MCP reciente</div>
        ) : (
          <div style={{ border: "1px solid var(--border-default)", background: "var(--bg-surface)" }}>
            {auditLog.map((entry, i) => (
              <div key={entry.id} style={{ padding: "12px 16px", borderBottom: i < auditLog.length - 1 ? "1px solid var(--border-subtle)" : "none" }}>
                <div style={{ display: "flex", justifyContent: "space-between" }}>
                  <span style={{ fontSize: 11, fontWeight: 700, color: "var(--accent)" }}>{TOOL_LABELS[entry.tool_name] || entry.tool_name}</span>
                  <span style={{ fontSize: 10, color: "var(--text-muted)" }}>{new Date(entry.called_at).toLocaleString("es-CL", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" })}</span>
                </div>
                {entry.result_preview && (
                  <div style={{ fontSize: 10, color: "var(--text-secondary)", marginTop: 4, fontFamily: "var(--font-mono)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{entry.result_preview}</div>
                )}
              </div>
            ))}
          </div>
        )
      )}

      {tab === "docs" && (
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          <div style={{ background: "var(--bg-surface)", border: "1px solid var(--border-default)", padding: "20px" }}>
            <div style={{ fontSize: 11, fontWeight: 700, color: "var(--text-primary)", marginBottom: 12 }}>Claude Desktop (claude_desktop_config.json)</div>
            <pre style={{ background: "var(--bg-base)", border: "1px solid var(--border-default)", padding: "14px", fontSize: 10, color: "var(--text-secondary)", overflow: "auto", fontFamily: "var(--font-mono)", margin: 0 }}>{`{\n  "mcpServers": {\n    "claria-cotizador": {\n      "command": "npx",\n      "args": ["-y", "@claria/mcp-server"],\n      "env": {\n        "CLARIA_TOKEN": "${mcpToken || "<tu-token-mcp>"}",\n        "CLARIA_USER_ID": "${userId || "<tu-user-id>"}"\n      }\n    }\n  }\n}`}</pre>
          </div>
          <div style={{ background: "var(--bg-surface)", border: "1px solid var(--border-default)", padding: "20px" }}>
            <div style={{ fontSize: 11, fontWeight: 700, color: "var(--text-primary)", marginBottom: 12 }}>Herramientas disponibles ({Object.keys(TOOL_LABELS).length})</div>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: 8 }}>
              {Object.entries(TOOL_LABELS).map(([key, label]) => (
                <div key={key} style={{ background: "var(--bg-base)", border: "1px solid var(--border-default)", padding: "8px 12px" }}>
                  <div style={{ fontSize: 10, fontWeight: 700, color: "var(--accent)" }}>{label}</div>
                  <div style={{ fontSize: 9, color: "var(--text-muted)", fontFamily: "var(--font-mono)" }}>{key}</div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </>
  );
}
