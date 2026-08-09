"use client";
import { BtnPrimary, BtnSecondary, Card, Input } from "@/components/ui";

export interface Etapa {
  nombre: string;
  tipo: string;
  roles: string[];
}

export interface ReglaAutorizacion {
  hasta: number | null;
  desde: number | null;
  descripcion: string;
}

export interface ResponsableDetectado {
  nombre: string;
  email: string;
  roles: string[];
}

export interface Propuesta {
  resumen: string;
  etapas: Etapa[];
  reglas_autorizacion: ReglaAutorizacion[];
  requiere_aclaracion: boolean;
  preguntas: string[];
  nodos: Record<string, unknown>[];
  conexiones: Record<string, unknown>[];
  responsables_detectados: ResponsableDetectado[];
}

export const TIPO_LABEL: Record<string, string> = {
  tarea_humana: "Tarea", revision: "Revisión", autorizacion: "Autorización",
  homologacion: "Homologación", emision_oc: "Emisión de OC",
  compra_sin_oc: "Compra sin OC", espera_documento: "Espera de documento",
  accion_automatica: "Acción automática",
};

export function fmtCLP(n: number) {
  return `$${Math.round(n).toLocaleString("es-CL")}`;
}

interface Props {
  propuesta: Propuesta;
  aInvitar: Set<string>;
  onToggleInvitar: (email: string, activo: boolean) => void;
  nombreWorkflow: string;
  onNombreWorkflowChange: (v: string) => void;
  onCorregir: () => void;
  onConfirmar: () => void;
  cargando: boolean;
  /** Onboarding lo muestra como preview sin acción de guardar/corregir. */
  soloPreview?: boolean;
}

/** Resumen conversacional de un workflow propuesto — etapas, reglas por
 * monto y responsables detectados, con checkboxes para invitar. Compartido
 * entre `/settings/autorizaciones` y el onboarding para no duplicar el JSX
 * ni el comportamiento de cada uno. */
export function PropuestaWorkflowCard({
  propuesta, aInvitar, onToggleInvitar, nombreWorkflow, onNombreWorkflowChange,
  onCorregir, onConfirmar, cargando, soloPreview,
}: Props) {
  return (
    <Card padding={18} style={{ marginLeft: 36 }}>
      <div style={{ display: "flex", flexDirection: "column", gap: 10, marginBottom: 14 }}>
        {propuesta.etapas.map((e, i) => (
          <div key={i} style={{ display: "flex", alignItems: "center", gap: 10, fontSize: 13.5 }}>
            <span style={{
              width: 22, height: 22, borderRadius: "50%", flexShrink: 0,
              background: "var(--brand-50)", color: "var(--brand)", fontSize: 11, fontWeight: 600,
              display: "inline-flex", alignItems: "center", justifyContent: "center",
            }}>{i + 1}</span>
            <div>
              <strong style={{ color: "var(--n-900)" }}>{e.nombre}</strong>
              <span style={{ color: "var(--n-500)" }}> · {TIPO_LABEL[e.tipo] ?? e.tipo} · {e.roles.join(", ")}</span>
            </div>
          </div>
        ))}
        {propuesta.reglas_autorizacion.length > 1 && (
          <div style={{ marginTop: 4, paddingTop: 10, borderTop: "1px dashed var(--n-200)" }}>
            <div style={{ fontSize: 12.5, color: "var(--n-500)", marginBottom: 6 }}>Reglas por monto:</div>
            {propuesta.reglas_autorizacion.map((r, i) => (
              <div key={i} style={{ fontSize: 13, color: "var(--n-700)", marginBottom: 3 }}>
                {r.hasta != null ? `Hasta ${fmtCLP(r.hasta)}` : `Desde ${fmtCLP(r.desde ?? 0)}`}: {r.descripcion}
              </div>
            ))}
          </div>
        )}
        {(propuesta.responsables_detectados || []).length > 0 && (
          <div style={{ marginTop: 4, paddingTop: 10, borderTop: "1px dashed var(--n-200)" }}>
            <div style={{ fontSize: 12.5, color: "var(--n-500)", marginBottom: 6 }}>
              Personas detectadas{!soloPreview && " · desmarca para no invitar"}
            </div>
            {(propuesta.responsables_detectados || []).map((r, i) => {
              const puedeInvitar = !!r.email && !soloPreview;
              const activo = puedeInvitar && aInvitar.has(r.email);
              return (
                <label key={`${r.email || r.nombre}-${i}`} style={{
                  display: "flex", alignItems: "center", gap: 8, padding: "5px 0",
                  fontSize: 13, color: "var(--n-800)",
                  cursor: puedeInvitar ? "pointer" : "default", opacity: puedeInvitar ? 1 : 0.65,
                }}>
                  {!soloPreview && (
                    <input
                      type="checkbox"
                      checked={activo}
                      disabled={!puedeInvitar}
                      onChange={e => {
                        if (!puedeInvitar) return;
                        onToggleInvitar(r.email, e.target.checked);
                      }}
                    />
                  )}
                  <div style={{ flex: 1 }}>
                    <div><strong style={{ color: "var(--n-900)" }}>{r.nombre || "(sin nombre)"}</strong>
                      {r.email && <span style={{ color: "var(--n-500)" }}> · {r.email}</span>}
                    </div>
                    <div style={{ fontSize: 11.5, color: "var(--n-500)" }}>
                      {r.roles.join(", ")}
                      {!r.email && " · sin email, no se puede invitar"}
                    </div>
                  </div>
                </label>
              );
            })}
          </div>
        )}
      </div>
      {!soloPreview && (
        <>
          <Input label="Nombre de este ciclo" value={nombreWorkflow} onChange={e => onNombreWorkflowChange(e.target.value)} />
          <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
            <BtnSecondary onClick={onCorregir} style={{ flex: 1 }}>Quiero corregir</BtnSecondary>
            <BtnPrimary onClick={onConfirmar} disabled={cargando} style={{ flex: 1 }}>
              {cargando ? "Guardando…" : "Sí, guardar como borrador"}
            </BtnPrimary>
          </div>
        </>
      )}
      {soloPreview && (
        <div style={{ fontSize: 12, color: "var(--n-500)", marginTop: 10 }}>
          Podrás revisar y activar este ciclo en Configuración → Ciclo de compras.
        </div>
      )}
    </Card>
  );
}
