"use client";
/**
 * Integraciones · MCP.
 *
 * Antes esta pantalla documentaba un producto que no existe: pedía pegar a mano
 * un "token MCP" que no había forma de obtener, y mostraba una config de
 * Claude Desktop con un paquete npx (`@claria/mcp-server`) que nunca se publicó.
 * El servidor real es Streamable HTTP con OAuth 2.1 + Dynamic Client
 * Registration, así que el usuario NO necesita ningún token: pega la URL en su
 * cliente y la autenticación la negocia el cliente solo, en el navegador.
 */
import { useState, useEffect } from "react";
import { createClient } from "@/lib/supabase/client";
import { authFetch } from "@/lib/authFetch";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const MCP_URL = `${API_URL}/api/mcp`;

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
  result_preview: string;
  called_at: string;
}

/** Instrucciones por cliente. El comando es lo único que el usuario necesita. */
const CLIENTES = [
  {
    id: "claude-code",
    nombre: "Claude Code",
    detalle: "CLI de Anthropic en la terminal",
    lenguaje: "bash",
    comando: (url: string) => `claude mcp add --transport http baiyer ${url}`,
    pasos: [
      "Corré el comando en cualquier carpeta.",
      "Abrí Claude Code y escribí /mcp.",
      "Elegí «baiyer» y autenticá: se abre el navegador con tu sesión de Baiyer.",
    ],
  },
  {
    id: "codex",
    nombre: "Codex",
    detalle: "CLI de OpenAI",
    lenguaje: "toml",
    comando: (url: string) =>
      `# ~/.codex/config.toml\n[mcp_servers.baiyer]\nurl = "${url}"`,
    pasos: [
      "Agregá ese bloque a ~/.codex/config.toml (o usá los subcomandos codex mcp).",
      "Al detectar una url en vez de un command, Codex usa transporte HTTP solo.",
      "En el primer uso te pide autenticar por OAuth en el navegador.",
    ],
  },
  {
    id: "claude-desktop",
    nombre: "Claude Desktop / claude.ai",
    detalle: "Conector remoto, sin instalar nada",
    lenguaje: "text",
    comando: (url: string) => url,
    pasos: [
      "Configuración → Conectores → Agregar conector personalizado.",
      "Pegá la URL. No hace falta comando ni token.",
      "Autorizá en la ventana que se abre.",
    ],
  },
];

export default function IntegracionesPage() {
  const [conexiones, setConexiones] = useState<MCPConnection[]>([]);
  const [actividad, setActividad] = useState<AuditEntry[]>([]);
  const [tab, setTab] = useState<"conectar" | "conexiones" | "audit">("conectar");
  const [revocando, setRevocando] = useState<string | null>(null);
  const [copiado, setCopiado] = useState<string | null>(null);
  const [cargando, setCargando] = useState(true);

  const cargar = async () => {
    try {
      const [conn, audit] = await Promise.all([
        authFetch(`${API_URL}/api/mcp/connections`).then(r => (r.ok ? r.json() : { connections: [] })),
        authFetch(`${API_URL}/api/mcp/audit?limit=20`).then(r => (r.ok ? r.json() : { logs: [] })),
      ]);
      setConexiones(conn.connections || []);
      setActividad(audit.logs || []);
    } catch {
      /* pantalla sigue usable: conectar no depende de esto */
    } finally {
      setCargando(false);
    }
  };

  useEffect(() => {
    createClient().auth.getUser().then(({ data: { user } }) => {
      if (user) cargar();
      else setCargando(false);
    });
  }, []);

  const copiar = (texto: string, clave: string) => {
    navigator.clipboard.writeText(texto);
    setCopiado(clave);
    setTimeout(() => setCopiado(null), 2000);
  };

  const desconectar = async (clientId: string) => {
    setRevocando(clientId);
    try {
      const r = await authFetch(`${API_URL}/api/mcp/connections/${encodeURIComponent(clientId)}`, {
        method: "DELETE",
      });
      if (r.ok) setConexiones(prev => prev.filter(c => c.client_id !== clientId));
    } finally {
      setRevocando(null);
    }
  };

  const tabBtn = (activo: boolean): React.CSSProperties => ({
    padding: "8px 16px", fontSize: 11, fontWeight: activo ? 700 : 400,
    color: activo ? "var(--accent)" : "var(--text-muted)", background: "none", border: "none",
    borderBottom: activo ? "2px solid var(--accent)" : "2px solid transparent",
    cursor: "pointer", fontFamily: "var(--font-mono)", letterSpacing: "0.04em",
  });

  const bloqueSt: React.CSSProperties = {
    background: "var(--bg-base)", border: "1px solid var(--border-default)",
    padding: "12px 14px", fontSize: 10, color: "var(--text-secondary)",
    fontFamily: "var(--font-mono)", overflowX: "auto", margin: 0, whiteSpace: "pre",
  };

  return (
    <>
      <div style={{ marginBottom: 28 }}>
        <div className="section-rule" style={{ marginBottom: 16 }} />
        <span style={{ fontSize: 10, fontWeight: 700, color: "var(--text-muted)", letterSpacing: "0.06em", display: "block", marginBottom: 6 }}>
          INTEGRACIONES · MODEL CONTEXT PROTOCOL
        </span>
        <h1 style={{ fontSize: 26, fontWeight: 700, color: "var(--text-primary)", margin: "0 0 6px", letterSpacing: "-0.02em" }}>MCP</h1>
        <p style={{ fontSize: 12, color: "var(--text-secondary)", margin: 0, maxWidth: 620 }}>
          Conectá Claude Code, Codex u otro cliente MCP a tu cuenta Baiyer para cotizar, comparar
          proveedores y consultar OCs desde tu terminal.
        </p>
      </div>

      <div style={{ borderBottom: "1px solid var(--border-default)", marginBottom: 24, display: "flex", gap: 4 }}>
        {(["conectar", "conexiones", "audit"] as const).map(t => (
          <button key={t} style={tabBtn(tab === t)} onClick={() => setTab(t)}>
            {t === "conectar" ? "Conectar" : t === "conexiones" ? `Conexiones${conexiones.length ? ` (${conexiones.length})` : ""}` : "Actividad"}
          </button>
        ))}
      </div>

      {tab === "conectar" && (
        <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
          <div style={{ background: "var(--bg-surface)", border: "1px solid var(--border-default)", borderLeft: "3px solid var(--accent)", padding: "18px 20px" }}>
            <div style={{ fontSize: 11, fontWeight: 700, color: "var(--text-primary)", marginBottom: 6 }}>
              No necesitás ningún token
            </div>
            <p style={{ fontSize: 11, color: "var(--text-secondary)", margin: "0 0 14px", lineHeight: 1.6 }}>
              El servidor usa OAuth 2.1 con registro dinámico: tu cliente se registra solo y te pide
              autorización en el navegador con la sesión que ya tenés abierta. La única cosa que
              tenés que copiar es esta dirección.
            </p>
            <div style={{ display: "flex", gap: 8, alignItems: "stretch" }}>
              <code style={{ ...bloqueSt, flex: 1, display: "flex", alignItems: "center", color: "var(--text-primary)" }}>{MCP_URL}</code>
              <button onClick={() => copiar(MCP_URL, "url")} className="btn-swiss-secondary" style={{ fontSize: 10, padding: "6px 14px", whiteSpace: "nowrap" }}>
                {copiado === "url" ? "Copiado ✓" : "Copiar"}
              </button>
            </div>
          </div>

          {CLIENTES.map(cliente => {
            const conectado = conexiones.some(c => c.client_id.includes(cliente.id));
            const texto = cliente.comando(MCP_URL);
            return (
              <div key={cliente.id} style={{ background: "var(--bg-surface)", border: "1px solid var(--border-default)", padding: "18px 20px" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 4 }}>
                  <div style={{ fontSize: 13, fontWeight: 700, color: "var(--text-primary)" }}>{cliente.nombre}</div>
                  {conectado && (
                    <span style={{ fontSize: 9, fontWeight: 700, color: "var(--text-success)", border: "1px solid var(--text-success)", padding: "2px 7px" }}>
                      Conectado
                    </span>
                  )}
                </div>
                <div style={{ fontSize: 11, color: "var(--text-muted)", marginBottom: 14 }}>{cliente.detalle}</div>

                <div style={{ display: "flex", gap: 8, alignItems: "stretch", marginBottom: 14 }}>
                  <pre style={{ ...bloqueSt, flex: 1 }}>{texto}</pre>
                  <button onClick={() => copiar(texto, cliente.id)} className="btn-swiss-secondary" style={{ fontSize: 10, padding: "6px 14px", whiteSpace: "nowrap", alignSelf: "flex-start" }}>
                    {copiado === cliente.id ? "Copiado ✓" : "Copiar"}
                  </button>
                </div>

                <ol style={{ margin: 0, paddingLeft: 18, fontSize: 11, color: "var(--text-secondary)", lineHeight: 1.8 }}>
                  {cliente.pasos.map((paso, i) => <li key={i}>{paso}</li>)}
                </ol>
              </div>
            );
          })}

          <div style={{ fontSize: 10, color: "var(--text-muted)", lineHeight: 1.7 }}>
            El acceso queda limitado a tu organización y a los permisos que autorices. Cada llamada
            de una herramienta queda registrada en «Actividad», y podés cortar el acceso de un
            cliente cuando quieras desde «Conexiones».
          </div>
        </div>
      )}

      {tab === "conexiones" && (
        cargando ? (
          <div style={{ textAlign: "center", padding: "40px 0", color: "var(--text-muted)", fontSize: 12 }}>Cargando…</div>
        ) : conexiones.length === 0 ? (
          <div style={{ textAlign: "center", padding: "40px 0", color: "var(--text-muted)", fontSize: 12 }}>
            Todavía no hay clientes conectados. Andá a «Conectar» para agregar el primero.
          </div>
        ) : (
          <div style={{ border: "1px solid var(--border-default)", background: "var(--bg-surface)" }}>
            {conexiones.map((conn, i) => (
              <div key={conn.id} style={{ padding: "14px 16px", borderBottom: i < conexiones.length - 1 ? "1px solid var(--border-subtle)" : "none", display: "flex", justifyContent: "space-between", alignItems: "center", gap: 16 }}>
                <div style={{ minWidth: 0 }}>
                  <div style={{ fontSize: 12, fontWeight: 700, color: "var(--text-primary)", marginBottom: 2 }}>{conn.client_id}</div>
                  <div style={{ fontSize: 10, color: "var(--text-muted)" }}>
                    Conectado: {new Date(conn.connected_at).toLocaleDateString("es-CL")}
                    {conn.last_used_at && ` · Último uso: ${new Date(conn.last_used_at).toLocaleDateString("es-CL")}`}
                    {conn.scopes?.length ? ` · ${conn.scopes.length} permisos` : ""}
                  </div>
                </div>
                <button onClick={() => desconectar(conn.client_id)} disabled={revocando === conn.client_id}
                  style={{ fontSize: 10, color: "var(--text-error)", background: "none", border: "1px solid var(--text-error)", padding: "5px 10px", cursor: "pointer", fontFamily: "inherit", whiteSpace: "nowrap" }}>
                  {revocando === conn.client_id ? "Desconectando…" : "Desconectar"}
                </button>
              </div>
            ))}
          </div>
        )
      )}

      {tab === "audit" && (
        actividad.length === 0 ? (
          <div style={{ textAlign: "center", padding: "40px 0", color: "var(--text-muted)", fontSize: 12 }}>Sin actividad MCP reciente</div>
        ) : (
          <div style={{ border: "1px solid var(--border-default)", background: "var(--bg-surface)" }}>
            {actividad.map((entry, i) => (
              <div key={entry.id} style={{ padding: "12px 16px", borderBottom: i < actividad.length - 1 ? "1px solid var(--border-subtle)" : "none" }}>
                <div style={{ display: "flex", justifyContent: "space-between", gap: 12 }}>
                  <span style={{ fontSize: 11, fontWeight: 700, color: "var(--accent)", fontFamily: "var(--font-mono)" }}>{entry.tool_name}</span>
                  <span style={{ fontSize: 10, color: "var(--text-muted)", whiteSpace: "nowrap" }}>
                    {new Date(entry.called_at).toLocaleString("es-CL", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" })}
                  </span>
                </div>
                {entry.result_preview && (
                  <div style={{ fontSize: 10, color: "var(--text-secondary)", marginTop: 4, fontFamily: "var(--font-mono)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    {entry.result_preview}
                  </div>
                )}
              </div>
            ))}
          </div>
        )
      )}
    </>
  );
}
