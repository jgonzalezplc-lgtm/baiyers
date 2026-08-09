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
  /** "Aceptar" — abre el canvas de inmediato. Activar el ciclo ya se hace
   * desde ahí (el canvas tiene su propio botón "Activar"), no desde acá. */
  onAceptar: () => void;
  /** "Modificar" — descarta este borrador y vuelve al chat original para
   * redescribir el proceso desde cero. */
  onModificar: () => void;
}

/** Tarjeta de resultado tras crear un workflow — dos únicas acciones, sin
 * ambigüedad: aceptarlo (te lleva al canvas a revisar/activar) o pedir
 * cambios (vuelve al chat). Compartida entre `/settings/autorizaciones` y
 * el onboarding para no duplicar el flujo. */
export function WorkflowGuardadoCard({ workflow, errores, onAceptar, onModificar }: Props) {
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
        <BtnSecondary onClick={onModificar} style={{ flex: 1 }}>
          Modificar
        </BtnSecondary>
        <BtnPrimary onClick={onAceptar} style={{ flex: 1 }}>
          Aceptar
        </BtnPrimary>
      </div>
    </Card>
  );
}
