"use client";
import { usePathname } from "next/navigation";

const NAV = [
  {
    section: "PRINCIPAL",
    links: [
      { href: "/dashboard", label: "Dashboard" },
      { href: "/cotizar", label: "Nueva cotización" },
      { href: "/cotizaciones", label: "Cotizaciones" },
      { href: "/listas", label: "Listas de cotización" },
    ],
  },
  {
    section: "GESTIÓN",
    links: [
      { href: "/proveedores", label: "Proveedores" },
      { href: "/estadisticas", label: "Estadísticas" },
      { href: "/oc", label: "OC emitidas" },
      { href: "/facturas", label: "Facturas" },
      { href: "/proyectos", label: "Proyectos" },
      { href: "/calendario", label: "Calendario" },
      { href: "/recurrencias", label: "Recurrencias" },
      { href: "/reportes", label: "Reportes" },
    ],
  },
  {
    section: "SISTEMA",
    links: [
      { href: "/chat", label: "Chat IA" },
      { href: "/integraciones", label: "MCP" },
      { href: "/developers", label: "API" },
      { href: "/settings", label: "Configuración" },
    ],
  },
];

const BREADCRUMB: Record<string, string> = {
  "/dashboard": "DASHBOARD",
  "/cotizar": "NUEVA COTIZACIÓN",
  "/cotizaciones": "COTIZACIONES",
  "/proveedores": "PROVEEDORES",
  "/estadisticas": "ESTADÍSTICAS",
  "/oc": "OC EMITIDAS",
  "/facturas": "FACTURAS",
  "/proyectos": "PROYECTOS",
  "/calendario": "CALENDARIO",
  "/recurrencias": "RECURRENCIAS",
  "/reportes": "REPORTES",
  "/chat": "CHAT IA",
  "/integraciones": "MCP",
  "/developers": "API",
  "/settings": "CONFIGURACIÓN",
};

interface AppShellProps {
  children: React.ReactNode;
  empresa: string;
  planLabel: string;
  planLimitLabel: string;
  userId: string;
}

export default function AppShell({ children, empresa, planLabel, planLimitLabel, userId }: AppShellProps) {
  const pathname = usePathname();
  const breadcrumb = BREADCRUMB[pathname] ?? BREADCRUMB[Object.keys(BREADCRUMB).find(k => pathname.startsWith(k) && k !== "/") ?? ""] ?? "";

  return (
    <div style={{ display: "flex", minHeight: "100vh", background: "var(--bg-base)" }}>
      {/* Sidebar */}
      <aside style={{
        width: 208,
        minHeight: "100vh",
        background: "var(--bg-surface)",
        borderRight: "1px solid var(--border-default)",
        display: "flex",
        flexDirection: "column",
        flexShrink: 0,
        position: "sticky",
        top: 0,
        height: "100vh",
        overflowY: "auto",
      }}>
        {/* Logo */}
        <div style={{ padding: "20px 20px 18px" }}>
          <div style={{ fontSize: 15, fontWeight: 700, color: "var(--text-primary)", letterSpacing: "-0.02em" }}>
            cotizador<span style={{ color: "var(--accent)" }}>.ai</span>
          </div>
          <div style={{ fontSize: 10, color: "var(--text-muted)", marginTop: 2 }}>
            Plan {planLabel} · {planLimitLabel}/mes
          </div>
        </div>

        {/* Nav */}
        <nav style={{ flex: 1, padding: "0 10px" }}>
          {NAV.map(({ section, links }) => (
            <div key={section} style={{ marginBottom: 18 }}>
              <div style={{
                fontSize: 9,
                fontWeight: 700,
                color: "var(--text-muted)",
                letterSpacing: "0.08em",
                padding: "0 10px",
                marginBottom: 4,
              }}>
                {section}
              </div>
              {links.map(({ href, label }) => {
                const active = pathname === href || (href !== "/dashboard" && pathname.startsWith(href));
                return (
                  <a key={href} href={href} style={{
                    display: "block",
                    padding: "6px 10px",
                    fontSize: 12,
                    fontWeight: active ? 700 : 400,
                    color: active ? "var(--accent)" : "var(--text-secondary)",
                    textDecoration: "none",
                    borderRadius: 2,
                    marginBottom: 1,
                    background: active ? "var(--accent-muted)" : "transparent",
                  }}>
                    {label}
                  </a>
                );
              })}
            </div>
          ))}
        </nav>

        {/* Footer */}
        <div style={{ padding: "14px 20px", borderTop: "1px solid var(--border-default)" }}>
          <div style={{ marginBottom: 10 }}>
            <div style={{ fontSize: 9, fontWeight: 700, color: "var(--text-muted)", letterSpacing: "0.08em", marginBottom: 6 }}>
              VARIACIÓN DE TEMA
            </div>
            <div style={{ display: "flex", gap: 5 }}>
              {["A · STARK", "B · WARM"].map((t) => (
                <span key={t} style={{
                  fontSize: 9,
                  fontWeight: 700,
                  padding: "3px 8px",
                  border: "1px solid var(--border-default)",
                  color: "var(--text-muted)",
                  cursor: "pointer",
                }}>{t}</span>
              ))}
            </div>
          </div>
          <div style={{ fontSize: 10, color: "var(--text-muted)", marginBottom: 5, wordBreak: "break-all" }}>{empresa}</div>
          <form action="/auth/signout" method="post">
            <button style={{
              background: "none",
              border: "none",
              padding: 0,
              fontSize: 11,
              color: "var(--text-muted)",
              cursor: "pointer",
              fontFamily: "inherit",
              textDecoration: "underline",
            }}>Salir</button>
          </form>
        </div>
      </aside>

      {/* Main */}
      <div style={{ flex: 1, display: "flex", flexDirection: "column", minWidth: 0 }}>
        {/* Top bar */}
        <header style={{
          borderBottom: "1px solid var(--border-default)",
          padding: "11px 32px",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          background: "var(--bg-surface)",
          position: "sticky",
          top: 0,
          zIndex: 10,
        }}>
          <div style={{ fontSize: 10, color: "var(--text-muted)", letterSpacing: "0.07em", fontWeight: 700 }}>
            COTIZADOR.AI{breadcrumb ? ` · ${breadcrumb}` : ""}
          </div>
          <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
            <span style={{
              fontSize: 9,
              fontWeight: 700,
              letterSpacing: "0.07em",
              color: "var(--accent)",
              border: "1px solid var(--accent)",
              padding: "3px 8px",
            }}>
              {planLabel.toUpperCase()}
            </span>
            <a href="/cotizar" style={{
              fontSize: 11,
              fontWeight: 700,
              letterSpacing: "0.04em",
              background: "var(--accent)",
              color: "var(--accent-text)",
              border: "1px solid var(--accent)",
              padding: "7px 14px",
              textDecoration: "none",
            }}>
              + NUEVA COTIZACIÓN
            </a>
          </div>
        </header>

        {/* Page content */}
        <main style={{ flex: 1, padding: "32px" }}>
          {children}
        </main>
      </div>
    </div>
  );
}
