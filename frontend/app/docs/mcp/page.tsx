import { Metadata } from "next";
import type { CSSProperties } from "react";

export const metadata: Metadata = {
  title: "Baiyer MCP · Conectar Claude Code y Codex",
  description: "Conecta globalmente Claude Code o Codex a Baiyer mediante OAuth, sin copiar tokens manuales.",
};

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const MCP_URL = `${API_URL}/api/mcp`;

const CLIENTES = [
  {
    nombre: "Claude Code",
    descripcion: "Guarda Baiyer con alcance de usuario para usarlo desde cualquier proyecto.",
    comando: `claude mcp add --scope user --transport http baiyer ${MCP_URL}`,
    siguiente: "Abre Claude Code, escribe /mcp, elige «baiyer» y autentica.",
  },
  {
    nombre: "Codex",
    descripcion: "La configuración global se comparte entre Codex app, CLI y extensión IDE.",
    comando: `codex mcp add baiyer --url ${MCP_URL}\ncodex mcp login baiyer`,
    siguiente: "La segunda línea abre automáticamente la autorización de Baiyer en tu navegador.",
  },
];

const CAPACIDADES = [
  "Crear y administrar listas y proyectos de compra.",
  "Buscar ofertas web y comparar cobertura, precio y proveedor.",
  "Preparar RFQs y revisar respuestas de proveedores.",
  "Solicitar aprobaciones y consultar la trazabilidad del workflow.",
  "Preparar órdenes de compra, facturas, reportes y métricas.",
];

export default function MCPDocsPage() {
  return (
    <main style={{ minHeight: "100vh", background: "var(--bg-base)", padding: "42px 20px" }}>
      <div style={{ maxWidth: 820, margin: "0 auto" }}>
        <a href="/" style={{ fontSize: 10, color: "var(--text-muted)", textDecoration: "none" }}>← Baiyer</a>

        <header style={{ margin: "24px 0 34px" }}>
          <span className="label" style={{ display: "block", color: "var(--accent)", marginBottom: 8 }}>MODEL CONTEXT PROTOCOL</span>
          <h1 style={{ fontSize: 28, color: "var(--text-primary)", margin: "0 0 9px", letterSpacing: "-0.025em" }}>Conecta Baiyer con tu asistente</h1>
          <p style={{ maxWidth: 640, fontSize: 13, lineHeight: 1.65, color: "var(--text-secondary)", margin: 0 }}>
            La conexión usa Streamable HTTP y OAuth 2.1. Se instala una vez, queda disponible de
            forma global y no requiere crear, copiar ni guardar tokens manuales.
          </p>
        </header>

        <section style={sectionStyle}>
          <div className="label" style={{ color: "var(--text-muted)", marginBottom: 8 }}>DIRECCIÓN DEL SERVIDOR</div>
          <code style={{ display: "block", padding: "12px 14px", background: "var(--bg-base)", border: "1px solid var(--border-default)", color: "var(--text-primary)", fontSize: 11, overflowX: "auto" }}>{MCP_URL}</code>
        </section>

        <div style={{ display: "grid", gap: 16, marginBottom: 28 }}>
          {CLIENTES.map((cliente, index) => (
            <section key={cliente.nombre} style={sectionStyle}>
              <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "center", marginBottom: 7 }}>
                <h2 style={{ margin: 0, fontSize: 15, color: "var(--text-primary)" }}>{index + 1}. {cliente.nombre}</h2>
                <span style={{ fontSize: 9, color: "var(--accent)", border: "1px solid var(--accent)", padding: "2px 7px" }}>GLOBAL</span>
              </div>
              <p style={{ margin: "0 0 14px", fontSize: 11, lineHeight: 1.6, color: "var(--text-secondary)" }}>{cliente.descripcion}</p>
              <pre style={codeStyle}>{cliente.comando}</pre>
              <p style={{ margin: "12px 0 0", fontSize: 11, lineHeight: 1.6, color: "var(--text-secondary)" }}>{cliente.siguiente}</p>
            </section>
          ))}
        </div>

        <section style={{ ...sectionStyle, borderLeft: "3px solid var(--accent)" }}>
          <h2 style={{ margin: "0 0 8px", fontSize: 14, color: "var(--text-primary)" }}>Autoriza con tu cuenta Baiyer</h2>
          <p style={{ margin: "0 0 14px", fontSize: 11, lineHeight: 1.65, color: "var(--text-secondary)" }}>
            Cuando se abra el navegador, usa la misma forma con la que creaste tu cuenta: el botón
            de Google/Gmail, el botón de Outlook/Microsoft o tu correo y contraseña. Si ya tienes una sesión
            abierta, sólo debes confirmar la conexión.
          </p>
          <a href="/integraciones" className="btn-swiss-primary" style={{ display: "inline-flex", textDecoration: "none" }}>
            Abrir Baiyer → MCP
          </a>
        </section>

        <section style={{ ...sectionStyle, marginTop: 28 }}>
          <h2 style={{ margin: "0 0 12px", fontSize: 14, color: "var(--text-primary)" }}>Qué puede hacer</h2>
          <ul style={{ margin: 0, paddingLeft: 18, fontSize: 11, lineHeight: 1.8, color: "var(--text-secondary)" }}>
            {CAPACIDADES.map(capacidad => <li key={capacidad}>{capacidad}</li>)}
          </ul>
          <p style={{ margin: "12px 0 0", fontSize: 10, lineHeight: 1.6, color: "var(--text-muted)" }}>
            Las acciones sensibles exigen confirmación explícita. Las conexiones y su actividad se
            pueden revisar o revocar desde la sección MCP de Baiyer.
          </p>
        </section>

        <section style={{ marginTop: 28, paddingTop: 20, borderTop: "1px solid var(--border-default)" }}>
          <details style={{ fontSize: 10, color: "var(--text-muted)" }}>
            <summary style={{ cursor: "pointer", color: "var(--text-secondary)" }}>Detalles técnicos de OAuth</summary>
            <div style={{ marginTop: 12, display: "grid", gap: 7, fontFamily: "var(--font-mono)" }}>
              <span>GET /.well-known/oauth-protected-resource/api/mcp</span>
              <span>GET /.well-known/oauth-authorization-server</span>
              <span>POST /api/mcp/oauth/register · DCR</span>
              <span>GET /api/mcp/oauth/authorize · PKCE S256</span>
              <span>POST /api/mcp/oauth/token · código + refresh rotativo</span>
            </div>
          </details>
        </section>
      </div>
    </main>
  );
}

const sectionStyle: CSSProperties = {
  background: "var(--bg-surface)",
  border: "1px solid var(--border-default)",
  padding: "20px 22px",
  marginBottom: 16,
};

const codeStyle: CSSProperties = {
  margin: 0,
  padding: "13px 14px",
  background: "var(--bg-base)",
  border: "1px solid var(--border-default)",
  color: "var(--text-primary)",
  fontFamily: "var(--font-mono)",
  fontSize: 10,
  lineHeight: 1.65,
  whiteSpace: "pre-wrap",
  overflowX: "auto",
};
