import { createClient } from "@/lib/supabase/server";
import { redirect } from "next/navigation";
import Link from "next/link";
import { FileText, CheckCircle2, AlertTriangle, XCircle, Mail, ShieldCheck } from "lucide-react";
import { Card, Badge, EmptyState } from "@/components/ui";
import { fmtCLP } from "@/components/ui/tokens";

type EstadoIndicador = "ok" | "atencion" | "desconectado";

const ESTADO_INDICADOR_UI: Record<EstadoIndicador, { color: string; bg: string; Icon: typeof CheckCircle2 }> = {
  ok:            { color: "var(--success)", bg: "var(--st-aprobada-bg)",  Icon: CheckCircle2 },
  atencion:      { color: "var(--warning)", bg: "var(--st-cotizando-bg)", Icon: AlertTriangle },
  desconectado:  { color: "var(--danger)",  bg: "var(--st-rechazada-bg)", Icon: XCircle },
};

function IndicadorEstado({
  icono: Icono, titulo, estado, detalle, accion,
}: {
  icono: typeof Mail; titulo: string; estado: EstadoIndicador; detalle: string;
  accion?: { label: string; href: string };
}) {
  const { color, bg, Icon } = ESTADO_INDICADOR_UI[estado];
  return (
    <div style={{
      display: "flex", alignItems: "center", gap: 12, flex: 1, minWidth: 240,
      background: "var(--surface)", border: "1px solid var(--n-200)",
      borderRadius: "var(--r-lg)", padding: "12px 16px",
    }}>
      <span style={{
        width: 36, height: 36, borderRadius: "var(--r-md)", flexShrink: 0,
        background: bg, color, display: "inline-flex", alignItems: "center", justifyContent: "center",
      }}>
        <Icono size={18} strokeWidth={1.75} />
      </span>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <span style={{ fontSize: 13.5, fontWeight: 600, color: "var(--n-900)" }}>{titulo}</span>
          <Icon size={14} strokeWidth={2} color={color} aria-hidden />
        </div>
        <div style={{ fontSize: 12.5, color: "var(--n-600)", marginTop: 1 }}>{detalle}</div>
      </div>
      {accion && (
        <Link href={accion.href} style={{
          fontSize: 12.5, fontWeight: 500, color: "var(--brand)", textDecoration: "none",
          whiteSpace: "nowrap", flexShrink: 0,
        }}>
          {accion.label} →
        </Link>
      )}
    </div>
  );
}

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
  let accessToken: string | undefined;
  try {
    const supabase = await createClient();
    const { data } = await supabase.auth.getUser();
    user = data.user;
    const { data: sessionData } = await supabase.auth.getSession();
    accessToken = sessionData.session?.access_token;
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
    fetch(`${API_URL}/api/gmail/sync-email`, {
      method: "POST",
      headers: accessToken ? { Authorization: `Bearer ${accessToken}` } : undefined,
    }).catch(() => {});
  }

  // Fetch real stats & recent quotes — con timeout duro para que un backend
  // lento nunca cuelgue el SSR (usuario quedaba viendo la página en blanco).
  let stats = { cotizaciones: 0, proveedores: 0, ocs: 0, totalOC: 0 };
  let listasRecientes: ListaReciente[] = [];
  let gmailConectado = gmailRecienConectado;
  let gmailEstado: EstadoIndicador = gmailRecienConectado ? "ok" : "desconectado";
  let gmailDetalle = gmailRecienConectado ? "Gmail conectado y listo para enviar cotizaciones." : "Conecta Gmail para enviar cotizaciones automáticamente.";
  let autorizacionEstado: EstadoIndicador = "desconectado";
  let autorizacionDetalle = "Sin ciclo de autorización configurado.";

  const fetchConTimeout = async (url: string, ms = 5000, auth = false): Promise<Response | null> => {
    const ctrl = new AbortController();
    const t = setTimeout(() => ctrl.abort(), ms);
    try {
      return await fetch(url, {
        cache: "no-store", signal: ctrl.signal,
        headers: auth && accessToken ? { Authorization: `Bearer ${accessToken}` } : undefined,
      });
    } catch (e) {
      console.warn(`[dashboard SSR] fetch falló: ${url}`, (e as Error).message);
      return null;
    } finally {
      clearTimeout(t);
    }
  };

  try {
    const [statsRes, cotRes, gmailRes, workflowsRes] = await Promise.all([
      fetchConTimeout(`${API_URL}/api/dashboard/stats`, 5000, true),
      fetchConTimeout(`${API_URL}/api/listas?user_id=${user.id}`),
      fetchConTimeout(`${API_URL}/api/gmail/status`, 5000, true),
      fetchConTimeout(`${API_URL}/api/workflows/estado/resumen?user_id=${user.id}`),
    ]);
    if (statsRes?.ok) stats = await statsRes.json();
    if (cotRes?.ok) listasRecientes = (await cotRes.json()).slice(0, 5);
    if (gmailRes?.ok) {
      const g = await gmailRes.json();
      gmailConectado = Boolean(g.connected);
      gmailEstado = g.estado ?? (gmailConectado ? "ok" : "desconectado");
      gmailDetalle = !gmailConectado
        ? "Conecta Gmail para enviar cotizaciones automáticamente."
        : gmailEstado === "atencion"
          ? `${g.conversaciones_atencion} conversación(es) necesitan revisión manual.`
          : "Gmail conectado y sincronizando respuestas automáticamente.";
    }
    if (workflowsRes?.ok) {
      const workflow: {
        estado?: "activo" | "borrador_validado" | "borrador_pendiente" | "sin_configurar";
        nombre?: string | null;
        tiene_autorizacion?: boolean;
        errores_validacion?: number;
      } = await workflowsRes.json();
      if (workflow.estado === "activo") {
        autorizacionEstado = "ok";
        autorizacionDetalle = workflow.tiene_autorizacion
          ? `“${workflow.nombre ?? "Ciclo de compras"}” está activo y aplicará sus autorizaciones.`
          : `“${workflow.nombre ?? "Ciclo de compras"}” está activo; no requiere un aprobador independiente.`;
      } else if (workflow.estado === "borrador_validado") {
        autorizacionEstado = "atencion";
        autorizacionDetalle = `“${workflow.nombre ?? "Ciclo de compras"}” está validado; falta activarlo para aplicarlo.`;
      } else if (workflow.estado === "borrador_pendiente") {
        autorizacionEstado = "atencion";
        autorizacionDetalle = `El borrador tiene ${workflow.errores_validacion ?? 0} punto(s) por corregir antes de activarlo.`;
      } else {
        autorizacionEstado = "desconectado";
        autorizacionDetalle = "Sin ciclo de autorización configurado — las OC no pasan por aprobación.";
      }
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

      {/* Estado operativo — arriba, no escondido al final */}
      <div style={{ display: "flex", gap: 12, flexWrap: "wrap", marginBottom: 20 }}>
        <IndicadorEstado
          icono={Mail}
          titulo="Agente de correo"
          estado={gmailEstado}
          detalle={gmailDetalle}
          accion={!gmailConectado
            ? { label: "Conectar Gmail", href: `${API_URL}/api/gmail/auth?user_id=${user.id}` }
            : gmailEstado === "atencion"
              ? { label: "Revisar conversaciones", href: "/conversaciones" }
              : undefined}
        />
        <IndicadorEstado
          icono={ShieldCheck}
          titulo="Ciclo de autorizaciones"
          estado={autorizacionEstado}
          detalle={autorizacionDetalle}
          accion={{ label: "Editar ciclo", href: "/settings/autorizaciones" }}
        />
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
            gridTemplateColumns: "1fr 90px 100px 100px 190px 120px 76px",
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
              const estadoUI = estado === "aprobado" ? "aprobada" : estado === "rechazado" ? "rechazada" : "cotizando";
              const estadoLabel = estado === "aprobado" ? "Aprobada" : estado === "aprobado_con_observaciones" ? "Con observaciones" : estado === "rechazado" ? "Rechazada" : estado === "pendiente" ? "Esperando aprobación" : "Sin enviar";

              return (
                <Link key={lista.id} href={`/listas/${lista.id}`}
                  style={{
                    display: "grid",
                    gridTemplateColumns: "1fr 90px 100px 100px 190px 120px 76px",
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
                  <div style={{ minWidth: 0, overflow: "hidden" }}><Badge status={estadoUI}>{estadoLabel}</Badge></div>
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

    </div>
  );
}
