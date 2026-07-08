"use client";
import { useState, useEffect } from "react";
import { createClient } from "@/lib/supabase/client";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface ApiKey {
  id: string;
  nombre: string;
  key_prefix: string;
  plan: string;
  activa: boolean;
  ultimo_uso_at: string | null;
  created_at: string;
}

interface Webhook {
  id: string;
  url: string;
  eventos: string[];
  activo: boolean;
  ultimo_envio_at: string | null;
  ultimo_status: number | null;
  ultimos_logs?: { exitoso: boolean }[];
}

interface Usage {
  cotizaciones: { usadas: number; limite: number; ilimitado: boolean };
  ocs: { usadas: number; limite: number; ilimitado: boolean };
}

const CODE_SNIPPETS = {
  python: `import requests

headers = {"X-Claria-Key": "claria_live_xxx"}

response = requests.post(
    "${API_URL}/api/v1/cotizar",
    headers=headers,
    json={"item": "válvula de paso 2 pulgadas", "cantidad": 10}
)

data = response.json()
print(data["proveedores"][0]["precio_unitario"])`,

  javascript: `const response = await fetch('${API_URL}/api/v1/cotizar', {
  method: 'POST',
  headers: {
    'X-Claria-Key': 'claria_live_xxx',
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({ item: 'válvula de paso 2 pulgadas', cantidad: 10 })
})

const data = await response.json()
console.log(data.proveedores[0].precio_unitario)`,

  curl: `curl -X POST ${API_URL}/api/v1/cotizar \\
  -H "X-Claria-Key: claria_live_xxx" \\
  -H "Content-Type: application/json" \\
  -d '{"item": "válvula de paso 2 pulgadas", "cantidad": 10}'`,
};

const TODOS_EVENTOS = ["oc.confirmada", "cotizacion.completada", "factura.recibida", "proveedor.respondio"];

export default function DevelopersPage() {
  const [user, setUser] = useState<{ id: string; plan: string } | null>(null);
  const [keys, setKeys] = useState<ApiKey[]>([]);
  const [webhooks, setWebhooks] = useState<Webhook[]>([]);
  const [usage, setUsage] = useState<Usage | null>(null);

  const [showCreateKey, setShowCreateKey] = useState(false);
  const [newKeyName, setNewKeyName] = useState("");
  const [newKeyModo, setNewKeyModo] = useState<"live" | "test">("live");
  const [createdKey, setCreatedKey] = useState<string | null>(null);
  const [showWebhookForm, setShowWebhookForm] = useState(false);
  const [webhookUrl, setWebhookUrl] = useState("");
  const [webhookSecret, setWebhookSecret] = useState("");
  const [webhookEventos, setWebhookEventos] = useState<string[]>(["oc.confirmada"]);
  const [testingWebhook, setTestingWebhook] = useState<string | null>(null);

  const [tab, setTab] = useState<"keys" | "webhooks" | "uso" | "docs">("keys");
  const [codeTab, setCodeTab] = useState<"python" | "javascript" | "curl">("python");
  const [copied, setCopied] = useState(false);
  const [revoking, setRevoking] = useState<string | null>(null);

  useEffect(() => {
    createClient().auth.getUser().then(async ({ data: { user: u } }) => {
      if (!u) return;
      setUser({ id: u.id, plan: u.user_metadata?.plan || "free" });
      const keysResp = await fetch(`${API_URL}/api/v1/keys`, { headers: { "X-Claria-User-Id": u.id } });
      if (keysResp.ok) { const d = await keysResp.json(); setKeys(d.keys || []); }
    });
  }, []);

  const handleCreateKey = async () => {
    if (!user || !newKeyName.trim()) return;
    const resp = await fetch(`${API_URL}/api/v1/keys`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Claria-User-Id": user.id, "X-Claria-User-Plan": user.plan },
      body: JSON.stringify({ nombre: newKeyName, modo: newKeyModo }),
    });
    if (resp.ok) {
      const data = await resp.json();
      setCreatedKey(data.key);
      setShowCreateKey(false);
      setNewKeyName("");
      const r = await fetch(`${API_URL}/api/v1/keys`, { headers: { "X-Claria-User-Id": user.id } });
      if (r.ok) setKeys((await r.json()).keys || []);
    }
  };

  const handleRevoke = async (keyId: string) => {
    if (!user) return;
    setRevoking(keyId);
    await fetch(`${API_URL}/api/v1/keys/${keyId}`, { method: "DELETE", headers: { "X-Claria-User-Id": user.id } });
    setKeys(prev => prev.filter(k => k.id !== keyId));
    setRevoking(null);
  };

  const handleAddWebhook = async () => {
    if (!user || !webhookUrl) return;
    await fetch(`${API_URL}/api/v1/webhooks/configurar`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Claria-Key": "internal" },
      body: JSON.stringify({ url: webhookUrl, eventos: webhookEventos, secret: webhookSecret || undefined }),
    });
    setShowWebhookForm(false); setWebhookUrl(""); setWebhookSecret("");
  };

  const handleTestWebhook = async (id: string) => {
    setTestingWebhook(id);
    await fetch(`${API_URL}/api/v1/webhooks/${id}/test`, { method: "POST", headers: { "X-Claria-Key": "internal" } });
    setTimeout(() => setTestingWebhook(null), 2000);
  };

  const copyKey = (text: string) => { navigator.clipboard.writeText(text); setCopied(true); setTimeout(() => setCopied(false), 2000); };

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
        <span style={{ fontSize: 10, fontWeight: 700, color: "var(--text-muted)", letterSpacing: "0.06em", display: "block", marginBottom: 6 }}>DEVELOPERS · API PÚBLICA v1</span>
        <h1 style={{ fontSize: 26, fontWeight: 700, color: "var(--text-primary)", margin: "0 0 6px", letterSpacing: "-0.02em" }}>API</h1>
        <p style={{ fontSize: 12, color: "var(--text-secondary)", margin: 0 }}>Gestiona tus API keys, webhooks y acceso programático.</p>
      </div>

      <div style={{ borderBottom: "1px solid var(--border-default)", marginBottom: 24, display: "flex", gap: 4 }}>
        {(["keys", "webhooks", "uso", "docs"] as const).map(t => (
          <button key={t} style={tabBtn(tab === t)} onClick={() => setTab(t)}>
            {t === "keys" ? "API KEYS" : t === "webhooks" ? "WEBHOOKS" : t === "uso" ? "USO DEL MES" : "QUICK START"}
          </button>
        ))}
      </div>

      {tab === "keys" && (
        <div>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
            <div style={{ fontSize: 11, color: "var(--text-muted)" }}>{keys.filter(k => k.activa).length} key(s) activa(s)</div>
            <button onClick={() => setShowCreateKey(true)} className="btn-swiss-primary" style={{ fontSize: 11, padding: "7px 14px" }}>+ Nueva API key</button>
          </div>

          {createdKey && (
            <div style={{ background: "var(--bg-surface)", border: "1px solid var(--text-success)", borderLeft: "3px solid var(--text-success)", padding: "20px", marginBottom: 20 }}>
              <div style={{ fontSize: 12, fontWeight: 700, color: "var(--text-success)", marginBottom: 6 }}>API Key creada — guarda esto ahora</div>
              <p style={{ fontSize: 11, color: "var(--text-secondary)", marginBottom: 12 }}>Esta es la única vez que podrás ver la key completa.</p>
              <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                <code style={{ flex: 1, background: "var(--bg-base)", border: "1px solid var(--border-default)", padding: "10px 14px", fontSize: 11, color: "var(--text-primary)", fontFamily: "var(--font-mono)", overflowX: "auto" }}>{createdKey}</code>
                <button onClick={() => copyKey(createdKey)} className="btn-swiss-primary" style={{ padding: "10px 16px", fontSize: 11, whiteSpace: "nowrap" }}>{copied ? "Copiada ✓" : "Copiar"}</button>
              </div>
              <button onClick={() => setCreatedKey(null)} style={{ marginTop: 10, background: "none", border: "none", color: "var(--text-muted)", fontSize: 10, cursor: "pointer", fontFamily: "inherit" }}>Ya la guardé — cerrar</button>
            </div>
          )}

          {showCreateKey && (
            <div style={{ background: "var(--bg-surface)", border: "1px solid var(--border-default)", padding: "20px", marginBottom: 20 }}>
              <div style={{ fontSize: 12, fontWeight: 700, color: "var(--text-primary)", marginBottom: 16 }}>Nueva API Key</div>
              <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                <div>
                  <div style={{ fontSize: 9, fontWeight: 700, color: "var(--text-muted)", letterSpacing: "0.06em", marginBottom: 6 }}>NOMBRE</div>
                  <input value={newKeyName} onChange={e => setNewKeyName(e.target.value)} placeholder="Ej: Defontana producción" style={inputSt} />
                </div>
                <div>
                  <div style={{ fontSize: 9, fontWeight: 700, color: "var(--text-muted)", letterSpacing: "0.06em", marginBottom: 6 }}>MODO</div>
                  <div style={{ display: "flex", gap: 8 }}>
                    {(["live", "test"] as const).map(m => (
                      <button key={m} onClick={() => setNewKeyModo(m)} style={{ padding: "6px 16px", fontSize: 10, fontWeight: newKeyModo === m ? 700 : 400, background: newKeyModo === m ? "var(--accent)" : "var(--bg-surface)", color: newKeyModo === m ? "#fff" : "var(--text-muted)", border: `1px solid ${newKeyModo === m ? "var(--accent)" : "var(--border-default)"}`, cursor: "pointer", fontFamily: "var(--font-mono)" }}>
                        {m === "live" ? "Producción" : "Test (sandbox)"}
                      </button>
                    ))}
                  </div>
                </div>
                <div style={{ display: "flex", gap: 8 }}>
                  <button onClick={handleCreateKey} disabled={!newKeyName.trim()} className="btn-swiss-primary" style={{ padding: "8px 20px", fontSize: 11 }}>Crear key</button>
                  <button onClick={() => setShowCreateKey(false)} className="btn-swiss-secondary" style={{ padding: "8px 16px", fontSize: 11 }}>Cancelar</button>
                </div>
              </div>
            </div>
          )}

          {keys.length === 0 ? (
            <div style={{ textAlign: "center", padding: "48px 0", color: "var(--text-muted)", fontSize: 12 }}>Sin API keys — crea tu primera key para comenzar a integrar</div>
          ) : (
            <div style={{ border: "1px solid var(--border-default)", background: "var(--bg-surface)" }}>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 140px 80px 110px 80px 70px", padding: "8px 16px", borderBottom: "1px solid var(--border-default)", background: "var(--bg-base)" }}>
                {["NOMBRE", "KEY", "PLAN", "ÚLTIMO USO", "ESTADO", ""].map(h => <div key={h} style={{ fontSize: 9, fontWeight: 700, color: "var(--text-muted)", letterSpacing: "0.06em" }}>{h}</div>)}
              </div>
              {keys.map((k, i) => (
                <div key={k.id} style={{ display: "grid", gridTemplateColumns: "1fr 140px 80px 110px 80px 70px", padding: "10px 16px", borderBottom: i < keys.length - 1 ? "1px solid var(--border-subtle)" : "none", alignItems: "center" }}>
                  <div style={{ fontSize: 12, fontWeight: 700, color: "var(--text-primary)" }}>{k.nombre}</div>
                  <code style={{ fontSize: 10, color: "var(--accent)", fontFamily: "var(--font-mono)" }}>{k.key_prefix}••••••••</code>
                  <div style={{ fontSize: 11, color: "var(--text-secondary)", textTransform: "capitalize" }}>{k.plan}</div>
                  <div style={{ fontSize: 11, color: "var(--text-muted)" }}>{k.ultimo_uso_at ? new Date(k.ultimo_uso_at).toLocaleDateString("es-CL") : "Nunca"}</div>
                  <div><span style={{ fontSize: 9, fontWeight: 700, color: k.activa ? "var(--text-success)" : "var(--text-error)", border: `1px solid ${k.activa ? "var(--text-success)" : "var(--text-error)"}`, padding: "2px 7px" }}>{k.activa ? "ACTIVA" : "REVOCADA"}</span></div>
                  <div>{k.activa && <button onClick={() => handleRevoke(k.id)} disabled={revoking === k.id} style={{ background: "none", color: "var(--text-error)", border: "1px solid var(--text-error)", padding: "3px 8px", fontSize: 9, cursor: "pointer", fontFamily: "inherit" }}>{revoking === k.id ? "..." : "Revocar"}</button>}</div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {tab === "webhooks" && (
        <div>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
            <div style={{ fontSize: 11, color: "var(--text-muted)" }}>{webhooks.filter(w => w.activo).length} webhook(s) activo(s)</div>
            <button onClick={() => setShowWebhookForm(true)} className="btn-swiss-primary" style={{ fontSize: 11, padding: "7px 14px" }}>+ Agregar webhook</button>
          </div>
          {showWebhookForm && (
            <div style={{ background: "var(--bg-surface)", border: "1px solid var(--border-default)", padding: "20px", marginBottom: 20 }}>
              <div style={{ fontSize: 12, fontWeight: 700, color: "var(--text-primary)", marginBottom: 16 }}>Nuevo webhook</div>
              <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                <div><div style={{ fontSize: 9, fontWeight: 700, color: "var(--text-muted)", letterSpacing: "0.06em", marginBottom: 6 }}>URL DEL ENDPOINT</div><input value={webhookUrl} onChange={e => setWebhookUrl(e.target.value)} placeholder="https://tu-erp.cl/webhook/claria" style={inputSt} /></div>
                <div><div style={{ fontSize: 9, fontWeight: 700, color: "var(--text-muted)", letterSpacing: "0.06em", marginBottom: 6 }}>SECRET HMAC (opcional)</div><input value={webhookSecret} onChange={e => setWebhookSecret(e.target.value)} placeholder="mi_secret_privado" type="password" style={inputSt} /></div>
                <div>
                  <div style={{ fontSize: 9, fontWeight: 700, color: "var(--text-muted)", letterSpacing: "0.06em", marginBottom: 8 }}>EVENTOS</div>
                  <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                    {TODOS_EVENTOS.map(ev => (
                      <button key={ev} onClick={() => setWebhookEventos(prev => prev.includes(ev) ? prev.filter(e => e !== ev) : [...prev, ev])} style={{ fontSize: 10, padding: "5px 10px", cursor: "pointer", fontFamily: "var(--font-mono)", background: webhookEventos.includes(ev) ? "var(--accent-muted)" : "var(--bg-base)", color: webhookEventos.includes(ev) ? "var(--accent)" : "var(--text-muted)", border: `1px solid ${webhookEventos.includes(ev) ? "var(--accent)" : "var(--border-default)"}`, fontWeight: webhookEventos.includes(ev) ? 700 : 400 }}>{ev}</button>
                    ))}
                  </div>
                </div>
                <div style={{ display: "flex", gap: 8 }}>
                  <button onClick={handleAddWebhook} className="btn-swiss-primary" style={{ padding: "8px 20px", fontSize: 11 }}>Guardar webhook</button>
                  <button onClick={() => setShowWebhookForm(false)} className="btn-swiss-secondary" style={{ padding: "8px 16px", fontSize: 11 }}>Cancelar</button>
                </div>
              </div>
            </div>
          )}
          {webhooks.length === 0 ? (
            <div style={{ textAlign: "center", padding: "48px 0" }}>
              <div style={{ fontSize: 12, color: "var(--text-muted)", fontWeight: 700, marginBottom: 6 }}>Sin webhooks configurados</div>
              <div style={{ fontSize: 11, color: "var(--text-muted)" }}>Agrega un webhook para recibir eventos en tiempo real en tu ERP</div>
            </div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 1 }}>
              {webhooks.map(wh => {
                const exitosos = (wh.ultimos_logs || []).filter(l => l.exitoso).length;
                const total = (wh.ultimos_logs || []).length;
                return (
                  <div key={wh.id} style={{ background: "var(--bg-surface)", border: "1px solid var(--border-default)", padding: "16px 20px" }}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
                      <div>
                        <div style={{ fontSize: 12, fontWeight: 700, color: "var(--text-primary)", marginBottom: 6, fontFamily: "var(--font-mono)" }}>{wh.url}</div>
                        <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 6 }}>{wh.eventos.map(ev => <span key={ev} style={{ fontSize: 9, color: "var(--accent)", border: "1px solid var(--accent)", padding: "2px 7px" }}>{ev}</span>)}</div>
                        <div style={{ fontSize: 10, color: "var(--text-muted)" }}>{wh.ultimo_envio_at && `Último envío: ${new Date(wh.ultimo_envio_at).toLocaleString("es-CL")} · `}{total > 0 && `Éxito: ${exitosos}/${total}`}</div>
                      </div>
                      <div style={{ display: "flex", gap: 8 }}>
                        <button onClick={() => handleTestWebhook(wh.id)} disabled={testingWebhook === wh.id} className="btn-swiss-secondary" style={{ fontSize: 10, padding: "5px 12px" }}>{testingWebhook === wh.id ? "Enviando..." : "Probar"}</button>
                        <button style={{ fontSize: 10, color: "var(--text-error)", background: "none", border: "1px solid var(--text-error)", padding: "5px 12px", cursor: "pointer", fontFamily: "inherit" }}>Eliminar</button>
                      </div>
                    </div>
                    {(wh.ultimos_logs || []).length > 0 && (
                      <div style={{ display: "flex", gap: 4, marginTop: 10 }}>
                        {(wh.ultimos_logs || []).slice(0, 10).map((log, i) => <div key={i} style={{ width: 8, height: 8, background: log.exitoso ? "var(--text-success)" : "var(--text-error)" }} />)}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}

      {tab === "uso" && (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: 1, border: "1px solid var(--border-default)" }}>
          {[
            { label: "COTIZACIONES ESTE MES", usadas: usage?.cotizaciones.usadas ?? 0, limite: usage?.cotizaciones.limite ?? 100, ilimitado: usage?.cotizaciones.ilimitado ?? false },
            { label: "OCS EMITIDAS", usadas: usage?.ocs.usadas ?? 0, limite: usage?.ocs.limite ?? 100, ilimitado: usage?.ocs.ilimitado ?? false },
          ].map((item, i) => {
            const pct = item.limite > 0 ? (item.usadas / item.limite) * 100 : 0;
            return (
              <div key={i} style={{ background: "var(--bg-surface)", borderRight: i === 0 ? "1px solid var(--border-default)" : "none", padding: "24px" }}>
                <div style={{ fontSize: 9, fontWeight: 700, color: "var(--text-muted)", letterSpacing: "0.06em", marginBottom: 12 }}>{item.label}</div>
                <div style={{ display: "flex", alignItems: "baseline", gap: 4, marginBottom: 16 }}>
                  <span style={{ fontSize: 32, fontWeight: 700, color: "var(--text-primary)", letterSpacing: "-0.02em" }}>{item.usadas}</span>
                  <span style={{ fontSize: 14, color: "var(--text-muted)" }}>/ {item.ilimitado ? "∞" : item.limite}</span>
                </div>
                {!item.ilimitado && <div style={{ background: "var(--border-default)", height: 4 }}><div style={{ width: `${Math.min(pct, 100)}%`, height: "100%", background: pct >= 80 ? "var(--text-warning)" : "var(--accent)" }} /></div>}
              </div>
            );
          })}
        </div>
      )}

      {tab === "docs" && (
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          <div style={{ background: "var(--bg-surface)", border: "1px solid var(--border-default)" }}>
            <div style={{ display: "flex", borderBottom: "1px solid var(--border-default)", padding: "0 4px" }}>
              {(["python", "javascript", "curl"] as const).map(lang => (
                <button key={lang} style={{ padding: "8px 16px", fontSize: 11, fontWeight: codeTab === lang ? 700 : 400, color: codeTab === lang ? "var(--accent)" : "var(--text-muted)", background: "none", border: "none", borderBottom: codeTab === lang ? "2px solid var(--accent)" : "2px solid transparent", cursor: "pointer", fontFamily: "var(--font-mono)" }} onClick={() => setCodeTab(lang)}>
                  {lang === "javascript" ? "JavaScript" : lang.charAt(0).toUpperCase() + lang.slice(1)}
                </button>
              ))}
              <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", padding: "0 12px" }}>
                <button onClick={() => copyKey(CODE_SNIPPETS[codeTab])} className="btn-swiss-secondary" style={{ fontSize: 9, padding: "3px 10px" }}>{copied ? "Copiado ✓" : "Copiar"}</button>
              </div>
            </div>
            <pre style={{ padding: "20px", fontSize: 11, color: "var(--text-secondary)", fontFamily: "var(--font-mono)", margin: 0, overflow: "auto", lineHeight: 1.6 }}>{CODE_SNIPPETS[codeTab]}</pre>
          </div>
          <div style={{ background: "var(--bg-surface)", border: "1px solid var(--border-default)", padding: "20px" }}>
            <div style={{ fontSize: 11, fontWeight: 700, color: "var(--text-primary)", marginBottom: 16 }}>Endpoints principales</div>
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {[
                { method: "POST", path: "/api/v1/cotizar", desc: "Cotizar un item" },
                { method: "POST", path: "/api/v1/cotizar/batch", desc: "Cotización masiva (Business+)" },
                { method: "POST", path: "/api/v1/oc/emitir", desc: "Emitir Orden de Compra" },
                { method: "GET",  path: "/api/v1/oc", desc: "Listar OCs con filtros" },
                { method: "GET",  path: "/api/v1/proveedores", desc: "Listar proveedores" },
                { method: "GET",  path: "/api/v1/estadisticas/gastos", desc: "Estadísticas de gasto" },
                { method: "POST", path: "/api/v1/webhooks/configurar", desc: "Configurar webhook" },
                { method: "GET",  path: "/api/v1/ping", desc: "Verificar conexión" },
              ].map(ep => (
                <div key={ep.path} style={{ display: "flex", alignItems: "center", gap: 12 }}>
                  <span style={{ fontSize: 9, fontWeight: 700, padding: "2px 8px", minWidth: 44, textAlign: "center", background: ep.method === "GET" ? "var(--bg-surface)" : "var(--accent-muted)", color: ep.method === "GET" ? "var(--text-success)" : "var(--accent)", border: `1px solid ${ep.method === "GET" ? "var(--text-success)" : "var(--accent)"}`, fontFamily: "var(--font-mono)" }}>{ep.method}</span>
                  <code style={{ fontSize: 10, color: "var(--text-secondary)", fontFamily: "var(--font-mono)" }}>{ep.path}</code>
                  <span style={{ fontSize: 10, color: "var(--text-muted)" }}>{ep.desc}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </>
  );
}
