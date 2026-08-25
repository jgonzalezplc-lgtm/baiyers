"use client";
import { useEffect, useState } from "react";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard, PlusCircle, ListChecks, Building2,
  ScrollText, Receipt, FolderKanban,
  Mail, Plug, Settings, LogOut, Menu, X,
  type LucideIcon,
} from "lucide-react";
import { ThemeToggle } from "@/components/ui";
import OnboardingFloating from "./OnboardingFloating";
import NotificationBell from "./NotificationBell";

interface NavLink { href: string; label: string; icon: LucideIcon }

const NAV: { section: string; links: NavLink[] }[] = [
  {
    section: "Principal",
    links: [
      { href: "/dashboard", label: "Inicio", icon: LayoutDashboard },
      { href: "/cotizar", label: "Nueva cotización", icon: PlusCircle },
      { href: "/listas", label: "Cotizaciones", icon: ListChecks },
    ],
  },
  {
    section: "Gestión",
    links: [
      { href: "/proveedores", label: "Proveedores", icon: Building2 },
      { href: "/conversaciones", label: "Conversaciones", icon: Mail },
      { href: "/oc", label: "Órdenes de compra", icon: ScrollText },
      { href: "/facturas", label: "Facturas", icon: Receipt },
      { href: "/proyectos", label: "Proyectos", icon: FolderKanban },
    ],
  },
  {
    section: "Sistema",
    links: [
      { href: "/integraciones", label: "MCP", icon: Plug },
      { href: "/settings", label: "Configuración", icon: Settings },
    ],
  },
];

const BREADCRUMB: Record<string, string> = {
  "/dashboard": "Inicio",
  "/cotizar": "Nueva cotización",
  "/cotizaciones": "Cotizaciones",
  "/listas": "Cotizaciones",
  "/proveedores": "Proveedores",
  "/conversaciones": "Conversaciones",
  "/estadisticas": "Estadísticas",
  "/oc": "Órdenes de compra",
  "/facturas": "Facturas",
  "/proyectos": "Proyectos",
  "/calendario": "Calendario",
  "/recurrencias": "Recurrencias",
  "/reportes": "Reportes",
  "/chat": "Chat IA",
  "/integraciones": "MCP",
  "/developers": "API",
  "/settings": "Configuración",
};

const RAIL = 66;
const EXPANDED = 224;

interface AppShellProps {
  children: React.ReactNode;
  empresa: string;
  planLabel: string;
  planLimitLabel: string;
  userId: string;
  perfilIncompleto?: boolean;
}

export default function AppShell({ children, empresa, planLabel, planLimitLabel, userId, perfilIncompleto }: AppShellProps) {
  const pathname = usePathname();
  const [expandido, setExpandido] = useState(false);
  const [drawerAbierto, setDrawerAbierto] = useState(false);
  const [esMobile, setEsMobile] = useState(false);

  const [breadcrumbOverride, setBreadcrumbOverride] = useState<string | null>(null);

  const breadcrumbBase = BREADCRUMB[pathname]
    ?? BREADCRUMB[Object.keys(BREADCRUMB).find(k => pathname.startsWith(k) && k !== "/") ?? ""]
    ?? "";
  const breadcrumb = breadcrumbOverride || breadcrumbBase;

  useEffect(() => {
    const check = () => setEsMobile(window.innerWidth < 860);
    check();
    window.addEventListener("resize", check);
    return () => window.removeEventListener("resize", check);
  }, []);

  // Páginas pueden sobrescribir el breadcrumb (ej: nombre de la lista en cotizar)
  useEffect(() => {
    const h = (e: Event) => setBreadcrumbOverride((e as CustomEvent<string | null>).detail || null);
    window.addEventListener("baiyer:breadcrumb", h);
    return () => window.removeEventListener("baiyer:breadcrumb", h);
  }, []);

  useEffect(() => { setDrawerAbierto(false); setBreadcrumbOverride(null); }, [pathname]);

  // En mobile el riel se reemplaza por un drawer; en desktop se expande al hover
  const abierto = esMobile ? drawerAbierto : expandido;
  const anchoVisible = esMobile ? 0 : RAIL;

  const sidebar = (
    <aside
      onMouseEnter={() => !esMobile && setExpandido(true)}
      onMouseLeave={() => !esMobile && setExpandido(false)}
      style={{
        position: "fixed", top: 0, left: 0, zIndex: 60,
        height: "100vh",
        width: abierto ? EXPANDED : RAIL,
        transform: esMobile && !drawerAbierto ? `translateX(-${EXPANDED}px)` : "translateX(0)",
        background: "var(--surface)",
        borderRight: "1px solid var(--n-200)",
        boxShadow: abierto ? "var(--shadow-pop)" : "none",
        display: "flex", flexDirection: "column",
        overflowX: "hidden", overflowY: "auto",
        transition: "width .3s cubic-bezier(.4,0,.2,1), transform .3s cubic-bezier(.4,0,.2,1), box-shadow .3s ease",
      }}
    >
      {/* Marca */}
      <div style={{ padding: "18px 0 16px", display: "flex", alignItems: "center", gap: 10, paddingLeft: 20, minHeight: 66 }}>
        <span style={{
          width: 26, height: 26, borderRadius: 7, flexShrink: 0,
          background: "var(--brand)", color: "#fff",
          display: "inline-flex", alignItems: "center", justifyContent: "center",
          fontSize: 14, fontWeight: 700,
        }}>B</span>
        <div style={{
          opacity: abierto ? 1 : 0,
          transform: abierto ? "translateX(0)" : "translateX(-6px)",
          transition: "opacity .2s ease, transform .2s ease",
          whiteSpace: "nowrap",
        }}>
          <div style={{ fontSize: 15, fontWeight: 600, color: "var(--n-900)", letterSpacing: "-0.015em" }}>Baiyer</div>
          <div style={{ fontSize: 12, color: "var(--n-500)" }}>Plan {planLabel} · {planLimitLabel}/mes</div>
        </div>
      </div>

      {/* Navegación */}
      <nav style={{ flex: 1, padding: "0 12px" }}>
        {NAV.map(({ section, links }) => (
          <div key={section} style={{ marginBottom: 14 }}>
            <div style={{
              fontSize: 11, fontWeight: 600, color: "var(--n-500)",
              padding: "0 10px", marginBottom: 4, height: 16,
              opacity: abierto ? 1 : 0,
              transition: "opacity .2s ease",
              whiteSpace: "nowrap", overflow: "hidden",
            }}>
              {section}
            </div>
            {links.map(({ href, label, icon: Icon }) => {
              const active = pathname === href || (href !== "/dashboard" && pathname.startsWith(href));
              const alerta = href === "/settings" && perfilIncompleto && !active;
              return (
                <a key={href} href={href} title={abierto ? undefined : label} style={{
                  display: "flex", alignItems: "center", gap: 12,
                  padding: "9px 10px", marginBottom: 2,
                  borderRadius: "var(--r-md)",
                  color: active ? "var(--brand)" : alerta ? "var(--brand)" : "var(--n-600)",
                  background: active ? "var(--brand-50)" : "transparent",
                  fontWeight: active ? 600 : 500,
                  fontSize: 14, textDecoration: "none",
                  whiteSpace: "nowrap",
                  transition: "background .15s ease, color .15s ease",
                }}>
                  <span style={{ position: "relative", display: "inline-flex", flexShrink: 0 }}>
                    <Icon size={19} strokeWidth={1.75} />
                    {alerta && (
                      <span style={{
                        position: "absolute", top: -2, right: -2,
                        width: 7, height: 7, borderRadius: "50%",
                        background: "var(--brand)", border: "1.5px solid var(--surface)",
                      }} />
                    )}
                  </span>
                  <span style={{
                    opacity: abierto ? 1 : 0,
                    transform: abierto ? "translateX(0)" : "translateX(-6px)",
                    transition: "opacity .2s ease, transform .2s ease",
                    overflow: "hidden",
                  }}>{label}</span>
                </a>
              );
            })}
          </div>
        ))}
      </nav>

      {/* Pie */}
      <div style={{ borderTop: "1px solid var(--n-200)", padding: "10px 12px" }}>
        <div style={{ padding: "0 2px" }}><ThemeToggle compact={!abierto} /></div>
        {abierto && empresa && (
          <div style={{
            fontSize: 12, color: "var(--n-500)", padding: "6px 10px 2px",
            whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis",
          }}>{empresa}</div>
        )}
        <form action="/auth/signout" method="post">
          <button title={abierto ? undefined : "Salir"} style={{
            display: "flex", alignItems: "center", gap: 12,
            width: "100%", padding: "9px 10px", borderRadius: "var(--r-md)",
            background: "none", border: "none", cursor: "pointer",
            color: "var(--n-600)", fontSize: 14, fontFamily: "inherit",
            whiteSpace: "nowrap",
          }}>
            <LogOut size={19} strokeWidth={1.75} style={{ flexShrink: 0 }} />
            <span style={{
              opacity: abierto ? 1 : 0,
              transition: "opacity .2s ease",
              overflow: "hidden",
            }}>Salir</span>
          </button>
        </form>
      </div>
    </aside>
  );

  return (
    <div style={{ minHeight: "100vh", background: "var(--canvas)" }}>
      {sidebar}

      {/* Backdrop del drawer en mobile */}
      {esMobile && drawerAbierto && (
        <div
          onClick={() => setDrawerAbierto(false)}
          style={{ position: "fixed", inset: 0, zIndex: 55, background: "rgba(33,29,24,.4)" }}
        />
      )}

      {/* Contenido, el margen sólo reserva el riel, así el hover no genera reflow */}
      <div style={{ marginLeft: anchoVisible, display: "flex", flexDirection: "column", minHeight: "100vh", minWidth: 0 }}>
        <header style={{
          borderBottom: "1px solid var(--n-200)",
          padding: "0 24px", height: 56,
          display: "flex", justifyContent: "space-between", alignItems: "center",
          background: "var(--surface)",
          position: "sticky", top: 0, zIndex: 40,
        }}>
          <div style={{ display: "flex", alignItems: "center", gap: 12, minWidth: 0 }}>
            {esMobile && (
              <button
                onClick={() => setDrawerAbierto(v => !v)}
                aria-label="Abrir navegación"
                style={{ background: "none", border: "none", cursor: "pointer", color: "var(--n-700)", display: "inline-flex", padding: 4 }}
              >
                {drawerAbierto ? <X size={20} strokeWidth={1.75} /> : <Menu size={20} strokeWidth={1.75} />}
              </button>
            )}
            <span style={{ fontSize: 14, fontWeight: 600, color: "var(--n-900)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
              {breadcrumb || "Baiyer"}
            </span>
          </div>
          <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
            <span style={{
              fontSize: 12, fontWeight: 600, padding: "4px 11px",
              borderRadius: "var(--r-pill)",
              background: "var(--brand-50)", color: "var(--brand-700)",
            }}>{planLabel}</span>
            <NotificationBell userId={userId} />
          </div>
        </header>

        <main style={{ flex: 1, padding: 28, minWidth: 0 }}>
          {children}
        </main>
      </div>

      {perfilIncompleto && <OnboardingFloating />}
    </div>
  );
}
