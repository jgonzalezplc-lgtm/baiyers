import Link from "next/link";

const FEATURES = [
  {
    titulo: "Identifica con IA",
    desc: "Sube una foto o describe con palabras. La IA identifica el item y genera terminos de busqueda en español, ingles y chino.",
  },
  {
    titulo: "Busca globalmente",
    desc: "Proveedores en Chile, China, Europa y USA. Precio estimado con costo de importacion CIF Santiago incluido.",
  },
  {
    titulo: "Cotiza automatico",
    desc: "El agente envia correos a los proveedores seleccionados desde tu cuenta. Parsea las respuestas y actualiza el funnel solo.",
  },
  {
    titulo: "OC instantanea",
    desc: "Elige el proveedor ganador y emite la Orden de Compra en un clic. El proveedor la confirma en linea sin necesidad de cuenta.",
  },
];

const PLANES = [
  {
    name: "Free",      price: "$0",   period: "",     cta: "Crear cuenta gratis", href: "/register",
    features: ["3 cotizaciones/mes", "Solo descripcion texto", "Busqueda Chile", "Resultados basicos"],
    highlight: false,
  },
  {
    name: "Starter",   price: "$49",  period: "/mes", cta: "Comenzar", href: "/register?plan=starter",
    features: ["20 cotizaciones/mes", "Foto + texto", "Busqueda Chile completa", "PDF / Excel"],
    highlight: false,
  },
  {
    name: "Pro",       price: "$149", period: "/mes", cta: "Comenzar", href: "/register?plan=pro",
    features: ["100 cotizaciones/mes", "Busqueda global + China", "OC automatica", "Email agent ilimitado"],
    highlight: true,
  },
  {
    name: "Business",  price: "$399", period: "/mes", cta: "Contactar", href: "/register?plan=business",
    features: ["Cotizaciones ilimitadas", "Multi-usuario", "Flujo aprobacion", "API para ERP / SAP"],
    highlight: false,
  },
];

export default function LandingPage() {
  return (
    <div style={{ minHeight: "100vh", background: "var(--bg-base)", color: "var(--text-primary)" }}>

      {/* Navbar */}
      <nav style={{
        padding: "0 24px",
        height: 52,
        display: "flex",
        justifyContent: "space-between",
        alignItems: "center",
        borderBottom: "1px solid var(--border-default)",
        maxWidth: 1100,
        margin: "0 auto",
      }}>
        <div style={{ fontSize: 13, fontWeight: 700, color: "var(--text-primary)", letterSpacing: "-0.02em" }}>
          Claria<span style={{ color: "var(--accent)", marginLeft: 1 }}>.</span>
        </div>
        <div style={{ display: "flex", gap: 20, alignItems: "center" }}>
          <Link href="/login" className="label" style={{ color: "var(--text-secondary)", textDecoration: "none" }}>
            Iniciar sesion
          </Link>
          <Link href="/cotizar" className="label" style={{ color: "var(--text-secondary)", textDecoration: "none" }}>
            Demo
          </Link>
          <Link href="/register" className="btn-swiss-primary" style={{ textDecoration: "none" }}>
            Crear cuenta
          </Link>
        </div>
      </nav>

      {/* Hero */}
      <div style={{ maxWidth: 700, margin: "0 auto", padding: "80px 24px 64px", textAlign: "center" }}>

        {/* Badge */}
        <div style={{
          display: "inline-block",
          border: "1px solid var(--border-default)",
          padding: "3px 12px",
          marginBottom: 28,
        }}>
          <span className="label" style={{ color: "var(--text-secondary)" }}>
            Plan free disponible · sin tarjeta de credito
          </span>
        </div>

        {/* Rule */}
        <div style={{ display: "flex", justifyContent: "center", marginBottom: 24 }}>
          <div className="section-rule" />
        </div>

        <h1 style={{
          fontSize: 44,
          fontWeight: 700,
          color: "var(--text-primary)",
          lineHeight: 1.1,
          margin: "0 0 20px",
          letterSpacing: "-0.03em",
        }}>
          Cotiza en minutos,<br />
          <span style={{ color: "var(--accent)" }}>no en una semana</span>
        </h1>

        <p style={{ fontSize: 14, color: "var(--text-secondary)", lineHeight: 1.7, margin: "0 0 36px" }}>
          Sube una foto o describe lo que necesitas. El sistema identifica el item, busca proveedores
          en Chile y el mundo, les envia cotizacion automatica y genera la Orden de Compra al instante.
        </p>

        <div style={{ display: "flex", gap: 12, justifyContent: "center", flexWrap: "wrap" }}>
          <Link href="/cotizar" className="btn-swiss-primary" style={{ textDecoration: "none" }}>
            Probar ahora — sin registro
          </Link>
          <Link href="/register" className="btn-swiss-secondary" style={{ textDecoration: "none" }}>
            Crear cuenta gratis
          </Link>
        </div>
      </div>

      {/* Features */}
      <div style={{ maxWidth: 1000, margin: "0 auto", padding: "0 24px 80px" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 32 }}>
          <div className="section-rule" />
          <span className="label">Como funciona</span>
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: 0, border: "1px solid var(--border-default)" }}>
          {FEATURES.map((f, i) => (
            <div key={i} style={{
              padding: "24px 20px",
              borderRight: i < FEATURES.length - 1 ? "1px solid var(--border-default)" : "none",
              background: "var(--bg-surface)",
            }}>
              <div className="label" style={{ marginBottom: 8, color: "var(--accent)" }}>
                0{i + 1}
              </div>
              <div style={{ fontSize: 13, fontWeight: 700, color: "var(--text-primary)", marginBottom: 8, lineHeight: 1.3 }}>
                {f.titulo}
              </div>
              <div style={{ fontSize: 11, color: "var(--text-secondary)", lineHeight: 1.7 }}>
                {f.desc}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Pricing */}
      <div style={{ maxWidth: 1000, margin: "0 auto", padding: "0 24px 80px" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 8 }}>
          <div className="section-rule" />
          <span className="label">Precios</span>
        </div>
        <h2 style={{ fontSize: 22, fontWeight: 700, color: "var(--text-primary)", margin: "0 0 8px" }}>
          Empieza gratis, escala cuando necesites
        </h2>
        <p className="label" style={{ marginBottom: 32, color: "var(--text-muted)" }}>
          Sin tarjeta de credito para el plan free
        </p>

        <div style={{ display: "grid", gridTemplateColumns: "repeat(4,1fr)", border: "1px solid var(--border-default)" }}>
          {PLANES.map((p, i) => (
            <div key={i} style={{
              padding: "24px 20px",
              borderRight: i < PLANES.length - 1 ? "1px solid var(--border-default)" : "none",
              background: p.highlight ? "var(--bg-inverse)" : "var(--bg-surface)",
              color: p.highlight ? "var(--text-inverse)" : "var(--text-primary)",
              position: "relative",
            }}>
              {p.highlight && (
                <div className="label" style={{
                  position: "absolute", top: 12, right: 12,
                  color: "var(--accent)", background: "var(--accent-muted)",
                  padding: "2px 8px", border: "1px solid var(--accent)",
                }}>
                  Popular
                </div>
              )}
              <div className="label" style={{ marginBottom: 12, color: p.highlight ? "var(--accent)" : "var(--text-muted)" }}>
                {p.name}
              </div>
              <div style={{ fontSize: 28, fontWeight: 700, marginBottom: 2 }}>
                {p.price}
                <span style={{ fontSize: 11, fontWeight: 400, color: p.highlight ? "#9a9a9a" : "var(--text-muted)" }}>
                  {p.period}
                </span>
              </div>
              <div style={{ borderTop: `1px solid ${p.highlight ? "#2e2e2e" : "var(--border-subtle)"}`, margin: "16px 0 12px", paddingTop: 12 }}>
                {p.features.map((f, j) => (
                  <div key={j} style={{
                    fontSize: 10,
                    color: p.highlight ? "#9a9a9a" : "var(--text-secondary)",
                    padding: "4px 0",
                    display: "flex", gap: 6, alignItems: "flex-start",
                  }}>
                    <span style={{ color: "var(--accent)", flexShrink: 0 }}>—</span>
                    {f}
                  </div>
                ))}
              </div>
              <Link
                href={p.href}
                style={{
                  display: "block",
                  textAlign: "center",
                  textDecoration: "none",
                  padding: "9px 16px",
                  fontSize: 10,
                  fontWeight: 500,
                  letterSpacing: "0.12em",
                  textTransform: "uppercase",
                  border: `1px solid ${p.highlight ? "var(--accent)" : "var(--border-strong)"}`,
                  background: p.highlight ? "var(--accent)" : "transparent",
                  color: p.highlight ? "#fff" : "var(--text-primary)",
                }}
              >
                {p.cta}
              </Link>
            </div>
          ))}
        </div>
        <p className="label" style={{ marginTop: 16, color: "var(--text-muted)" }}>
          Precios en USD · Cobros en CLP via Flow Chile · Cancela cuando quieras
        </p>
      </div>

      {/* Footer */}
      <footer style={{
        borderTop: "1px solid var(--border-default)",
        padding: "20px 24px",
        textAlign: "center",
      }}>
        <span className="label" style={{ color: "var(--text-muted)" }}>
          Claria · Santiago, Chile · hola@claria.cc
        </span>
      </footer>
    </div>
  );
}
