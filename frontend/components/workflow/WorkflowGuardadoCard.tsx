"use client";
import { CheckCircle2, XCircle } from "lucide-react";
import { BtnPrimary, BtnSecondary, Card } from "@/components/ui";

export interface WorkflowGuardado {
  id: string;
  estado: string;
}

export interface ErrorValidacion {
  codigo: string;
  mensaje: string;
}

interface Props {
  workflow: WorkflowGuardado;
  errores: ErrorValidacion[];
  activando: boolean;
  onActivar: () => void;
  onAjustarVisualmente: () => void;
}

/** Tarjeta de resultado tras crear/activar un workflow — validación,
 * link al canvas y botón de activación explícita. Compartida entre
 * `/settings/autorizaciones` y el onboarding para no duplicar el flujo de
 * "borrador → validar → activar". */
export function WorkflowGuardadoCard({ workflow, errores, activando, onActivar, onAjustarVisualmente }: Props) {
  return (
    <Card padding={18} style={{ marginLeft: 36 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
        {errores.length === 0 ? (
          <CheckCircle2 size={18} color="var(--success)" />
        ) : (
          <XCircle size={18} color="var(--danger)" />
        )}
        <strong style={{ fontSize: 14, color: "var(--n-900)" }}>
          {workflow.estado === "activo" ? "Ciclo activo" : "Guardado como borrador"}
        </strong>
      </div>
      {errores.length > 0 && (
        <ul style={{ margin: "0 0 12px", paddingLeft: 20, fontSize: 13, color: "var(--danger)" }}>
          {errores.map((e, i) => <li key={i}>{e.mensaje}</li>)}
        </ul>
      )}
      <div style={{ display: "flex", gap: 8 }}>
        <BtnSecondary onClick={onAjustarVisualmente} style={{ flex: 1 }}>
          Ajustar visualmente
        </BtnSecondary>
        {workflow.estado !== "activo" && (
          <BtnPrimary onClick={onActivar} disabled={activando || errores.length > 0} style={{ flex: 1 }}>
            {activando ? "Activando…" : "Activar este ciclo"}
          </BtnPrimary>
        )}
      </div>
    </Card>
  );
}
