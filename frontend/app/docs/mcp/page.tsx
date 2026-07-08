import { Metadata } from "next";

export const metadata: Metadata = {
  title: "Claria MCP — Documentacion",
  description: "Integra Claude, ChatGPT y otros LLMs con Claria Cotizador Inteligente via Model Context Protocol (MCP).",
};

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const TOOLS = [
  {
    name: "cotizar_item",
    label: "Cotizar Item",
    description: "Busca precios para un producto en multiples proveedores chilenos e internacionales.",
    params: [
      { name: "descripcion", type: "string", required: true, desc: "Descripcion del item a cotizar" },
      { name: "cantidad", type: "integer", required: false, desc: "Cantidad requerida (default: 1)" },
    ],
    example: `{
  "name": "cotizar_item",
  "arguments": {
    "descripcion": "cable HDMI 2.0 10 metros",
    "cantidad": 3
  }
}`,
  },
  {
    name: "buscar_proveedores",
    label: "Buscar Proveedores",
    description: "Lista proveedores registrados con scores, datos de contacto y estadisticas.",
    params: [
      { name: "rubro", type: "string", required: false, desc: "Filtrar por rubro (ej: electronica, ferreteria)" },
      { name: "ciudad", type: "string", required: false, desc: "Filtrar por ciudad" },
      { name: "min_score", type: "number", required: false, desc: "Score minimo 0-5" },
    ],
    example: `{
  "name": "buscar_proveedores",
  "arguments": {
    "rubro": "electronica",
    "min_score": 4.0
  }
}`,
  },
  {
    name: "emitir_oc",
    label: "Emitir Orden de Compra",
    description: "Emite una OC oficial a un proveedor. Requiere plan Pro o superior.",
    params: [
      { name: "proveedor_id", type: "string", required: true, desc: "ID del proveedor" },
      { name: "items", type: "array", required: true, desc: "Lista de items [{nombre, cantidad, precio_unitario_clp}]" },
      { name: "notas", type: "string", required: false, desc: "Notas adicionales" },
    ],
    example: `{
  "name": "emitir_oc",
  "arguments": {
    "proveedor_id": "uuid-del-proveedor",
    "items": [
      {"nombre": "cable HDMI", "cantidad": 3, "precio_unitario_clp": 15990}
    ]
  }
}`,
  },
  {
    name: "consultar_gastos",
    label: "Consultar Gastos",
    description: "Estadisticas de gasto: total, top proveedores, top items, tendencias.",
    params: [
      { name: "periodo", type: "string", required: false, desc: "mes | trimestre | anio | todo" },
    ],
    example: `{
  "name": "consultar_gastos",
  "arguments": {
    "periodo": "trimestre"
  }
}`,
  },
  {
    name: "crear_recurrencia",
    label: "Crear Recurrencia",
    description: "Configura compras automaticas periodicas para un item.",
    params: [
      { name: "item_nombre", type: "string", required: true, desc: "Item a comprar periodicamente" },
      { name: "cantidad", type: "integer", required: true, desc: "Cantidad por compra" },
      { name: "frecuencia", type: "string", required: true, desc: "semanal | quincenal | mensual | bimestral | trimestral" },
      { name: "precio_maximo_clp", type: "integer", required: false, desc: "Precio maximo aceptable" },
    ],
    example: `{
  "name": "crear_recurrencia",
  "arguments": {
    "item_nombre": "papel bond A4",
    "cantidad": 10,
    "frecuencia": "mensual",
    "precio_maximo_clp": 5000
  }
}`,
  },
  {
    name: "historico_precios",
    label: "Historico de Precios",
    description: "Consulta historial de precios de items comprados anteriormente.",
    params: [
      { name: "item_nombre", type: "string", required: true, desc: "Item a consultar" },
      { name: "precio_actual_clp", type: "integer", required: false, desc: "Precio actual para comparar" },
    ],
    example: `{
  "name": "historico_precios",
  "arguments": {
    "item_nombre": "toner HP 85A",
    "precio_actual_clp": 29990
  }
}`,
  },
  {
    name: "crear_proyecto",
    label: "Crear Proyecto",
    description: "Crea un proyecto con lista de materiales (cubicacion).",
    params: [
      { name: "nombre", type: "string", required: true, desc: "Nombre del proyecto" },
      { name: "items", type: "array", required: true, desc: "Lista de materiales [{nombre, cantidad, unidad}]" },
      { name: "fecha_inicio", type: "string", required: false, desc: "YYYY-MM-DD" },
      { name: "fecha_fin", type: "string", required: false, desc: "YYYY-MM-DD" },
    ],
    example: `{
  "name": "crear_proyecto",
  "arguments": {
    "nombre": "Remodelacion oficina",
    "items": [
      {"nombre": "pintura latex blanca", "cantidad": 20, "unidad": "litro"},
      {"nombre": "rodillo pintura", "cantidad": 4, "unidad": "unidad"}
    ]
  }
}`,
  },
  {
    name: "generar_reporte",
    label: "Generar Reporte",
    description: "Genera reporte PDF o Excel de cotizaciones, OCs o gastos.",
    params: [
      { name: "tipo", type: "string", required: true, desc: "cotizacion | oc | gastos | proyecto | comparativo" },
      { name: "formato", type: "string", required: false, desc: "pdf | excel (default: pdf)" },
      { name: "periodo", type: "string", required: false, desc: "mes | trimestre | anio" },
    ],
    example: `{
  "name": "generar_reporte",
  "arguments": {
    "tipo": "gastos",
    "formato": "excel",
    "periodo": "mes"
  }
}`,
  },
];

export default function MCPDocsPage() {
  return (
    <div style={{ minHeight: "100vh", background: "#060610", padding: "40px 20px" }}>
      <div style={{ maxWidth: 900, margin: "0 auto" }}>

        {/* Header */}
        <div style={{ marginBottom: 40 }}>
          <a href="/" style={{ fontSize: 10, color: "#475569", textDecoration: "none" }}>← Claria</a>
          <div style={{ marginTop: 20 }}>
            <div style={{ display: "inline-block", background: "#6366f122", color: "#6366f1", borderRadius: 6, padding: "3px 10px", fontSize: 10, fontWeight: 700, marginBottom: 12, letterSpacing: "0.1em" }}>
              MODEL CONTEXT PROTOCOL
            </div>
            <h1 style={{ fontSize: 28, fontWeight: 800, color: "#f1f5f9", margin: "0 0 8px" }}>Claria MCP Server</h1>
            <p style={{ fontSize: 13, color: "#94a3b8", maxWidth: 600 }}>
              Conecta Claude, ChatGPT, Gemini y cualquier LLM compatible con MCP a tu cuenta Claria.
              Cotiza productos, emite OCs y analiza gastos directamente desde el chat de IA.
            </p>
          </div>
        </div>

        {/* Quick start */}
        <div style={{ background: "#0a0a18", border: "1px solid #6366f133", borderRadius: 12, padding: "24px", marginBottom: 32 }}>
          <h2 style={{ fontSize: 15, fontWeight: 700, color: "#f1f5f9", margin: "0 0 16px" }}>Inicio rapido — Claude Desktop</h2>
          <p style={{ fontSize: 11, color: "#475569", marginBottom: 16 }}>
            Agrega esto a tu archivo <code style={{ background: "#1a1a2e", padding: "1px 6px", borderRadius: 3, color: "#94a3b8" }}>claude_desktop_config.json</code>:
          </p>
          <pre style={{ background: "#060610", border: "1px solid #1a1a2e", borderRadius: 8, padding: "16px", fontSize: 11, color: "#94a3b8", overflow: "auto", fontFamily: "monospace" }}>{`{
  "mcpServers": {
    "claria-cotizador": {
      "command": "npx",
      "args": ["-y", "@claria/mcp-server"],
      "env": {
        "CLARIA_TOKEN": "<tu-token-mcp>",
        "CLARIA_USER_ID": "<tu-user-id>"
      }
    }
  }
}`}</pre>
          <a
            href="/integraciones"
            style={{ display: "inline-block", marginTop: 16, background: "#6366f1", color: "#fff", padding: "10px 24px", borderRadius: 6, fontSize: 12, fontWeight: 700, textDecoration: "none" }}
          >
            Obtener mi token →
          </a>
        </div>

        {/* OAuth endpoints */}
        <div style={{ background: "#0a0a18", border: "1px solid #1a1a2e", borderRadius: 12, padding: "24px", marginBottom: 32 }}>
          <h2 style={{ fontSize: 15, fontWeight: 700, color: "#f1f5f9", margin: "0 0 16px" }}>Endpoints OAuth 2.1</h2>
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            {[
              { method: "GET", path: "/api/mcp/oauth/authorize", desc: "Pagina de autorizacion (PKCE)" },
              { method: "POST", path: "/api/mcp/oauth/token", desc: "Intercambio de codigo por token" },
              { method: "GET", path: "/api/mcp/oauth/userinfo", desc: "Info del usuario autenticado" },
              { method: "DELETE", path: "/api/mcp/oauth/revoke", desc: "Revocar acceso" },
            ].map(ep => (
              <div key={ep.path} style={{ display: "flex", alignItems: "center", gap: 12 }}>
                <span style={{
                  fontSize: 9, fontWeight: 700, padding: "2px 8px", borderRadius: 3,
                  background: ep.method === "GET" ? "#34d39922" : ep.method === "POST" ? "#6366f122" : "#f8717122",
                  color: ep.method === "GET" ? "#34d399" : ep.method === "POST" ? "#6366f1" : "#f87171",
                  fontFamily: "monospace", minWidth: 44, textAlign: "center",
                }}>{ep.method}</span>
                <code style={{ fontSize: 11, color: "#94a3b8", fontFamily: "monospace" }}>{ep.path}</code>
                <span style={{ fontSize: 11, color: "#475569" }}>{ep.desc}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Tools */}
        <h2 style={{ fontSize: 15, fontWeight: 700, color: "#f1f5f9", margin: "0 0 16px" }}>Herramientas disponibles ({TOOLS.length})</h2>
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          {TOOLS.map(tool => (
            <div key={tool.name} style={{ background: "#0a0a18", border: "1px solid #1a1a2e", borderRadius: 12, overflow: "hidden" }}>
              <div style={{ padding: "16px 20px", borderBottom: "1px solid #0d0d1a" }}>
                <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 6 }}>
                  <code style={{ fontSize: 12, color: "#6366f1", fontFamily: "monospace", fontWeight: 700 }}>{tool.name}</code>
                  <span style={{ fontSize: 11, color: "#f1f5f9", fontWeight: 700 }}>{tool.label}</span>
                </div>
                <p style={{ fontSize: 11, color: "#94a3b8", margin: 0 }}>{tool.description}</p>
              </div>

              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 0 }}>
                <div style={{ padding: "16px 20px", borderRight: "1px solid #0d0d1a" }}>
                  <div style={{ fontSize: 9, color: "#475569", textTransform: "uppercase", letterSpacing: "0.1em", marginBottom: 10 }}>Parametros</div>
                  <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                    {tool.params.map(p => (
                      <div key={p.name}>
                        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                          <code style={{ fontSize: 10, color: "#a78bfa", fontFamily: "monospace" }}>{p.name}</code>
                          <span style={{ fontSize: 9, color: "#475569" }}>{p.type}</span>
                          {p.required && <span style={{ fontSize: 8, color: "#f87171", background: "#f8717122", padding: "1px 5px", borderRadius: 3 }}>req</span>}
                        </div>
                        <div style={{ fontSize: 10, color: "#475569", marginTop: 2, paddingLeft: 0 }}>{p.desc}</div>
                      </div>
                    ))}
                  </div>
                </div>
                <div style={{ padding: "16px 20px" }}>
                  <div style={{ fontSize: 9, color: "#475569", textTransform: "uppercase", letterSpacing: "0.1em", marginBottom: 10 }}>Ejemplo</div>
                  <pre style={{ fontSize: 9, color: "#94a3b8", fontFamily: "monospace", margin: 0, overflow: "auto", background: "#060610", borderRadius: 6, padding: "10px" }}>{tool.example}</pre>
                </div>
              </div>
            </div>
          ))}
        </div>

        {/* Footer */}
        <div style={{ marginTop: 40, paddingTop: 24, borderTop: "1px solid #1a1a2e", textAlign: "center" }}>
          <p style={{ fontSize: 10, color: "#334155" }}>
            Claria MCP · Protocol version 2024-11-05 ·{" "}
            <a href="https://modelcontextprotocol.io" style={{ color: "#475569" }}>modelcontextprotocol.io</a>
          </p>
        </div>
      </div>
    </div>
  );
}
