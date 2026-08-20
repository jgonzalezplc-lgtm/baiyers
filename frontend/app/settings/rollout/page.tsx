"use client";

/**
 * Operación del rollout del workflow unificado (Fase G).
 *
 * Hasta acá el modo sólo se cambiaba por curl contra
 * PUT /api/workflows/rollout/estado, lo que hacía que el rollback —justo la
 * maniobra que hay que poder ejecutar rápido y bajo presión— dependiera de
 * tener a mano un JWT y el comando correcto. Ver WORKFLOW_ROLLOUT_RUNBOOK.md.
 *
 * La página no decide nada por su cuenta: el backend valida el workflow activo
 * antes de permitir `unified` y exige es_admin. Acá sólo se muestran las
 * métricas que permiten decidir y se pide una confirmación explícita.
 */

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { ArrowLeft, AlertTriangle, CheckCircle2, RotateCcw } from "lucide-react";
import { BtnPrimary, BtnSecondary, Card, Input, PageHeader, SkeletonBox } from "@/components/ui";
import { authFetch } from "@/lib/authFetch";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface Resumen {
  instancias: number;
  activas: number;
  completadas: number;
  eventos: number;
  loops_agotados: number;
  envios_inciertos: number;
}

interface EstadoRollout {
  rollout: {
    execution_mode: string;
    change_reason?: string | null;
    changed_at?: string | null;
    migration_pending?: boolean;
  };
  legacy: Resumen;
  unified: Resumen;
  nota?: string;
}

const METRICAS: { key: keyof Resumen; label: string; alertaSiPositivo?: boolean }[] = [
  { key: "instancias", label: "Instancias" },
  { key: "activas", label: "Activas" },
  { key: "completadas", label: "Completadas" },
  { key: "eventos", label: "Eventos" },
  { key: "loops_agotados", label: "Loops agotados", alertaSiPositivo: true },
  { key: "envios_inciertos", label: "Envíos inciertos", alertaSiPositivo: true },
];

export default function RolloutPage() {
  const [estado, setEstado] = useState<EstadoRollout | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [confirmacion, setConfirmacion] = useState("");
  const [aplicando, setAplicando] = useState(false);
  const [motivo, setMotivo] = useState("");

  const cargar = useCallback(async () => {
    setError(null);
    try {
      const res = await authFetch(`${API_URL}/api/workflows/rollout/estado`);
      if (!res.ok) throw new Error(`El servidor respondió ${res.status}`);
      setEstado(await res.json());
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo cargar el estado");
    }
    setLoading(false);
  }, []);

  useEffect(() => { void cargar(); }, [cargar]);

  const modo = estado?.rollout?.execution_mode ?? "legacy";
  const esUnified = modo === "unified";
  // `compatibility` no es un modo que alguien elija: lo devuelve el backend
  // cuando la tabla workflow_rollout_settings no existe (migración 045 sin
  // aplicar). Se muestra distinto porque significa "no sé", no "está activo".
  const esCompatibility = modo === "compatibility";

  const destino = esUnified ? "legacy" : "unified";
  const palabraConfirmacion = destino.toUpperCase();
  const puedeAplicar = confirmacion.trim().toUpperCase() === palabraConfirmacion && !aplicando;

  async function aplicarCambio() {
    setAplicando(true);
    setError(null);
    try {
      const res = await authFetch(`${API_URL}/api/workflows/rollout/estado`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ execution_mode: destino, reason: motivo.trim() }),
      });
      if (!res.ok) {
        const detalle = await res.json().catch(() => null);
        throw new Error(detalle?.detail || `El servidor respondió ${res.status}`);
      }
      setConfirmacion("");
      setMotivo("");
      await cargar();
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo cambiar el modo");
    }
    setAplicando(false);
  }

  return (
    <>
      <PageHeader
        eyebrow="Fase G"
        title="Rollout del ciclo unificado"
        subtitle="Qué motor gobierna las compras nuevas. El cambio no reescribe instancias ya iniciadas."
      />
      <div style={{ maxWidth: 780, margin: "0 auto", padding: "0 20px 60px" }}>
        <Link href="/settings" style={{
          display: "inline-flex", alignItems: "center", gap: 6, marginBottom: 18,
          fontSize: 13, color: "var(--n-600)", textDecoration: "none",
        }}>
          <ArrowLeft size={15} /> Volver a configuración
        </Link>

        {loading ? <SkeletonBox height={280} /> : error && !estado ? (
          <Card padding={20}>
            <div style={{ color: "var(--danger)", fontSize: 13.5 }}>{error}</div>
            <BtnSecondary onClick={() => void cargar()} style={{ marginTop: 12 }}>Reintentar</BtnSecondary>
          </Card>
        ) : estado && (
          <>
            {/* Modo actual */}
            <Card padding={20} style={{ display: "flex", alignItems: "center", gap: 16 }}>
              <div style={{
                width: 44, height: 44, flexShrink: 0, borderRadius: "var(--r-md)",
                display: "flex", alignItems: "center", justifyContent: "center",
                background: esUnified ? "var(--brand-50)" : "var(--n-100)",
                color: esUnified ? "var(--brand)" : "var(--n-500)",
              }}>
                {esUnified ? <CheckCircle2 size={22} strokeWidth={1.75} /> : <RotateCcw size={22} strokeWidth={1.75} />}
              </div>
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 15, fontWeight: 600, color: "var(--n-900)" }}>
                  Compras nuevas: <strong>{modo}</strong>
                </div>
                <div style={{ fontSize: 13, color: "var(--n-600)", marginTop: 2 }}>
                  {estado.rollout.change_reason || "Sin motivo registrado"}
                  {estado.rollout.changed_at && ` · ${new Date(estado.rollout.changed_at).toLocaleString("es-CL")}`}
                </div>
              </div>
            </Card>

            {esCompatibility && (
              <div style={{
                marginTop: 14, padding: "12px 14px", fontSize: 13.5, lineHeight: 1.6,
                background: "var(--st-cotizando-bg)", color: "var(--st-cotizando-fg)",
                border: "1px solid rgba(124,92,18,.25)", borderRadius: "var(--r-md)",
                display: "flex", gap: 10, alignItems: "flex-start",
              }}>
                <AlertTriangle size={17} strokeWidth={1.75} style={{ flexShrink: 0, marginTop: 1 }} />
                <span>
                  El backend reporta <strong>compatibility</strong>, que significa que la tabla
                  <code> workflow_rollout_settings </code> no existe — la migración 045 no está aplicada.
                  En ese estado el motor unificado queda habilitado por el opt-in temporal, sin control
                  de rollout. <strong>No hagas el checkpoint hasta resolverlo.</strong>
                </span>
              </div>
            )}

            {/* Comparativa */}
            <Card padding={0} style={{ marginTop: 16, overflow: "hidden" }}>
              <div style={{ padding: "14px 18px", borderBottom: "1px solid var(--n-200)" }}>
                <div style={{ fontSize: 14, fontWeight: 600, color: "var(--n-900)" }}>Comparativa por dueño</div>
                <div style={{ fontSize: 12.5, color: "var(--n-600)", marginTop: 2 }}>
                  Guardá estos números antes de habilitar: son el baseline contra el que se juzga el ciclo.
                </div>
              </div>
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13.5 }}>
                <thead>
                  <tr style={{ background: "var(--surface-2)" }}>
                    <th style={{ textAlign: "left", padding: "9px 18px", fontWeight: 600, color: "var(--n-600)" }}>Métrica</th>
                    <th style={{ textAlign: "right", padding: "9px 18px", fontWeight: 600, color: "var(--n-600)" }}>legacy</th>
                    <th style={{ textAlign: "right", padding: "9px 18px", fontWeight: 600, color: "var(--n-600)" }}>unified</th>
                  </tr>
                </thead>
                <tbody>
                  {METRICAS.map(({ key, label, alertaSiPositivo }) => {
                    const l = estado.legacy[key], u = estado.unified[key];
                    const alerta = (v: number) => alertaSiPositivo && v > 0;
                    return (
                      <tr key={key} style={{ borderTop: "1px solid var(--n-200)" }}>
                        <td style={{ padding: "9px 18px", color: "var(--n-700)" }}>{label}</td>
                        <td style={{ padding: "9px 18px", textAlign: "right", color: alerta(l) ? "var(--danger)" : "var(--n-700)", fontWeight: alerta(l) ? 700 : 400 }}>{l}</td>
                        <td style={{ padding: "9px 18px", textAlign: "right", color: alerta(u) ? "var(--danger)" : "var(--n-700)", fontWeight: alerta(u) ? 700 : 400 }}>{u}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </Card>

            {(estado.unified.envios_inciertos > 0 || estado.unified.loops_agotados > 0) && (
              <div style={{
                marginTop: 14, padding: "12px 14px", fontSize: 13.5, lineHeight: 1.6,
                background: "#f7e6e1", color: "var(--danger)",
                border: "1px solid rgba(154,63,40,.3)", borderRadius: "var(--r-md)",
                display: "flex", gap: 10, alignItems: "flex-start",
              }}>
                <AlertTriangle size={17} strokeWidth={1.75} style={{ flexShrink: 0, marginTop: 1 }} />
                <span>
                  El ciclo unificado tiene envíos inciertos o loops agotados sin resolver. El runbook
                  exige que ambos estén en cero antes de retirar el código legacy.
                </span>
              </div>
            )}

            {estado.nota && (
              <p style={{ fontSize: 12.5, color: "var(--n-600)", lineHeight: 1.6, marginTop: 14 }}>
                {estado.nota} Un rollback desvía sólo compras nuevas: las instancias <code>unified</code> ya
                iniciadas siguen siendo consumidas por el scheduler y hay que completarlas, pausarlas o
                cancelarlas explícitamente.
              </p>
            )}

            {/* Cambio de modo */}
            <div style={{
              marginTop: 24, background: "var(--surface)", padding: 22,
              borderRadius: "var(--r-lg)",
              border: `1px solid ${esUnified ? "rgba(154,63,40,.3)" : "var(--n-200)"}`,
            }}>
              <div style={{ fontSize: 16, fontWeight: 600, color: "var(--n-900)", marginBottom: 4 }}>
                {esUnified ? "Volver a legacy (rollback)" : "Habilitar el ciclo unificado"}
              </div>
              <p style={{ fontSize: 13.5, color: "var(--n-600)", lineHeight: 1.6, marginBottom: 14 }}>
                {esUnified
                  ? "Las compras nuevas vuelven al flujo anterior. No se reescriben instancias, eventos, acciones ni OCs existentes."
                  : "Las compras nuevas pasan a ser gobernadas por las tarjetas del ciclo. El backend rechaza el cambio si el workflow activo no valida limpio."}
                {" "}Para confirmar, escribí <strong>{palabraConfirmacion}</strong>.
              </p>

              <Input
                label="Motivo (queda registrado)"
                value={motivo}
                onChange={e => setMotivo(e.target.value)}
                placeholder={esUnified ? "Rollback: describir incidente y ticket" : "Ciclo validado por el equipo de compras"}
              />
              <div style={{ marginTop: 12 }}>
                <Input
                  value={confirmacion}
                  onChange={e => setConfirmacion(e.target.value)}
                  placeholder={`Escribí ${palabraConfirmacion}`}
                />
              </div>

              {error && (
                <div style={{ marginTop: 12, fontSize: 13, color: "var(--danger)" }}>{error}</div>
              )}

              <BtnPrimary
                onClick={() => void aplicarCambio()}
                disabled={!puedeAplicar}
                style={{ marginTop: 14, width: "100%" }}
              >
                {aplicando ? "Aplicando…" : esUnified ? "Volver a legacy" : "Habilitar unified"}
              </BtnPrimary>
            </div>
          </>
        )}
      </div>
    </>
  );
}
