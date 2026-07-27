import { createClient } from "@/lib/supabase/server";
import { redirect } from "next/navigation";
import Link from "next/link";
import { FileText } from "lucide-react";
import { Card, Badge, CategoryChip, EmptyState } from "@/components/ui";
import { categoriaLabel, fmtCLP } from "@/components/ui/tokens";

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

  // Fetch real stats & recent quotes — con timeout duro para que un backend
  // lento nunca cuelgue el SSR (usuario quedaba viendo la página en blanco).
  let stats = { cotizaciones: 0, proveedores: 0, ocs: 0, totalOC: 0 };
  let cotizacionesRecientes: CotizacionReciente[] = [];

  const fetchConTimeout = async (url: string, ms = 5000): Promise<Response | null> => {
    const ctrl = new AbortController();
    const t = setTimeout(() => ctrl.abort(), ms);
    try {
      return await fetch(url, { cache: "no-store", signal: ctrl.signal });
    } catch (e) {
      console.warn(`[dashboard SSR] fetch falló: ${url}`, (e as Error).message);
      return null;
    } finally {
      clearTimeout(t);
    }
  };

  try {
    const [statsRes, cotRes] = await Promise.all([
      fetchConTimeout(`${API_URL}/api/dashboard/stats?user_id=${user.id}`),
      fetchConTimeout(`${API_URL}/api/cotizaciones?user_id=${user.id}&limit=5`),
    ]);
    if (statsRes?.ok) stats = await statsRes.json();
    if (cotRes?.ok) cotizacionesRecientes = await cotRes.json();
  } catch (_) { /* silent */ }

  return (
    <div>
      {/* Title */}
      <div style={{ marginBottom: 24, display: "flex", alignItems: "center", gap: 14 }}>
        {user.user_metadata?.logo_url && (
          /* eslint-disable-next-line @next/next/no-img-element */
          <img src={user.user_metadata.logo_url as string} alt={String(user.user_metadata?.empresa ?? "logo")}
            width={52} height={52}
            style={{ objectFit: "contain", borderRadius: "var(--r-md)", border: "1px solid var(--n-200)", background: "#fff", flexShrink: 0 }} />
        )}
        <div>
          {user.user_metadata?.industria && (
            <span style={{ fontSize: 13, color: "var(--brand)", display: "block", marginBottom: 3, fontWeight: 500 }}>
              {String(user.user_metadata.industria)}
            </span>
          )}
          <h1 style={{ fontSize: 26, lineHeight: 1.2, fontWeight: 600, color: "var(--n-900)", margin: "0 0 4px", letterSpacing: "-0.015em" }}>
            {user.user_metadata?.empresa ? `Hola, ${user.user_metadata.empresa}` : "Inicio"}
          </h1>
          <p style={{ fontSize: 14, color: "var(--n-600)", margin: 0 }}>¿Qué necesitas cotizar hoy?</p>
        </div>
      </div>

      {/* Stats row */}
      <div style={{
        display: "grid",
        gridTemplateColumns: "repeat(auto-fit, minmax(210px, 1fr))",
        gap: 12,
        marginBottom: 20,
      }}>
        {[
          {
            label: "Cotizaciones este mes",
            val: stats.cotizaciones,
            sub: `Límite: ${planInfo.cotizaciones === 9999 ? "ilimitadas" : planInfo.cotizaciones + "/mes"}`,
          },
          {
            label: "Proveedores contactados",
            val: stats.proveedores,
            sub: "Red en crecimiento",
          },
          {
            label: "Órdenes de compra emitidas",
            val: stats.ocs,
            sub: stats.totalOC > 0
              ? `${fmtCLP(stats.totalOC)} en total`
              : plan === "free" || plan === "starter" ? "Disponible en Pro" : "Activo en tu plan",
          },
        ].map((s, i) => (
          <Card key={i} padding={18}>
            <div style={{ fontSize: 12.5, color: "var(--n-500)", marginBottom: 8 }}>{s.label}</div>
            <div style={{ fontSize: 30, fontWeight: 600, color: "var(--n-900)", letterSpacing: "-0.02em", lineHeight: 1 }}>
              {s.val}
            </div>
            <div style={{ fontSize: 12.5, color: "var(--n-600)", marginTop: 6 }}>{s.sub}</div>
          </Card>
        ))}
      </div>

      {/* Nueva cotización CTA */}
      <div style={{
        background: "var(--brand-50)",
        border: "1px solid var(--brand-100)",
        borderRadius: "var(--r-lg)",
        padding: "20px 24px",
        marginBottom: 28,
        display: "flex",
        justifyContent: "space-between",
        alignItems: "center",
        gap: 24,
        flexWrap: "wrap",
      }}>
        <div>
          <h2 style={{ fontSize: 16, fontWeight: 600, color: "var(--n-900)", margin: "0 0 4px" }}>
            Nueva cotización
          </h2>
          <p style={{ fontSize: 13.5, color: "var(--n-600)", margin: 0, maxWidth: 420, lineHeight: 1.6 }}>
            Describe el ítem o sube una foto, el sistema lo identifica, busca proveedores y cotiza automáticamente.
          </p>
        </div>
        <a href="/cotizar" className="btn-swiss-primary" style={{ textDecoration: "none", whiteSpace: "nowrap", flexShrink: 0 }}>
          Comenzar
        </a>
      </div>

      {/* Cotizaciones recientes */}
      <div>
        <div style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginBottom: 12,
        }}>
          <h2 style={{ fontSize: 16, fontWeight: 600, color: "var(--n-900)", margin: 0 }}>
            Cotizaciones recientes
          </h2>
          <a href="/listas" style={{ fontSize: 13.5, fontWeight: 500, color: "var(--brand)", textDecoration: "none" }}>
            Ver todas →
          </a>
        </div>

        <div style={{
          border: "1px solid var(--n-200)", background: "var(--surface)",
          borderRadius: "var(--r-lg)", overflow: "hidden", boxShadow: "var(--shadow-card)",
        }}>
          {/* Cabecera */}
          <div style={{
            display: "grid",
            gridTemplateColumns: "72px 1fr 110px 90px 110px 110px 100px 76px",
            gap: 10,
            padding: "10px 16px",
            borderBottom: "1px solid var(--n-200)",
            background: "var(--canvas)",
          }}>
            {["ID", "Ítem", "Categoría", "Confianza", "Correos env.", "Respondieron", "Precio mín.", "Fecha"].map(h => (
              <div key={h} style={{ fontSize: 12, fontWeight: 600, color: "var(--n-600)" }}>{h}</div>
            ))}
          </div>

          {cotizacionesRecientes.length === 0 ? (
            <EmptyState
              icon={FileText}
              title="Aún no hay cotizaciones"
              description="Describe lo que necesitas comprar y el sistema busca proveedores por ti."
              action={<a href="/cotizar" className="btn-swiss-primary" style={{ textDecoration: "none" }}>Crear mi primera cotización</a>}
            />
          ) : (
            cotizacionesRecientes.map((c, i) => {
              const conf = c.confianza_ia?.toLowerCase();
              const tieneRespuestas = c.n_respondieron > 0;
              const tieneEnviados = c.n_enviados > 0;

              return (
                <Link key={c.id} href={`/listas/${c.id}`}
                  style={{
                    display: "grid",
                    gridTemplateColumns: "72px 1fr 110px 90px 110px 110px 100px 76px",
                    gap: 10,
                    padding: "12px 16px",
                    borderBottom: i < cotizacionesRecientes.length - 1 ? "1px solid var(--n-100)" : "none",
                    alignItems: "center",
                    textDecoration: "none", color: "inherit",
                    background: tieneRespuestas ? "var(--st-aprobada-bg)" : i % 2 ? "var(--canvas)" : undefined,
                  }}>
                  <div style={{ fontSize: 12, color: "var(--n-500)", fontFamily: "var(--font-mono)" }}>
                    COT-{c.id.slice(-4).toUpperCase()}
                  </div>
                  <div style={{ minWidth: 0 }}>
                    <div style={{ fontSize: 14, fontWeight: 600, color: "var(--n-900)" }}>{c.nombre_identificado}</div>
                    {c.marca && <div style={{ fontSize: 12, color: "var(--n-500)" }}>{c.marca}</div>}
                  </div>
                  <div style={{ display: "flex", alignItems: "center", gap: 7, minWidth: 0 }}>
                    <CategoryChip categoria={c.categoria} size={26} />
                    <span style={{ fontSize: 13, color: "var(--n-600)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                      {categoriaLabel(c.categoria)}
                    </span>
                  </div>
                  <div>
                    {conf ? (
                      <Badge status={conf === "alto" ? "aprobada" : conf === "medio" ? "cotizando" : "rechazada"}>
                        {conf}
                      </Badge>
                    ) : <span style={{ fontSize: 13, color: "var(--n-500)" }}>—</span>}
                  </div>
                  {/* Correos enviados */}
                  <div>
                    {tieneEnviados ? (
                      <Badge status="en_curso">{c.n_enviados} enviado{c.n_enviados !== 1 ? "s" : ""}</Badge>
                    ) : (
                      <span style={{ fontSize: 13, color: "var(--n-500)" }}>
                        {c.n_encontrados > 0 ? `${c.n_encontrados} encontr.` : "—"}
                      </span>
                    )}
                  </div>
                  {/* Respondieron */}
                  <div>
                    {tieneRespuestas ? (
                      <Badge status="aprobada">{c.n_respondieron} respondió</Badge>
                    ) : (
                      <span style={{ fontSize: 13, color: "var(--n-500)" }}>{tieneEnviados ? "Esperando" : "—"}</span>
                    )}
                  </div>
                  {/* Precio mínimo */}
                  <div style={{ fontSize: 14, fontWeight: 600, color: "var(--n-900)", fontFamily: "var(--font-mono)", fontVariantNumeric: "tabular-nums" }}>
                    {c.precio_min != null ? fmtCLP(c.precio_min) : "—"}
                  </div>
                  <div style={{ fontSize: 12.5, color: "var(--n-500)" }}>{fmtFecha(c.created_at)}</div>
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
          background: "var(--surface)",
          border: "1px solid var(--n-200)",
          borderRadius: "var(--r-lg)",
          padding: "16px 20px",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          gap: 16,
          flexWrap: "wrap",
        }}>
          <div>
            <div style={{ fontSize: 15, fontWeight: 600, color: "var(--n-900)", marginBottom: 2 }}>
              Agente de correo
            </div>
            <div style={{ fontSize: 13.5, color: "var(--n-600)" }}>
              Conecta Gmail para enviar cotizaciones automáticamente.
            </div>
          </div>
          <a href={`${API_URL}/api/gmail/auth?user_id=${user.id}`} className="btn-swiss-secondary" style={{ textDecoration: "none" }}>
            Conectar Gmail
          </a>
        </div>
      )}
    </div>
  );
}
