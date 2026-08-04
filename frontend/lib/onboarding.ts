export const CAMPOS_REQUERIDOS = ["empresa", "nombre_usuario", "rut", "industria"] as const;
export type CampoRequerido = (typeof CAMPOS_REQUERIDOS)[number];

export function camposFaltantes(m: Record<string, unknown>): CampoRequerido[] {
  return CAMPOS_REQUERIDOS.filter(k => {
    const v = m[k];
    return typeof v !== "string" || !v.trim();
  });
}

export function normalizarRut(value: string): string {
  const limpio = value.replace(/[^0-9kK]/g, "").toUpperCase();
  if (limpio.length < 2) return "";
  const cuerpo = limpio.slice(0, -1).replace(/^0+/, "") || "0";
  const dv = limpio.slice(-1);
  return `${Number(cuerpo).toLocaleString("es-CL")}-${dv}`;
}

export function rutChilenoValido(value: string): boolean {
  const limpio = value.replace(/[^0-9kK]/g, "").toUpperCase();
  if (!/^\d{7,8}[0-9K]$/.test(limpio)) return false;
  const cuerpo = limpio.slice(0, -1);
  const dv = limpio.slice(-1);
  let suma = 0;
  let factor = 2;
  for (let i = cuerpo.length - 1; i >= 0; i -= 1) {
    suma += Number(cuerpo[i]) * factor;
    factor = factor === 7 ? 2 : factor + 1;
  }
  const resultado = 11 - (suma % 11);
  const esperado = resultado === 11 ? "0" : resultado === 10 ? "K" : String(resultado);
  return dv === esperado;
}
