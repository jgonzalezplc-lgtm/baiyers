import { createClient } from "@/lib/supabase/server";
import { redirect } from "next/navigation";
import Link from "next/link";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface CotizacionReciente {
  id: string;
  nombre_identificado: string;
  marca: string | null;
  categoria: string | null;
  confianza_ia: string | null;
  created_at: string;
  n_encontrados: number;
  n_enviados: number;
  n_respondieron: number;
  precio_min: number | null;
}

const CONFIANZA_COLORS: Record<string, string> = {
  alto: "var(--text-success)",
  medio: "#92400e",
  bajo: "var(--text-error)",
};

function fmtFecha(iso: string) {
  const d = new Date(iso);
  return `${d.getDate()} ${["Ene","Feb","Mar","Abr","May","Jun","Jul","Ago","Sep","Oct","Nov","Dic"][d.getMonth()]}`;
}

export default async function DashboardPage({
  searchParams,
}: {
  searchParams: Promise<{ gmail?: string }>;
}) {
  const supabase = await createClient();
  const { data: { user } } = await supabase.auth.getUser();
  const sp = await searchParams;
  const gmailRecienConectado = sp.gmail === "conectado";

  if (!user) redirect("/login");

  const plan: string = user.user_metadata?.plan || "free";

  const PLANES: Record<string, { label: string; cotizaciones: number }> = {
    free:     { label: "Free",     cotizaciones: 3 },
    starter:  { label: "Starter",  cotizaciones: 20 },
    pro:      { label: "Pro",      cotizaciones: 100 },
    business: { label: "Business", cotizaciones: 9999 },
  };
  const planInfo = PLANES[plan] ?? PLANES.free;

  // Si Gmail recién conectado, sincronizar email real
  if (gmailRecienConectado) {
    fetch(`${API_URL}/api/gmail/sync-email?user_id=${user!.id}`, { method: "POST" }).catch(() => {});
  }

  // Fetch real stats & recent quotes
  let stats = { cotizaciones: 0, proveedores: 0, ocs: 0, totalOC: 0 };
  let cotizacionesRecientes: CotizacionReciente[] = [];

  try {
    const [statsRes, cotRes] = await Promise.all([
      fetch(`${API_URL}/api/dashboard/stats?user_id=${user.id}`, { cache: "no-store" }).catch(() => null),
      fetch(`${API_URL}/api/cotizaciones?user_id=${user.id}&limit=5`, { cache: "no-store" }).catch(() => null),
    ]);
    if (statsRes?.ok) stats = await statsRes.json();
    if (cotRes?.ok) cotizacionesRecientes = await cotRes.json();
  } catch (_) {}

  return (
    <div>
      {/* Title */}
      <div style={{ marginBottom: 28 }}>
        <span className="label" style={{ fontSize: 10, color: "var(--text-muted)", letterSpacing: "0.06em", display: "block", marginBottom: 6 }}>
          COTIZADOR INTELIGENTE
        </span>
        <h1 style={{ fontSize: 28, fontWeight: 700, color: "var(--text-primary)", margin: "0 0 6px", letterSpacing: "-0.02em" }}>
          Dashboard
        </h1>
        <p style={{ fontSize: 12, color: "var(--text-secondary)", margin: 0 }}>¿Qué necesitas cotizar hoy?</p>
      </div>

      {/* Stats row */}
      <div style={{
        display: "grid",
        gridTemplateColumns: "repeat(3,1fr)",
        border: "1px solid var(--border-default)",
        marginBottom: 24,
      }}>
        {[
          {
            label: "COTIZACIONES ESTE MES",
            val: stats.cotizaciones,
            sub: `Límite: ${planInfo.cotizaciones === 9999 ? "ilimitadas" : planInfo.cotizaciones + "/mes"}`,
            subColor: "var(--text-muted)",
          },
          {
            label: "PROVEEDORES CONTACTADOS",
            val: stats.proveedores,
            sub: "Red en crecimiento",
            subColor: "var(--text-muted)",
          },
          {
            label: "OC EMITIDAS",
            val: stats.ocs,
            sub: stats.totalOC > 0
              ? `$${stats.totalOC.toLocaleString("es-CL")} CLP total`
              : plan === "free" || plan === "starter" ? "Disponible en Pro" : "Activo en tu plan",
            subColor: stats.totalOC > 0 ? "var(--accent)" : "var(--text-muted)",
          },
        ].map((s, i) => (
          <div key={i} style={{
            background: "var(--bg-surface)",
            borderRight: i < 2 ? "1px solid var(--border-default)" : "none",
            padding: "20px 24px",
          }}>
            <div style={{ fontSize: 9, fontWeight: 700, color: "var(--text-muted)", letterSpacing: "0.06em", marginBottom: 12 }}>
              {s.label}
            </div>
            <div style={{ fontSize: 32, fontWeight: 700, color: "var(--text-primary)", letterSpacing: "-0.03em", lineHeight: 1 }}>
              {s.val}
            </div>
            <div style={{ fontSize: 11, color: s.subColor, marginTop: 6 }}>{s.sub}</div>
          </div>
        ))}
      </div>

      {/* Nueva cotización CTA */}
      <div style={{
        background: "var(--bg-surface)",
        border: "1px solid var(--border-default)",
        borderLeft: "3px solid var(--accent)",
        padding: "24px 28px",
        marginBottom: 28,
        display: "flex",
        justifyContent: "space-between",
        alignItems: "center",
        gap: 24,
      }}>
        <div>
          <h2 style={{ fontSize: 15, fontWeight: 700, color: "var(--text-primary)", margin: "0 0 6px", letterSpacing: "-0.01em" }}>
            Nueva cotización
          </h2>
          <p style={{ fontSize: 12, color: "var(--text-secondary)", margin: 0, maxWidth: 380 }}>
            Describe el item o sube una foto — el sistema identifica, busca proveedores y cotiza automáticamente.
          </p>
        </div>
        <a href="/cotizar" className="btn-swiss-primary" style={{ textDecoration: "none", whiteSpace: "nowrap", flexShrink: 0 }}>
          COMENZAR →
        </a>
      </div>

      {/* Cotizaciones recientes */}
      <div>
        <div style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginBottom: 14,
        }}>
          <div style={{ fontSize: 9, fontWeight: 700, color: "var(--text-muted)", letterSpacing: "0.06em" }}>
            COTIZACIONES RECIENTES
          </div>
          <a href="/cotizaciones" className="btn-swiss-secondary" style={{ textDecoration: "none", fontSize: 10, padding: "5px 12px" }}>
            VER TODAS →
          </a>
        </div>

        <div style={{ border: "1px solid var(--border-default)", background: "var(--bg-surface)" }}>
          {/* Cabecera */}
          <div style={{
            display: "grid",
            gridTemplateColumns: "72px 1fr 100px 90px 110px 110px 100px 68px",
            padding: "9px 16px",
            borderBottom: "1px solid var(--border-default)",
            background: "var(--bg-base)",
          }}>
            {["ID", "ITEM", "CATEGORÍA", "CONFIANZA", "CORREOS ENV.", "RESPONDIERON", "PRECIO MIN", "FECHA"].map(h => (
              <div key={h} style={{ fontSize: 9, fontWeight: 700, color: "var(--text-muted)", letterSpacing: "0.06em" }}>{h}</div>
            ))}
          </div>

          {cotizacionesRecientes.length === 0 ? (
            <div style={{ padding: "32px 16px", textAlign: "center", fontSize: 12, color: "var(--text-muted)" }}>
              Aún no hay cotizaciones. <a href="/cotizar" style={{ color: "var(--accent)" }}>Crea tu primera →</a>
            </div>
          ) : (
            cotizacionesRecientes.map((c, i) => {
              const conf = c.confianza_ia?.toLowerCase();
              const tieneRespuestas = c.n_respondieron > 0;
              const tieneEnviados = c.n_enviados > 0;

              return (
                <Link key={c.id} href={`/cotizaciones/${c.id}`}
                  style={{
                    display: "grid",
                    gridTemplateColumns: "72px 1fr 100px 90px 110px 110px 100px 68px",
                    padding: "11px 16px",
                    borderBottom: i < cotizacionesRecientes.length - 1 ? "1px solid var(--border-subtle)" : "none",
                    alignItems: "center",
                    textDecoration: "none", color: "inherit",
                    background: tieneRespuestas ? "var(--fill-success)" : undefined,
                  }}>
                  <div style={{ fontSize: 9, color: "var(--text-muted)", fontFamily: "var(--font-mono)" }}>
                    COT-{c.id.slice(-4).toUpperCase()}
                  </div>
                  <div>
                    <div style={{ fontSize: 12, fontWeight: 700, color: "var(--text-primary)", marginBottom: 1 }}>{c.nombre_identificado}</div>
                    {c.marca && <div style={{ fontSize: 9, color: "var(--text-muted)" }}>{c.marca}</div>}
                  </div>
                  <div style={{ fontSize: 11, color: "var(--text-secondary)" }}>{c.categoria || "—"}</div>
                  <div>
                    {conf ? (
                      <span style={{ fontSize: 9, fontWeight: 700, color: CONFIANZA_COLORS[conf] ?? "var(--text-muted)", border: `1px solid ${CONFIANZA_COLORS[conf] ?? "var(--border-default)"}`, padding: "2px 6px" }}>
                        {conf.toUpperCase()}
                      </span>
                    ) : <span style={{ fontSize: 11, color: "var(--text-muted)" }}>—</span>}
                  </div>
                  {/* Correos enviados */}
                  <div>
                    {tieneEnviados ? (
                      <span style={{ fontSize: 10, fontWeight: 700, color: "#2980b9", border: "1px solid #2980b9", padding: "2px 8px" }}>
                        {c.n_enviados} enviado{c.n_enviados !== 1 ? "s" : ""}
                      </span>
                    ) : (
                      <span style={{ fontSize: 10, color: "var(--text-muted)" }}>
                        {c.n_encontrados > 0 ? `${c.n_encontrados} encontr.` : "—"}
                      </span>
                    )}
                  </div>
                  {/* Respondieron */}
                  <div>
                    {tieneRespuestas ? (
                      <span style={{ fontSize: 10, fontWeight: 700, color: "var(--text-success)", border: "1px solid var(--text-success)", padding: "2px 8px" }}>
                        {c.n_respondieron} respondió
                      </span>
                    ) : tieneEnviados ? (
                      <span style={{ fontSize: 10, color: "var(--text-muted)" }}>Esperando</span>
                    ) : (
                      <span style={{ fontSize: 10, color: "var(--text-muted)" }}>—</span>
                    )}
                  </div>
                  {/* Precio mínimo */}
                  <div style={{ fontSize: 11, fontWeight: 700, color: "var(--text-primary)" }}>
                    {c.precio_min != null ? `$${Math.round(c.precio_min).toLocaleString("es-CL")}` : "—"}
                  </div>
                  <div style={{ fontSize: 10, color: "var(--text-muted)" }}>{fmtFecha(c.created_at)}</div>
                </Link>
              );
            })
          )}
        </div>
      </div>

      {/* Gmail integration (compacto, al final) */}
      {!gmailRecienConectado && (
        <div style={{
          marginTop: 24,
          background: "var(--bg-surface)",
          border: "1px solid var(--border-default)",
          padding: "14px 20px",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
        }}>
          <div>
            <span style={{ fontSize: 9, fontWeight: 700, color: "var(--text-muted)", letterSpacing: "0.06em", display: "block", marginBottom: 4 }}>
              EMAIL AGENT
            </span>
            <div style={{ fontSize: 12, color: "var(--text-secondary)" }}>
              Conecta Gmail para enviar cotizaciones automáticamente
            </div>
          </div>
          <a href={`${API_URL}/api/gmail/auth?user_id=${user.id}`} className="btn-swiss-primary" style={{ textDecoration: "none" }}>
            CONECTAR GMAIL
          </a>
        </div>
      )}
    </div>
  );
}
