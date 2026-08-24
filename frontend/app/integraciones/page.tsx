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
import { Check, Copy, Link2, MessageSquare, Plug, Terminal } from "lucide-react";
import { createClient } from "@/lib/supabase/client";
import { authFetch } from "@/lib/authFetch";
import {
  BtnSecondary, Card, EmptyState, PageHeader, SkeletonBox,
} from "@/components/ui";

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

/**
 * Un cliente por tarjeta. `comando` es opcional: las apps de escritorio y web
 * se configuran desde su propia interfaz, sin terminal.
 *
 * Cada producto guarda su propia conexión. Instalar en Claude Code NO habilita
 * Claude Desktop ni claude.ai: es el mismo servidor y la misma cuenta, pero el
 * alta va una vez por producto. La duda es real y aparece siempre, así que
 * está dicha en la pantalla y no sólo acá.
 */
const CLIENTES: {
  id: string;
  nombre: string;
  detalle: string;
  alcance: string;
  comando?: (url: string) => string;
  pasos: string[];
}[] = [
  {
    id: "claude-code",
    nombre: "Claude Code",
    detalle: "CLI de Anthropic en la terminal",
    alcance: "Todos tus proyectos",
    comando: (url: string) => `claude mcp add --scope user --transport http baiyer ${url}`,
    pasos: [
      "Pega y ejecuta el comando una sola vez.",
      "En Claude Code escribe /mcp, elige «baiyer» y autentica.",
      "Continúa con Google/Gmail, Outlook/Microsoft o tu correo y contraseña.",
    ],
  },
  {
    id: "codex",
    nombre: "Codex",
    detalle: "CLI de OpenAI, app y extensión del IDE",
    alcance: "Todo Codex",
    comando: (url: string) =>
      `codex mcp add baiyer --url ${url}\ncodex mcp login baiyer`,
    pasos: [
      "Pega las dos líneas en tu terminal; no necesitas editar config.toml.",
      "Codex abrirá Baiyer en el navegador para autenticar la conexión.",
      "Continúa con Google/Gmail, Outlook/Microsoft o tu correo y contraseña.",
    ],
  },
  {
    id: "claude-desktop",
    nombre: "Claude Desktop y claude.ai",
    detalle: "El chat de Claude, en escritorio y navegador",
    alcance: "Tu cuenta de Claude",
    pasos: [
      "Abre Configuración → Conectores → Agregar conector personalizado.",
      "Pega la dirección de arriba. No hace falta comando ni token.",
      "Autoriza en la ventana que se abre y continúa con tu cuenta de Baiyer.",
    ],
  },
];

const TABS = [
  { key: "conectar", label: "Conectar" },
  { key: "conexiones", label: "Conexiones" },
  { key: "audit", label: "Actividad" },
] as const;

type TabKey = (typeof TABS)[number]["key"];

export default function IntegracionesPage() {
  const [conexiones, setConexiones] = useState<MCPConnection[]>([]);
  const [actividad, setActividad] = useState<AuditEntry[]>([]);
  const [tab, setTab] = useState<TabKey>("conectar");
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

  /** Bloque de comando. Mono sólo acá, que es donde el monoespaciado sirve. */
  const bloqueCodigo = (texto: string, clave: string) => (
    <div style={{ display: "flex", gap: 8, alignItems: "flex-start" }}>
      {/* `pre-wrap` + `break-word`: es un comando para copiar, verlo entero
          importa más que respetar el ancho. Con scroll horizontal la URL
          quedaba cortada y no se sabía si el comando estaba completo. */}
      <pre style={{
        flex: 1, minWidth: 0, margin: 0, padding: "12px 14px",
        background: "var(--surface-2)", border: "1px solid var(--n-200)",
        borderRadius: "var(--r-md)",
        fontFamily: "var(--font-mono)", fontSize: 13, lineHeight: 1.7,
        color: "var(--n-900)", whiteSpace: "pre-wrap", overflowWrap: "anywhere",
      }}>{texto}</pre>
      <BtnSecondary onClick={() => copiar(texto, clave)} style={{ flexShrink: 0 }}>
        {copiado === clave ? <Check size={15} /> : <Copy size={15} />}
        {copiado === clave ? "Copiado" : "Copiar"}
      </BtnSecondary>
    </div>
  );

  return (
    <div style={{ maxWidth: 780, margin: "0 auto", padding: "0 20px 60px" }}>
      <PageHeader
        eyebrow="Integraciones"
        title="Model Context Protocol"
        subtitle="Conecta Baiyer a Claude Code, Codex o el chat de Claude para cotizar, comparar proveedores y consultar órdenes de compra sin salir de tu asistente."
      />

      <div style={{ display: "flex", gap: 4 }}>
        {TABS.map(t => {
          const activa = tab === t.key;
          const conteo = t.key === "conexiones" && conexiones.length ? ` (${conexiones.length})` : "";
          return (
            <button
              key={t.key}
              onClick={() => setTab(t.key)}
              style={{
                padding: "8px 14px", cursor: "pointer", fontFamily: "var(--font-sans)",
                border: "none", background: "none",
                fontSize: 14, fontWeight: activa ? 600 : 500,
                color: activa ? "var(--brand)" : "var(--n-500)",
                borderBottom: `2px solid ${activa ? "var(--brand)" : "transparent"}`,
              }}
            >
              {t.label}{conteo}
            </button>
          );
        })}
      </div>
      <div style={{ borderBottom: "1px solid var(--n-200)", marginBottom: 24 }} />

      {tab === "conectar" && (
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          <Card padding={20} style={{ display: "flex", gap: 14, alignItems: "flex-start" }}>
            <span style={{
              width: 40, height: 40, flexShrink: 0, borderRadius: "var(--r-md)",
              background: "var(--brand-50)", color: "var(--brand)",
              display: "inline-flex", alignItems: "center", justifyContent: "center",
            }}>
              <Link2 size={20} strokeWidth={1.75} />
            </span>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: 15, fontWeight: 600, color: "var(--n-900)", marginBottom: 4 }}>
                Una sola dirección, sin tokens manuales
              </div>
              <p style={{ fontSize: 13.5, color: "var(--n-600)", lineHeight: 1.6, margin: "0 0 10px" }}>
                Esta es la dirección del servidor. Es la misma para todos los clientes: la pegas
                donde corresponda y autorizas en el navegador con la cuenta que usas para entrar
                a Baiyer (Google/Gmail, Outlook/Microsoft o correo y contraseña).
              </p>
              <p style={{ fontSize: 13.5, color: "var(--n-600)", lineHeight: 1.6, margin: "0 0 14px" }}>
                <strong style={{ color: "var(--n-900)", fontWeight: 600 }}>
                  Cada aplicación se conecta por separado.
                </strong>{" "}
                Instalarlo en Claude Code no lo habilita en Claude Desktop ni en claude.ai: es el
                mismo servidor y la misma cuenta, pero das de alta la conexión una vez por
                aplicación.
              </p>
              {bloqueCodigo(MCP_URL, "url")}
            </div>
          </Card>

          {CLIENTES.map(cliente => (
            <Card key={cliente.id} padding={20}>
              <div style={{ display: "flex", alignItems: "flex-start", gap: 12, marginBottom: 14 }}>
                <span style={{
                  width: 40, height: 40, flexShrink: 0, borderRadius: "var(--r-md)",
                  background: "var(--n-100)", color: "var(--n-600)",
                  display: "inline-flex", alignItems: "center", justifyContent: "center",
                }}>
                  {cliente.comando
                    ? <Terminal size={20} strokeWidth={1.75} />
                    : <MessageSquare size={20} strokeWidth={1.75} />}
                </span>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: 15, fontWeight: 600, color: "var(--n-900)" }}>{cliente.nombre}</div>
                  <div style={{ fontSize: 13, color: "var(--n-600)", marginTop: 2 }}>{cliente.detalle}</div>
                </div>
                <span style={{
                  flexShrink: 0, padding: "3px 10px", borderRadius: "var(--r-pill)",
                  background: "var(--n-100)", color: "var(--n-600)",
                  fontSize: 12.5, fontWeight: 500, whiteSpace: "nowrap",
                }}>
                  {cliente.alcance}
                </span>
              </div>

              {cliente.comando
                ? bloqueCodigo(cliente.comando(MCP_URL), cliente.id)
                : (
                  <p style={{ fontSize: 13.5, color: "var(--n-600)", lineHeight: 1.6, margin: 0 }}>
                    No se configura por terminal: se agrega desde la propia aplicación.
                  </p>
                )}

              {/* `listStyle` explícito: el preflight de Tailwind lo pone en
                  `none`, así que los pasos quedaban sin numerar. */}
              <ol style={{
                margin: "14px 0 0", paddingLeft: 20, listStyle: "decimal",
                fontSize: 13.5, color: "var(--n-600)", lineHeight: 1.8,
              }}>
                {cliente.pasos.map((paso, i) => <li key={i}>{paso}</li>)}
              </ol>
            </Card>
          ))}

          <p style={{ fontSize: 13, color: "var(--n-500)", lineHeight: 1.6, margin: 0 }}>
            El acceso queda limitado a tu organización y a los permisos que autorices. Cada llamada
            de una herramienta queda registrada en «Actividad», y puedes cortar el acceso de un
            cliente cuando quieras desde «Conexiones».
          </p>
        </div>
      )}

      {tab === "conexiones" && (
        cargando ? (
          <SkeletonBox height={160} radius="var(--r-lg)" />
        ) : conexiones.length === 0 ? (
          <Card padding={0}>
            <EmptyState
              icon={Plug}
              title="Todavía no hay clientes conectados"
              description="Ve a «Conectar» y sigue el comando de Claude Code o Codex para agregar el primero."
            />
          </Card>
        ) : (
          <Card padding={0}>
            {conexiones.map((conn, i) => (
              <div key={conn.id} style={{
                padding: "16px 18px", display: "flex", justifyContent: "space-between",
                alignItems: "center", gap: 16,
                borderBottom: i < conexiones.length - 1 ? "1px solid var(--n-200)" : "none",
              }}>
                <div style={{ minWidth: 0 }}>
                  <div style={{ fontSize: 14.5, fontWeight: 600, color: "var(--n-900)" }}>
                    {conn.client_name || "Cliente MCP"}
                  </div>
                  <div style={{ fontSize: 13, color: "var(--n-600)", marginTop: 2 }}>
                    Conectado el {new Date(conn.connected_at).toLocaleDateString("es-CL")}
                    {conn.last_used_at && ` · último uso ${new Date(conn.last_used_at).toLocaleDateString("es-CL")}`}
                    {conn.scopes?.length ? ` · ${conn.scopes.length} permisos` : ""}
                  </div>
                  <div className="mono" style={{ fontSize: 12, color: "var(--n-500)", marginTop: 4 }}>
                    {conn.client_id}
                  </div>
                </div>
                <BtnSecondary
                  onClick={() => desconectar(conn.client_id)}
                  disabled={revocando === conn.client_id}
                  style={{ flexShrink: 0, color: "var(--danger)", borderColor: "var(--n-300)" }}
                >
                  {revocando === conn.client_id ? "Desconectando…" : "Desconectar"}
                </BtnSecondary>
              </div>
            ))}
          </Card>
        )
      )}

      {tab === "audit" && (
        cargando ? (
          <SkeletonBox height={160} radius="var(--r-lg)" />
        ) : actividad.length === 0 ? (
          <Card padding={0}>
            <EmptyState
              icon={Terminal}
              title="Sin actividad reciente"
              description="Acá aparece cada herramienta que un cliente MCP ejecuta con tu cuenta."
            />
          </Card>
        ) : (
          <Card padding={0}>
            {actividad.map((entry, i) => (
              <div key={entry.id} style={{
                padding: "14px 18px",
                borderBottom: i < actividad.length - 1 ? "1px solid var(--n-200)" : "none",
              }}>
                <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "baseline" }}>
                  <span className="mono" style={{ fontSize: 13.5, fontWeight: 600, color: "var(--brand)" }}>
                    {entry.tool_name}
                  </span>
                  <span style={{ fontSize: 12.5, color: "var(--n-500)", whiteSpace: "nowrap" }}>
                    {new Date(entry.called_at).toLocaleString("es-CL", {
                      day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit",
                    })}
                  </span>
                </div>
                {entry.result_preview && (
                  <div className="mono" style={{
                    fontSize: 12.5, color: "var(--n-600)", marginTop: 4,
                    overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
                  }}>
                    {entry.result_preview}
                  </div>
                )}
              </div>
            ))}
          </Card>
        )
      )}
    </div>
  );
}
