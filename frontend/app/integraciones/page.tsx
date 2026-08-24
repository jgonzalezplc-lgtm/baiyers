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
  client_name?: string;
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

/** Instalación global: se configura una vez y queda en todos los proyectos. */
const CLIENTES = [
  {
    id: "claude-code",
    nombre: "Claude Code",
    detalle: "Disponible globalmente en todos tus proyectos de Claude Code",
    comando: (url: string) => `claude mcp add --scope user --transport http baiyer ${url}`,
    pasos: [
      "Pega y ejecuta el comando una sola vez.",
      "En Claude Code escribe /mcp, elige «baiyer» y autentica.",
      "En Baiyer continúa con Google/Gmail, Outlook/Microsoft o tu correo y contraseña.",
    ],
  },
  {
    id: "codex",
    nombre: "Codex",
    detalle: "Disponible globalmente en Codex app, CLI y extensión IDE",
    comando: (url: string) =>
      `codex mcp add baiyer --url ${url}\ncodex mcp login baiyer`,
    pasos: [
      "Pega las dos líneas en tu terminal; no necesitas editar config.toml.",
      "Codex abrirá Baiyer en el navegador para autenticar la conexión.",
      "Continúa con Google/Gmail, Outlook/Microsoft o tu correo y contraseña.",
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
          Conecta Baiyer una sola vez y úsalo desde cualquier proyecto de Claude Code o Codex para
          cotizar, comparar proveedores y consultar órdenes de compra.
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
              Una instalación global. Sin tokens manuales.
            </div>
            <p style={{ fontSize: 11, color: "var(--text-secondary)", margin: "0 0 14px", lineHeight: 1.6 }}>
              Elige tu cliente, copia su comando y autoriza en el navegador con la misma cuenta que
              usaste para entrar a Baiyer: Google/Gmail, Outlook/Microsoft o correo y contraseña.
            </p>
            <div style={{ display: "flex", gap: 8, alignItems: "stretch" }}>
              <code style={{ ...bloqueSt, flex: 1, display: "flex", alignItems: "center", color: "var(--text-primary)" }}>{MCP_URL}</code>
              <button onClick={() => copiar(MCP_URL, "url")} className="btn-swiss-secondary" style={{ fontSize: 10, padding: "6px 14px", whiteSpace: "nowrap" }}>
                {copiado === "url" ? "Copiado ✓" : "Copiar"}
              </button>
            </div>
          </div>

          {CLIENTES.map(cliente => {
            const texto = cliente.comando(MCP_URL);
            return (
              <div key={cliente.id} style={{ background: "var(--bg-surface)", border: "1px solid var(--border-default)", padding: "18px 20px" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 4 }}>
                  <div style={{ fontSize: 13, fontWeight: 700, color: "var(--text-primary)" }}>{cliente.nombre}</div>
                  <span style={{ fontSize: 9, fontWeight: 700, color: "var(--accent)", border: "1px solid var(--accent)", padding: "2px 7px" }}>GLOBAL</span>
                </div>
                <div style={{ fontSize: 11, color: "var(--text-muted)", marginBottom: 14 }}>{cliente.detalle}</div>

                <div style={{ display: "flex", gap: 8, alignItems: "stretch", marginBottom: 14 }}>
                  <pre style={{ ...bloqueSt, flex: 1 }}>{texto}</pre>
                  <button onClick={() => copiar(texto, cliente.id)} className="btn-swiss-secondary" style={{ fontSize: 10, padding: "6px 14px", whiteSpace: "nowrap", alignSelf: "flex-start" }}>
                    {copiado === cliente.id ? "Copiado ✓" : "Copiar instalación"}
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
                  <div style={{ fontSize: 12, fontWeight: 700, color: "var(--text-primary)", marginBottom: 2 }}>{conn.client_name || "Cliente MCP"}</div>
                  <div style={{ fontSize: 10, color: "var(--text-muted)" }}>
                    Conectado: {new Date(conn.connected_at).toLocaleDateString("es-CL")}
                    {conn.last_used_at && ` · Último uso: ${new Date(conn.last_used_at).toLocaleDateString("es-CL")}`}
                    {conn.scopes?.length ? ` · ${conn.scopes.length} permisos` : ""}
                  </div>
                  <div style={{ fontSize: 9, color: "var(--text-muted)", marginTop: 3, fontFamily: "var(--font-mono)" }}>{conn.client_id}</div>
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
