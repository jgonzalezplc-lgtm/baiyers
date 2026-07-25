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
    <div style={{ minHeight: "100vh", background: "var(--canvas)", padding: "40px 20px" }}>
      <div style={{ maxWidth: 900, margin: "0 auto" }}>

        {/* Header */}
        <div style={{ marginBottom: 40 }}>
          <a href="/" style={{ fontSize: 10, color: "var(--n-600)", textDecoration: "none" }}>← Claria</a>
          <div style={{ marginTop: 20 }}>
            <div style={{ display: "inline-block", background: "var(--brand)22", color: "var(--brand)", borderRadius: 6, padding: "3px 10px", fontSize: 10, fontWeight: 700, marginBottom: 12, letterSpacing: "0.1em" }}>
              MODEL CONTEXT PROTOCOL
            </div>
            <h1 style={{ fontSize: 28, fontWeight: 800, color: "var(--n-900)", margin: "0 0 8px" }}>Claria MCP Server</h1>
            <p style={{ fontSize: 13, color: "var(--n-500)", maxWidth: 600 }}>
              Conecta Claude, ChatGPT, Gemini y cualquier LLM compatible con MCP a tu cuenta Claria.
              Cotiza productos, emite OCs y analiza gastos directamente desde el chat de IA.
            </p>
          </div>
        </div>

        {/* Quick start */}
        <div style={{ background: "var(--surface)", border: "1px solid var(--brand)33", borderRadius: 12, padding: "24px", marginBottom: 32 }}>
          <h2 style={{ fontSize: 15, fontWeight: 700, color: "var(--n-900)", margin: "0 0 16px" }}>Inicio rapido — Claude Desktop</h2>
          <p style={{ fontSize: 11, color: "var(--n-600)", marginBottom: 16 }}>
            Agrega esto a tu archivo <code style={{ background: "var(--n-200)", padding: "1px 6px", borderRadius: 3, color: "var(--n-500)" }}>claude_desktop_config.json</code>:
          </p>
          <pre style={{ background: "var(--canvas)", border: "1px solid var(--n-200)", borderRadius: 8, padding: "16px", fontSize: 11, color: "var(--n-500)", overflow: "auto", fontFamily: "monospace" }}>{`{
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
            style={{ display: "inline-block", marginTop: 16, background: "var(--brand)", color: "#fff", padding: "10px 24px", borderRadius: 6, fontSize: 12, fontWeight: 700, textDecoration: "none" }}
          >
            Obtener mi token →
          </a>
        </div>

        {/* OAuth endpoints */}
        <div style={{ background: "var(--surface)", border: "1px solid var(--n-200)", borderRadius: 12, padding: "24px", marginBottom: 32 }}>
          <h2 style={{ fontSize: 15, fontWeight: 700, color: "var(--n-900)", margin: "0 0 16px" }}>Endpoints OAuth 2.1</h2>
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
                  background: ep.method === "GET" ? "var(--success)22" : ep.method === "POST" ? "var(--brand)22" : "var(--danger)22",
                  color: ep.method === "GET" ? "var(--success)" : ep.method === "POST" ? "var(--brand)" : "var(--danger)",
                  fontFamily: "monospace", minWidth: 44, textAlign: "center",
                }}>{ep.method}</span>
                <code style={{ fontSize: 11, color: "var(--n-500)", fontFamily: "monospace" }}>{ep.path}</code>
                <span style={{ fontSize: 11, color: "var(--n-600)" }}>{ep.desc}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Tools */}
        <h2 style={{ fontSize: 15, fontWeight: 700, color: "var(--n-900)", margin: "0 0 16px" }}>Herramientas disponibles ({TOOLS.length})</h2>
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          {TOOLS.map(tool => (
            <div key={tool.name} style={{ background: "var(--surface)", border: "1px solid var(--n-200)", borderRadius: 12, overflow: "hidden" }}>
              <div style={{ padding: "16px 20px", borderBottom: "1px solid var(--surface-2)" }}>
                <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 6 }}>
                  <code style={{ fontSize: 12, color: "var(--brand)", fontFamily: "monospace", fontWeight: 700 }}>{tool.name}</code>
                  <span style={{ fontSize: 11, color: "var(--n-900)", fontWeight: 700 }}>{tool.label}</span>
                </div>
                <p style={{ fontSize: 11, color: "var(--n-500)", margin: 0 }}>{tool.description}</p>
              </div>

              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 0 }}>
                <div style={{ padding: "16px 20px", borderRight: "1px solid var(--surface-2)" }}>
                  <div style={{ fontSize: 9, color: "var(--n-600)", letterSpacing: "0.1em", marginBottom: 10 }}>Parametros</div>
                  <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                    {tool.params.map(p => (
                      <div key={p.name}>
                        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                          <code style={{ fontSize: 10, color: "var(--brand-400)", fontFamily: "monospace" }}>{p.name}</code>
                          <span style={{ fontSize: 9, color: "var(--n-600)" }}>{p.type}</span>
                          {p.required && <span style={{ fontSize: 8, color: "var(--danger)", background: "var(--danger)22", padding: "1px 5px", borderRadius: 3 }}>req</span>}
                        </div>
                        <div style={{ fontSize: 10, color: "var(--n-600)", marginTop: 2, paddingLeft: 0 }}>{p.desc}</div>
                      </div>
                    ))}
                  </div>
                </div>
                <div style={{ padding: "16px 20px" }}>
                  <div style={{ fontSize: 9, color: "var(--n-600)", letterSpacing: "0.1em", marginBottom: 10 }}>Ejemplo</div>
                  <pre style={{ fontSize: 9, color: "var(--n-500)", fontFamily: "monospace", margin: 0, overflow: "auto", background: "var(--canvas)", borderRadius: 6, padding: "10px" }}>{tool.example}</pre>
                </div>
              </div>
            </div>
          ))}
        </div>

        {/* Footer */}
        <div style={{ marginTop: 40, paddingTop: 24, borderTop: "1px solid var(--n-200)", textAlign: "center" }}>
          <p style={{ fontSize: 10, color: "var(--n-700)" }}>
            Claria MCP · Protocol version 2024-11-05 ·{" "}
            <a href="https://modelcontextprotocol.io" style={{ color: "var(--n-600)" }}>modelcontextprotocol.io</a>
          </p>
        </div>
      </div>
    </div>
  );
}
