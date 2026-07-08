export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type EstadoProveedor =
  | "pendiente_cotizar"
  | "correo_enviado"
  | "respuesta_recibida"
  | "seleccionado"
  | "oc_emitida"
  | "descartado";

export const ESTADO_META: Record<EstadoProveedor, { label: string; color: string; bg: string; tachado?: boolean }> = {
  pendiente_cotizar:   { label: "Pendiente",   color: "#606060", bg: "#f5f5f5" },
  correo_enviado:      { label: "Correo env.", color: "#1e40af", bg: "#dbeafe" },
  respuesta_recibida:  { label: "Respondió",   color: "#92400e", bg: "#fef3c7" },
  seleccionado:        { label: "Seleccionado",color: "#1a6e45", bg: "#e6f4ec" },
  oc_emitida:          { label: "OC emitida",  color: "#ffffff", bg: "#1a6e45" },
  descartado:          { label: "Descartado",  color: "#9a9a9a", bg: "#fafafa", tachado: true },
};

export type Badge = "mas_conveniente" | "mas_economico" | "disponibilidad_inmediata";

export const BADGE_META: Record<Badge, { label: string; color: string; bg: string; border: string }> = {
  mas_conveniente:          { label: "Más conveniente",        color: "#ffffff", bg: "#c0392b", border: "#c0392b" },
  mas_economico:            { label: "Más económico",          color: "#ffffff", bg: "#2e2e2e", border: "#2e2e2e" },
  disponibilidad_inmediata: { label: "Disponibilidad inmediata", color: "#1a6e45", bg: "#e6f4ec", border: "#1a6e45" },
};

export const EVENTO_ESTADO_META: Record<string, { label: string; color: string; bg: string }> = {
  borrador:      { label: "Borrador",      color: "#606060", bg: "#f5f5f5" },
  en_cotizacion: { label: "En cotización", color: "#1e40af", bg: "#dbeafe" },
  oc_emitida:    { label: "OC emitida",    color: "#1a6e45", bg: "#e6f4ec" },
  cerrado:       { label: "Cerrado",       color: "#ffffff", bg: "#1a6e45" },
  cancelado:     { label: "Cancelado",     color: "#9a9a9a", bg: "#fafafa" },
};

export const TIMELINE_ICON: Record<string, string> = {
  evento_creado:          "◆",
  proveedor_agregado:     "＋",
  cotizacion_enviada:     "📧",
  respuesta_recibida:     "📩",
  proveedor_seleccionado: "★",
  oc_emitida:             "✅",
  despacho_recibido:      "📦",
  nota:                   "•",
};

export function fmtPrecio(precio: number | null | undefined, moneda = "CLP"): string {
  if (precio == null) return "—";
  if (moneda === "CLP") return `$${Math.round(precio).toLocaleString("es-CL")}`;
  if (moneda === "EUR") return `€${precio.toLocaleString("de-DE", { maximumFractionDigits: 2 })}`;
  return `$${precio.toLocaleString("en-US", { maximumFractionDigits: 2 })} ${moneda}`;
}

export function fmtFecha(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleDateString("es-CL", { day: "2-digit", month: "short", year: "numeric" });
}

export function fmtFechaHora(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleString("es-CL", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" });
}
