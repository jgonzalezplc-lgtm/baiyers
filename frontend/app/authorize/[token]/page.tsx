"use client";
import { useEffect, useState } from "react";
import { useParams, useSearchParams } from "next/navigation";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface Solicitud {
  id: string;
  referencia: string;
  resumen: Record<string, unknown>;
  estado: string;
  aprobador_email: string | null;
  expira_at: string | null;
  created_at: string;
}

export default function AuthorizePage() {
  const params = useParams();
  const searchParams = useSearchParams();
  const token = params.token as string;
  const decisionAuto = searchParams.get("decision"); // aprobar | rechazar | null

  const [sol, setSol] = useState<Solicitud | null>(null);
  const [error, setError] = useState("");
  const [resultado, setResultado] = useState("");
  const [enviando, setEnviando] = useState(false);

  useEffect(() => {
    fetch(`${API_URL}/api/aprobaciones/token/${token}`)
      .then(async (r) => {
        if (!r.ok) throw new Error((await r.json()).detail ?? "Error");
        return r.json();
      })
      .then(setSol)
      .catch((e) => setError(e.message));
  }, [token]);

  const decidir = async (decision: "aprobar" | "rechazar") => {
    setEnviando(true);
    try {
      const r = await fetch(`${API_URL}/api/aprobaciones/token/${token}/decidir`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ decision }),
      });
      const d = await r.json();
      if (!r.ok) throw new Error(d.detail ?? "Error");
      setResultado(d.estado);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Error");
    } finally {
      setEnviando(false);
    }
  };

  const resumenEntries = sol ? Object.entries(sol.resumen ?? {}) : [];

  return (
    <div style={{ minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center", background: "var(--bg-base)", padding: 24 }}>
      <div style={{ width: 480, maxWidth: "100%", border: "1px solid var(--border-strong)", background: "var(--bg-elevated)", padding: 32 }}>
        <div className="label" style={{ color: "var(--text-accent)", fontWeight: 800, marginBottom: 4 }}>CLARIA</div>
        <h1 style={{ fontSize: 18, fontWeight: 800, margin: "0 0 16px" }}>Autorización de compra</h1>

        {error && <div className="label" style={{ color: "var(--text-error)", padding: 12, background: "var(--fill-error)" }}>{error}</div>}

        {!error && !sol && <div className="label" style={{ color: "var(--text-muted)" }}>Cargando…</div>}

        {sol && !resultado && (
          <>
            {resumenEntries.length > 0 && (
              <div style={{ border: "1px solid var(--border-default)", padding: 14, marginBottom: 16 }}>
                {resumenEntries.map(([k, v]) => (
                  <div key={k} style={{ display: "flex", justifyContent: "space-between", padding: "3px 0", fontSize: 12 }}>
                    <span className="label" style={{ color: "var(--text-muted)" }}>{k.replace(/_/g, " ")}</span>
                    <span style={{ fontWeight: 700, textAlign: "right" }}>{String(v)}</span>
                  </div>
                ))}
              </div>
            )}

            {sol.estado !== "pendiente" ? (
              <div className="label" style={{ padding: 12, background: "var(--bg-surface)" }}>
                Esta solicitud ya está <strong>{sol.estado}</strong>.
              </div>
            ) : (
              <div style={{ display: "flex", gap: 10 }}>
                <button className="btn-swiss-primary" style={{ flex: 1, padding: "12px 0", fontSize: 13 }}
                  disabled={enviando} onClick={() => decidir("aprobar")}>
                  ✓ Aprobar
                </button>
                <button className="btn-swiss-secondary" style={{ flex: 1, padding: "12px 0", fontSize: 13 }}
                  disabled={enviando} onClick={() => decidir("rechazar")}>
                  ✗ Rechazar
                </button>
              </div>
            )}
            {decisionAuto && sol.estado === "pendiente" && (
              <div className="label" style={{ color: "var(--text-muted)", marginTop: 10 }}>
                Llegaste desde el enlace de {decisionAuto === "aprobar" ? "aprobación" : "rechazo"} — confirma con el botón.
              </div>
            )}
          </>
        )}

        {resultado && (
          <div style={{ padding: 20, textAlign: "center", background: resultado === "aprobado" ? "var(--fill-success)" : "var(--fill-error)" }}>
            <div style={{ fontSize: 24 }}>{resultado === "aprobado" ? "✅" : "❌"}</div>
            <div style={{ fontSize: 14, fontWeight: 800, marginTop: 6 }}>
              Solicitud {resultado}
            </div>
            <div className="label" style={{ color: "var(--text-muted)", marginTop: 4 }}>Ya puedes cerrar esta ventana.</div>
          </div>
        )}
      </div>
    </div>
  );
}
