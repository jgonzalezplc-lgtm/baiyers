export const CAMPOS_REQUERIDOS = ["empresa", "nombre_usuario", "rut", "industria"] as const;
export type CampoRequerido = (typeof CAMPOS_REQUERIDOS)[number];

export function camposFaltantes(m: Record<string, unknown>): CampoRequerido[] {
  return CAMPOS_REQUERIDOS.filter(k => {
    const v = m[k];
    return typeof v !== "string" || !v.trim();
  });
}
