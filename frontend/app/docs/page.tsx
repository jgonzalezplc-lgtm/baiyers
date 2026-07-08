import { Metadata } from "next";

export const metadata: Metadata = {
  title: "Claria API Docs — Documentacion para ERPs",
  description: "Integra Defontana, SAP, Bsale y Odoo con Claria Cotizador Inteligente via API REST.",
};

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const SIDEBAR = [
  { id: "intro", label: "Introduccion" },
  { id: "auth", label: "Autenticacion" },
  { id: "cotizar", label: "POST /cotizar" },
  { id: "batch", label: "POST /cotizar/batch" },
  { id: "oc", label: "OC — Ordenes de Compra" },
  { id: "proveedores", label: "Proveedores" },
  { id: "estadisticas", label: "Estadisticas" },
  { id: "webhooks", label: "Webhooks" },
  { id: "errores", label: "Errores" },
  { id: "erps", label: "Integracion por ERP" },
];

export default function DocsPage() {
  return (
    <div style={{ minHeight: "100vh", background: "#060610", display: "flex" }}>

      {/* Sidebar */}
      <div style={{ width: 220, flexShrink: 0, background: "#0a0a18", borderRight: "1px solid #1a1a2e", padding: "28px 0", position: "sticky", top: 0, height: "100vh", overflowY: "auto" }}>
        <div style={{ padding: "0 20px 20px" }}>
          <a href="/" style={{ fontSize: 16, fontWeight: 800, color: "#6366f1", textDecoration: "none", display: "block", marginBottom: 2 }}>Claria</a>
          <div style={{ fontSize: 9, color: "#475569", textTransform: "uppercase", letterSpacing: "0.1em" }}>API v1 · Docs</div>
        </div>
        <nav>
          {SIDEBAR.map(item => (
            <a key={item.id} href={`#${item.id}`} style={{ display: "block", padding: "7px 20px", fontSize: 11, color: "#94a3b8", textDecoration: "none" }}>
              {item.label}
            </a>
          ))}
        </nav>
        <div style={{ padding: "20px 20px 0", marginTop: 20, borderTop: "1px solid #1a1a2e" }}>
          <a href="/developers" style={{ display: "block", fontSize: 10, color: "#6366f1", textDecoration: "none", fontWeight: 700, marginBottom: 8 }}>→ Mis API Keys</a>
          <a href="/docs/mcp" style={{ display: "block", fontSize: 10, color: "#475569", textDecoration: "none" }}>→ MCP Docs</a>
        </div>
      </div>

      {/* Content */}
      <div style={{ flex: 1, padding: "40px 60px", maxWidth: 860, overflowY: "auto" }}>

        {/* Intro */}
        <section id="intro" style={{ marginBottom: 48 }}>
          <div style={{ display: "inline-block", background: "#6366f122", color: "#6366f1", borderRadius: 6, padding: "3px 10px", fontSize: 10, fontWeight: 700, marginBottom: 16, letterSpacing: "0.1em" }}>
            API PUBLICA v1
          </div>
          <h1 style={{ fontSize: 28, fontWeight: 800, color: "#f1f5f9", margin: "0 0 12px" }}>Claria API</h1>
          <p style={{ fontSize: 13, color: "#94a3b8", lineHeight: 1.7, marginBottom: 16 }}>
            La API de Claria permite que cualquier ERP, sistema de compras o aplicacion integre el motor de procurement
            de Claria directamente. Cotiza en segundos, emite OCs y recibe eventos en tiempo real.
          </p>
          <div style={{ display: "flex", gap: 16 }}>
            <div style={{ background: "#0a0a18", border: "1px solid #1a1a2e", borderRadius: 8, padding: "12px 16px" }}>
              <div style={{ fontSize: 9, color: "#475569", textTransform: "uppercase", marginBottom: 4 }}>Base URL</div>
              <code style={{ fontSize: 11, color: "#6366f1", fontFamily: "monospace" }}>{API_URL}/api/v1</code>
            </div>
            <div style={{ background: "#0a0a18", border: "1px solid #1a1a2e", borderRadius: 8, padding: "12px 16px" }}>
              <div style={{ fontSize: 9, color: "#475569", textTransform: "uppercase", marginBottom: 4 }}>Formato</div>
              <code style={{ fontSize: 11, color: "#94a3b8", fontFamily: "monospace" }}>REST · JSON</code>
            </div>
            <div style={{ background: "#0a0a18", border: "1px solid #1a1a2e", borderRadius: 8, padding: "12px 16px" }}>
              <div style={{ fontSize: 9, color: "#475569", textTransform: "uppercase", marginBottom: 4 }}>Auth</div>
              <code style={{ fontSize: 11, color: "#94a3b8", fontFamily: "monospace" }}>X-Claria-Key header</code>
            </div>
          </div>
        </section>

        {/* Auth */}
        <section id="auth" style={{ marginBottom: 48 }}>
          <h2 style={{ fontSize: 18, fontWeight: 700, color: "#f1f5f9", marginBottom: 12 }}>Autenticacion</h2>
          <p style={{ fontSize: 12, color: "#94a3b8", lineHeight: 1.7, marginBottom: 16 }}>
            Todas las requests requieren el header <code style={{ background: "#1a1a2e", padding: "1px 6px", borderRadius: 3, color: "#a78bfa" }}>X-Claria-Key</code> con tu API key.
            Genera tus keys en <a href="/developers" style={{ color: "#6366f1" }}>/developers</a>.
          </p>
          <Pre>{`# Produccion
curl -H "X-Claria-Key: claria_live_xxxxxxxxxxxx" \\
     ${API_URL}/api/v1/ping

# Sandbox (datos de prueba)
curl -H "X-Claria-Key: claria_test_xxxxxxxxxxxx" \\
     ${API_URL}/api/v1/ping`}</Pre>
          <div style={{ marginTop: 16, background: "#0d1a0d", border: "1px solid #34d39933", borderRadius: 8, padding: "12px 16px" }}>
            <div style={{ fontSize: 11, color: "#34d399", fontWeight: 700, marginBottom: 4 }}>Seguridad</div>
            <p style={{ fontSize: 11, color: "#94a3b8", margin: 0 }}>
              Las keys se almacenan solo como hash SHA-256. Si pierdes una key debes generar una nueva.
              Las keys de test (<code style={{ color: "#94a3b8" }}>claria_test_</code>) usan datos de sandbox separados.
            </p>
          </div>
        </section>

        {/* Cotizar */}
        <section id="cotizar" style={{ marginBottom: 48 }}>
          <h2 style={{ fontSize: 18, fontWeight: 700, color: "#f1f5f9", marginBottom: 4 }}>POST /cotizar</h2>
          <p style={{ fontSize: 12, color: "#94a3b8", lineHeight: 1.7, marginBottom: 16 }}>
            Busca precios para un item en multiples proveedores chilenos e internacionales. Retorna lista ordenada por precio.
          </p>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
            <div>
              <Label>Request</Label>
              <Pre>{`POST /api/v1/cotizar
X-Claria-Key: claria_live_xxx
Content-Type: application/json

{
  "item": "válvula de paso 2\" acero",
  "cantidad": 10,
  "unidad": "unidad",
  "numero_parte": "VP-2IN-SS",
  "marca": "Nibco",
  "urgente": false
}`}</Pre>
            </div>
            <div>
              <Label>Response 200</Label>
              <Pre>{`{
  "cotizacion_id": "cot_abc123",
  "item_identificado": {
    "nombre_tecnico": "Válvula de bola 2\"",
    "categoria": "hidraulico",
    "confianza": "alto"
  },
  "proveedores": [
    {
      "nombre": "Hidráulica SpA",
      "precio_unitario": 45000,
      "precio_total": 450000,
      "moneda": "CLP",
      "plazo_entrega_dias": 5,
      "disponibilidad": "en_stock",
      "score_claria": 87
    }
  ],
  "total_proveedores": 8,
  "tiempo_busqueda_ms": 2340,
  "creado_en": "2025-09-15T14:23:00Z"
}`}</Pre>
            </div>
          </div>
        </section>

        {/* Batch */}
        <section id="batch" style={{ marginBottom: 48 }}>
          <h2 style={{ fontSize: 18, fontWeight: 700, color: "#f1f5f9", marginBottom: 4 }}>POST /cotizar/batch</h2>
          <Badge color="#f59e0b">Business+</Badge>
          <p style={{ fontSize: 12, color: "#94a3b8", lineHeight: 1.7, marginBottom: 16, marginTop: 10 }}>
            Cotiza hasta 100 items en paralelo. Ideal para cubicaciones y listas de materiales. Solo en plan Business y Enterprise.
          </p>
          <Pre>{`POST /api/v1/cotizar/batch

{
  "items": [
    { "item": "cable HDMI 10m", "cantidad": 5 },
    { "item": "switch 24 puertos", "cantidad": 2 },
    { "item": "rack 42U", "cantidad": 1 }
  ],
  "proyecto_nombre": "Data Center Norte 2025"
}`}</Pre>
        </section>

        {/* OC */}
        <section id="oc" style={{ marginBottom: 48 }}>
          <h2 style={{ fontSize: 18, fontWeight: 700, color: "#f1f5f9", marginBottom: 12 }}>OC — Ordenes de Compra</h2>

          <div style={{ marginBottom: 20 }}>
            <h3 style={{ fontSize: 13, fontWeight: 700, color: "#f1f5f9", marginBottom: 8 }}>POST /oc/emitir</h3>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
              <div>
                <Label>Request</Label>
                <Pre>{`{
  "cotizacion_id": "cot_abc123",
  "proveedor_id": "prov_xyz",
  "cantidad": 10,
  "precio_unitario": 45000,
  "condiciones_pago": "30_dias",
  "referencia_erp": "PO-2025-1234",
  "notas": "Entregar en bodega"
}`}</Pre>
              </div>
              <div>
                <Label>Response 200</Label>
                <Pre>{`{
  "oc_id": "oc_def456",
  "numero_oc": "OC-2025-0089",
  "estado": "enviada",
  "pdf_url": "https://storage...",
  "referencia_erp": "PO-2025-1234",
  "total": 450000,
  "moneda": "CLP",
  "creado_en": "2025-09-15T14:25Z"
}`}</Pre>
              </div>
            </div>
          </div>

          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            {[
              { method: "GET", path: "/oc/{oc_id}", desc: "Estado de una OC especifica" },
              { method: "GET", path: "/oc?estado=enviada&referencia_erp=PO-2025-1234", desc: "Listar OCs con filtros" },
            ].map(ep => (
              <EndpointRow key={ep.path} {...ep} />
            ))}
          </div>
        </section>

        {/* Proveedores */}
        <section id="proveedores" style={{ marginBottom: 48 }}>
          <h2 style={{ fontSize: 18, fontWeight: 700, color: "#f1f5f9", marginBottom: 12 }}>Proveedores</h2>
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            {[
              { method: "GET",  path: "/proveedores?categoria=hidraulico&score_min=60", desc: "Listar con filtros" },
              { method: "GET",  path: "/proveedores/{id}", desc: "Detalle de proveedor" },
              { method: "POST", path: "/proveedores", desc: "Agregar proveedor" },
              { method: "POST", path: "/proveedores/import", desc: "Importar hasta 500 proveedores" },
            ].map(ep => <EndpointRow key={ep.path} {...ep} />)}
          </div>
        </section>

        {/* Estadisticas */}
        <section id="estadisticas" style={{ marginBottom: 48 }}>
          <h2 style={{ fontSize: 18, fontWeight: 700, color: "#f1f5f9", marginBottom: 12 }}>Estadisticas</h2>
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            {[
              { method: "GET", path: "/estadisticas/gastos?periodo=ultimo_trimestre", desc: "Gasto total, por mes, por categoria" },
              { method: "GET", path: "/estadisticas/proveedores?limit=10", desc: "Top proveedores por score" },
              { method: "GET", path: "/estadisticas/uso_api", desc: "Uso de la API este mes" },
            ].map(ep => <EndpointRow key={ep.path} {...ep} />)}
          </div>
        </section>

        {/* Webhooks */}
        <section id="webhooks" style={{ marginBottom: 48 }}>
          <h2 style={{ fontSize: 18, fontWeight: 700, color: "#f1f5f9", marginBottom: 12 }}>Webhooks</h2>
          <p style={{ fontSize: 12, color: "#94a3b8", lineHeight: 1.7, marginBottom: 16 }}>
            Recibe eventos en tu ERP en tiempo real cuando ocurren acciones en Claria. Soporta firma HMAC-SHA256 para verificar autenticidad.
          </p>

          <h3 style={{ fontSize: 13, fontWeight: 700, color: "#f1f5f9", marginBottom: 8 }}>Configurar</h3>
          <Pre>{`POST /api/v1/webhooks/configurar

{
  "url": "https://erp.empresa.cl/webhook/claria",
  "eventos": ["oc.confirmada", "factura.recibida"],
  "secret": "mi_secret_privado"
}`}</Pre>

          <h3 style={{ fontSize: 13, fontWeight: 700, color: "#f1f5f9", marginBottom: 8, marginTop: 20 }}>Payload recibido en tu ERP</h3>
          <Pre>{`POST https://erp.empresa.cl/webhook/claria
X-Claria-Event: oc.confirmada
X-Claria-Timestamp: 1694781900
X-Claria-Signature: sha256=abc123...

{
  "evento": "oc.confirmada",
  "oc_id": "oc_def456",
  "numero_oc": "OC-2025-0089",
  "referencia_erp": "PO-2025-1234",
  "confirmada_en": "2025-09-15T16:00:00Z",
  "proveedor": "Hidráulica Industrial SpA"
}`}</Pre>

          <h3 style={{ fontSize: 13, fontWeight: 700, color: "#f1f5f9", marginBottom: 8, marginTop: 20 }}>Verificar firma (Python)</h3>
          <Pre>{`import hmac, hashlib, json

def verificar_firma(payload_bytes, timestamp, firma, secret):
    msg = f"{timestamp}.{payload_bytes.decode()}"
    esperada = hmac.new(secret.encode(), msg.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(f"sha256={esperada}", firma)

# En tu endpoint Flask/FastAPI:
firma = request.headers["X-Claria-Signature"]
ts    = request.headers["X-Claria-Timestamp"]
ok    = verificar_firma(request.data, ts, firma, "mi_secret_privado")`}</Pre>

          <div style={{ marginTop: 16, background: "#0a0a18", border: "1px solid #1a1a2e", borderRadius: 8, padding: "12px 16px" }}>
            <div style={{ fontSize: 11, fontWeight: 700, color: "#f1f5f9", marginBottom: 6 }}>Retry logic</div>
            <div style={{ fontSize: 11, color: "#94a3b8" }}>
              Si tu endpoint no responde 2xx, Claria reintenta: inmediato → 5min → 30min → 2h → 24h.
              Despues de 5 intentos fallidos te notificamos por email.
            </div>
          </div>
        </section>

        {/* Errores */}
        <section id="errores" style={{ marginBottom: 48 }}>
          <h2 style={{ fontSize: 18, fontWeight: 700, color: "#f1f5f9", marginBottom: 12 }}>Codigos de error</h2>
          <Pre>{`{
  "error": {
    "codigo": "PLAN_LIMIT_EXCEEDED",
    "mensaje": "Excediste el límite de 100 cotizaciones/mes del plan Pro",
    "plan_actual": "pro",
    "limite": 100,
    "usadas": 100,
    "reinicia_en": "2025-10-01T00:00:00Z",
    "upgrade_url": "https://claria.cc/pricing"
  }
}`}</Pre>
          <div style={{ marginTop: 16, display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
            {[
              { code: "INVALID_API_KEY", status: 401, desc: "Key invalida o inexistente" },
              { code: "API_KEY_EXPIRED", status: 401, desc: "Key expirada" },
              { code: "RATE_LIMIT_EXCEEDED", status: 429, desc: "Demasiadas requests por minuto" },
              { code: "PLAN_LIMIT_EXCEEDED", status: 402, desc: "Limite mensual del plan alcanzado" },
              { code: "ITEM_NOT_IDENTIFIED", status: 400, desc: "No se pudo identificar el item" },
              { code: "BATCH_NOT_AVAILABLE", status: 402, desc: "Batch requiere Business+" },
              { code: "OC_ALREADY_CONFIRMED", status: 409, desc: "OC ya confirmada" },
              { code: "NOT_FOUND", status: 404, desc: "Recurso no encontrado" },
            ].map(e => (
              <div key={e.code} style={{ background: "#0a0a18", border: "1px solid #1a1a2e", borderRadius: 6, padding: "10px 12px" }}>
                <div style={{ fontSize: 10, color: "#f87171", fontFamily: "monospace", fontWeight: 700, marginBottom: 2 }}>{e.code}</div>
                <div style={{ display: "flex", justifyContent: "space-between" }}>
                  <span style={{ fontSize: 10, color: "#94a3b8" }}>{e.desc}</span>
                  <span style={{ fontSize: 9, color: "#475569" }}>HTTP {e.status}</span>
                </div>
              </div>
            ))}
          </div>
        </section>

        {/* ERPs */}
        <section id="erps" style={{ marginBottom: 48 }}>
          <h2 style={{ fontSize: 18, fontWeight: 700, color: "#f1f5f9", marginBottom: 16 }}>Integracion por ERP</h2>

          {[
            {
              name: "Defontana",
              color: "#3b82f6",
              flujo: [
                "Webhook de Defontana se dispara al crear una requisicion",
                "Tu middleware llama POST /api/v1/cotizar con los datos del item",
                "Resultados se muestran en sidebar dentro de Defontana",
                "Usuario aprueba y llamas POST /api/v1/oc/emitir",
                "Claria envia OC al proveedor y te retorna PDF + numero",
                "Webhook oc.confirmada notifica a Defontana para registrar la PO",
              ],
              code: `# 1. Recibir requisicion de Defontana
@app.post("/webhook/defontana")
def requisicion(data: dict):
    resp = requests.post(
        "${API_URL}/api/v1/cotizar",
        headers={"X-Claria-Key": CLARIA_KEY},
        json={"item": data["descripcion"], "cantidad": data["cantidad"]}
    )
    return resp.json()  # Devolver a Defontana`,
            },
            {
              name: "Bsale",
              color: "#10b981",
              flujo: [
                "Webhook de Bsale dispara en 'pedido pendiente'",
                "Items bajo $500k CLP: cotizacion y OC automatica",
                "Items sobre $500k CLP: flujo de aprobacion manual",
                "OC confirmada → Bsale la registra como venta",
              ],
              code: `# Automatico para items < $500k CLP
if precio_estimado < 500_000:
    oc = requests.post("${API_URL}/api/v1/oc/emitir", ...)
else:
    # Enviar a aprobacion manual
    notificar_comprador(item, cotizaciones)`,
            },
            {
              name: "SAP Business One",
              color: "#f59e0b",
              flujo: [
                "Claria actua como proveedor externo de precios en SAP B1",
                "Integracion via SAP Service Layer REST API",
                "Compatible con SAP B1 version 9.3 y superior",
                "Mapeamos Purchase Quotation → POST /cotizar",
              ],
              code: `// SAP B1 Service Layer + Claria
const sap_token = await getSAPToken();
const req = await getSAPPurchaseRequest(prId);

const precios = await fetch('${API_URL}/api/v1/cotizar', {
  method: 'POST',
  headers: {'X-Claria-Key': CLARIA_KEY},
  body: JSON.stringify({item: req.ItemDescription, cantidad: req.Quantity})
});`,
            },
            {
              name: "Odoo 16/17",
              color: "#a78bfa",
              flujo: [
                "Instala el addon claria_procurement en /addons",
                "Configura tu API key en Ajustes → Claria",
                "El boton 'Cotizar con Claria' aparece en Purchase Orders",
                "Resultados se importan directamente como lineas de PO",
              ],
              code: `# /addons/claria_procurement/models/purchase.py
class PurchaseOrder(models.Model):
    def action_claria_quote(self):
        for line in self.order_line:
            resp = requests.post(
                '${API_URL}/api/v1/cotizar',
                headers={'X-Claria-Key': self.env.company.claria_api_key},
                json={'item': line.product_id.name, 'cantidad': line.product_qty}
            )
            line.claria_best_price = resp.json()['proveedores'][0]['precio_unitario']`,
            },
          ].map(erp => (
            <div key={erp.name} style={{ background: "#0a0a18", border: `1px solid ${erp.color}22`, borderRadius: 10, padding: "20px", marginBottom: 16 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 14 }}>
                <div style={{ width: 8, height: 8, borderRadius: "50%", background: erp.color }} />
                <div style={{ fontSize: 14, fontWeight: 700, color: "#f1f5f9" }}>{erp.name}</div>
              </div>
              <ol style={{ margin: "0 0 16px 16px", padding: 0 }}>
                {erp.flujo.map((paso, i) => (
                  <li key={i} style={{ fontSize: 11, color: "#94a3b8", marginBottom: 4, lineHeight: 1.5 }}>{paso}</li>
                ))}
              </ol>
              <pre style={{ background: "#060610", border: "1px solid #1a1a2e", borderRadius: 6, padding: "14px", fontSize: 10, color: "#94a3b8", overflow: "auto", fontFamily: "monospace", margin: 0 }}>{erp.code}</pre>
            </div>
          ))}
        </section>

        {/* Footer */}
        <div style={{ paddingTop: 24, borderTop: "1px solid #1a1a2e", textAlign: "center" }}>
          <p style={{ fontSize: 10, color: "#334155" }}>
            Claria API v1 · <a href="mailto:hola@claria.cc" style={{ color: "#475569" }}>hola@claria.cc</a> · <a href="/developers" style={{ color: "#475569" }}>Obtener API key</a>
          </p>
        </div>

      </div>
    </div>
  );
}

// ─── Utility components ────────────────────────────────────────────────────────

function Pre({ children }: { children: string }) {
  return (
    <pre style={{ background: "#0a0a18", border: "1px solid #1a1a2e", borderRadius: 8, padding: "16px", fontSize: 10, color: "#94a3b8", overflow: "auto", fontFamily: "monospace", margin: 0, lineHeight: 1.6 }}>
      {children}
    </pre>
  );
}

function Label({ children }: { children: string }) {
  return <div style={{ fontSize: 9, color: "#475569", textTransform: "uppercase", letterSpacing: "0.1em", marginBottom: 6 }}>{children}</div>;
}

function Badge({ children, color }: { children: string; color: string }) {
  return (
    <span style={{ display: "inline-block", fontSize: 9, fontWeight: 700, color, background: `${color}22`, border: `1px solid ${color}44`, borderRadius: 4, padding: "2px 8px" }}>
      {children}
    </span>
  );
}

function EndpointRow({ method, path, desc }: { method: string; path: string; desc: string }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 12, background: "#0a0a18", border: "1px solid #1a1a2e", borderRadius: 6, padding: "10px 14px" }}>
      <span style={{
        fontSize: 9, fontWeight: 700, padding: "2px 8px", borderRadius: 3, minWidth: 44, textAlign: "center",
        background: method === "GET" ? "#34d39922" : method === "POST" ? "#6366f122" : method === "DELETE" ? "#f8717122" : "#f59e0b22",
        color: method === "GET" ? "#34d399" : method === "POST" ? "#6366f1" : method === "DELETE" ? "#f87171" : "#f59e0b",
        fontFamily: "monospace",
      }}>{method}</span>
      <code style={{ fontSize: 10, color: "#94a3b8", fontFamily: "monospace", flex: 1 }}>{path}</code>
      <span style={{ fontSize: 10, color: "#475569" }}>{desc}</span>
    </div>
  );
}
