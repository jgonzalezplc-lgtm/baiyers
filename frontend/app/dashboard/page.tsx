import { createClient } from "@/lib/supabase/server";
import { redirect } from "next/navigation";
import Link from "next/link";
import { FileText } from "lucide-react";
import { Card, Badge, EmptyState } from "@/components/ui";
import { fmtCLP } from "@/components/ui/tokens";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface ListaReciente {
  id: string;
  nombre: string;
  created_at: string | null;
  monto_total: number;
  n_items: number;
  n_comparados: number;
  n_definitivos: number;
  aprobacion_estado: "aprobado" | "aprobado_con_observaciones" | "rechazado" | "pendiente" | null;
}

function fmtFecha(iso: string) {
  const d = new Date(iso);
  return `${d.getDate()} ${["Ene","Feb","Mar","Abr","May","Jun","Jul","Ago","Sep","Oct","Nov","Dic"][d.getMonth()]}`;
}

export default async function DashboardPage({
  searchParams,
}: {
  searchParams: Promise<{ gmail?: string }>;
}) {
  let user;
  try {
    const supabase = await createClient();
    const { data } = await supabase.auth.getUser();
    user = data.user;
  } catch (e) {
    console.error("[dashboard] auth.getUser tiró:", (e as Error).message);
    redirect("/login");
  }
  const sp = await searchParams;
  const gmailRecienConectado = sp.gmail === "conectado";

  if (!user) redirect("/login");

  const m = (user.user_metadata ?? {}) as Record<string, unknown>;
  const plan: string = typeof m.plan === "string" ? m.plan : "free";

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
  let listasRecientes: ListaReciente[] = [];
  let gmailConectado = gmailRecienConectado;

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
    const [statsRes, cotRes, gmailRes] = await Promise.all([
      fetchConTimeout(`${API_URL}/api/dashboard/stats?user_id=${user.id}`),
      fetchConTimeout(`${API_URL}/api/listas?user_id=${user.id}`),
      fetchConTimeout(`${API_URL}/api/gmail/status?user_id=${user.id}`),
    ]);
    if (statsRes?.ok) stats = await statsRes.json();
    if (cotRes?.ok) listasRecientes = (await cotRes.json()).slice(0, 5);
    if (gmailRes?.ok) {
      const gmailStatus = await gmailRes.json();
      gmailConectado = Boolean(gmailStatus.connected);
    }
  } catch (_) { /* silent */ }

  return (
    <div>
      {/* Title */}
      <div style={{ marginBottom: 24, display: "flex", alignItems: "center", gap: 14 }}>
        {typeof m.logo_url === "string" && m.logo_url && (
          /* eslint-disable-next-line @next/next/no-img-element */
          <img src={m.logo_url} alt={typeof m.empresa === "string" ? m.empresa : "logo"}
            width={52} height={52}
            style={{ objectFit: "contain", borderRadius: "var(--r-md)", border: "1px solid var(--n-200)", background: "#fff", flexShrink: 0 }} />
        )}
        <div>
          {typeof m.industria === "string" && m.industria && (
            <span style={{ fontSize: 13, color: "var(--brand)", display: "block", marginBottom: 3, fontWeight: 500 }}>
              {m.industria}
            </span>
          )}
          <h1 style={{ fontSize: 26, lineHeight: 1.2, fontWeight: 600, color: "var(--n-900)", margin: "0 0 4px", letterSpacing: "-0.015em" }}>
            {typeof m.empresa === "string" && m.empresa ? `Hola, ${m.empresa}` : "Inicio"}
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
            Listas de cotización recientes
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
            gridTemplateColumns: "1fr 90px 110px 110px 170px 120px 76px",
            gap: 10,
            padding: "10px 16px",
            borderBottom: "1px solid var(--n-200)",
            background: "var(--canvas)",
          }}>
            {["Lista", "Ítems", "Comparados", "Elegidos", "Autorización", "Total", "Fecha"].map(h => (
              <div key={h} style={{ fontSize: 12, fontWeight: 600, color: "var(--n-600)" }}>{h}</div>
            ))}
          </div>

          {listasRecientes.length === 0 ? (
            <EmptyState
              icon={<FileText size={26} strokeWidth={1.5} />}
              title="Aún no hay listas de cotización"
              description="Crea una cotización para comparar proveedores y organizar una lista de compra."
              action={<a href="/cotizar" className="btn-swiss-primary" style={{ textDecoration: "none" }}>Crear mi primera cotización</a>}
            />
          ) : (
            listasRecientes.map((lista, i) => {
              const estado = lista.aprobacion_estado;
              const estadoUI = estado === "aprobado" ? "aprobada" : estado === "aprobado_con_observaciones" ? "en_curso" : estado === "rechazado" ? "rechazada" : "cotizando";
              const estadoLabel = estado === "aprobado" ? "Aprobada" : estado === "aprobado_con_observaciones" ? "Aprobada con modificaciones" : estado === "rechazado" ? "Rechazada" : estado === "pendiente" ? "Esperando aprobación" : "Sin enviar";

              return (
                <Link key={lista.id} href={`/listas/${lista.id}`}
                  style={{
                    display: "grid",
                    gridTemplateColumns: "1fr 90px 110px 110px 170px 120px 76px",
                    gap: 10,
                    padding: "12px 16px",
                    borderBottom: i < listasRecientes.length - 1 ? "1px solid var(--n-100)" : "none",
                    alignItems: "center",
                    textDecoration: "none", color: "inherit",
                    background: i % 2 ? "var(--canvas)" : undefined,
                  }}>
                  <div style={{ minWidth: 0 }}>
                    <div style={{ fontSize: 14, fontWeight: 600, color: "var(--n-900)" }}>{lista.nombre}</div>
                    <div style={{ fontSize: 12, color: "var(--n-500)", fontFamily: "var(--font-mono)" }}>LIST-{lista.id.slice(-4).toUpperCase()}</div>
                  </div>
                  <div style={{ fontSize: 14, color: "var(--n-700)", fontFamily: "var(--font-mono)" }}>{lista.n_items}</div>
                  <div style={{ fontSize: 14, color: "var(--n-700)", fontFamily: "var(--font-mono)" }}>{lista.n_comparados}/{lista.n_items}</div>
                  <div style={{ fontSize: 14, color: "var(--n-700)", fontFamily: "var(--font-mono)" }}>{lista.n_definitivos}/{lista.n_items}</div>
                  <div><Badge status={estadoUI}>{estadoLabel}</Badge></div>
                  <div style={{ fontSize: 14, fontWeight: 600, color: "var(--n-900)", fontFamily: "var(--font-mono)", fontVariantNumeric: "tabular-nums" }}>
                    {lista.monto_total ? fmtCLP(lista.monto_total) : "—"}
                  </div>
                  <div style={{ fontSize: 12.5, color: "var(--n-500)" }}>{lista.created_at ? fmtFecha(lista.created_at) : "—"}</div>
                </Link>
              );
            })
          )}
        </div>
      </div>

      {/* Gmail integration (compacto, al final) */}
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
              {gmailConectado
                ? "Gmail conectado y listo para enviar cotizaciones."
                : "Conecta Gmail para enviar cotizaciones automáticamente."}
            </div>
          </div>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            {!gmailConectado && <a href={`${API_URL}/api/gmail/auth?user_id=${user.id}`} className="btn-swiss-secondary" style={{ textDecoration: "none" }}>
              Conectar Gmail
            </a>}
            <Link href="/settings?section=autorizaciones" className="btn-swiss-secondary" style={{ textDecoration: "none" }}>
              Editar ciclo de autorizaciones
            </Link>
          </div>
        </div>
    </div>
  );
}
