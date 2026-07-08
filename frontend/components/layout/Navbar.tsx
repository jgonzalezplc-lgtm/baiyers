import Link from "next/link";

export default function Navbar() {
  return (
    <nav style={{ padding: "16px 24px", display: "flex", justifyContent: "space-between", alignItems: "center", borderBottom: "1px solid #1a1a2e" }}>
      <Link href="/" style={{ fontSize: 13, fontWeight: 800, color: "#6366f1", letterSpacing: "-0.02em", textDecoration: "none" }}>
        cotizador<span style={{ color: "#f1f5f9" }}>.ai</span>
      </Link>
      <div style={{ display: "flex", gap: 16, alignItems: "center" }}>
        <Link href="/login" style={{ fontSize: 11, color: "#475569", textDecoration: "none" }}>Iniciar sesion</Link>
        <Link href="/register" style={{ fontSize: 11, background: "#6366f1", color: "#fff", padding: "8px 16px", borderRadius: 6, textDecoration: "none", fontWeight: 700 }}>
          Probar gratis
        </Link>
      </div>
    </nav>
  );
}
