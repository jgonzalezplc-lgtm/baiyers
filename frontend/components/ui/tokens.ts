/**
 * Mapas centrales del design system:
 *   - estado de dominio → tokens de color del badge
 *   - categoría de compra → ícono de línea + tinte
 * Cualquier pantalla que muestre estados o categorías debe usar estos mapas.
 */
import {
  HardHat, Ruler, Zap, Cpu, Cog, Package, Briefcase, Search,
  type LucideIcon,
} from "lucide-react";

// ─── Estados ────────────────────────────────────────────────────────────────
export type EstadoUI =
  | "cotizando" | "aprobada" | "en_curso" | "cerrada" | "rechazada" | "borrador";

export const ESTADO_TOKENS: Record<EstadoUI, { bg: string; fg: string; label: string }> = {
  cotizando: { bg: "var(--st-cotizando-bg)", fg: "var(--st-cotizando-fg)", label: "Cotizando" },
  aprobada:  { bg: "var(--st-aprobada-bg)",  fg: "var(--st-aprobada-fg)",  label: "Aprobada" },
  en_curso:  { bg: "var(--st-encurso-bg)",   fg: "var(--st-encurso-fg)",   label: "En curso" },
  cerrada:   { bg: "var(--st-cerrada-bg)",   fg: "var(--st-cerrada-fg)",   label: "Cerrada" },
  rechazada: { bg: "var(--st-rechazada-bg)", fg: "var(--st-rechazada-fg)", label: "Rechazada" },
  borrador:  { bg: "var(--st-borrador-bg)",  fg: "var(--st-borrador-fg)",  label: "Borrador" },
};

/** Normaliza los muchos estados del backend a los 6 estados visuales. */
export function normalizarEstado(raw: string | null | undefined): EstadoUI {
  const e = (raw ?? "").toLowerCase().trim().replace(/\s+/g, "_");
  if (["aprobada", "aprobado", "autorizado", "autorizada", "entregado", "completada", "completado", "recibida"].includes(e)) return "aprobada";
  if (["rechazada", "rechazado", "cancelada", "cancelado", "expirado", "error", "fallida"].includes(e)) return "rechazada";
  if (["borrador", "draft", "nueva", "nuevo", "identificado", "pendiente_envio"].includes(e)) return "borrador";
  if (["cerrada", "cerrado", "archivada", "archivado", "facturado", "finalizada"].includes(e)) return "cerrada";
  if (["en_curso", "en_transito", "enviada", "enviado", "oc_enviada", "en_proceso", "procesando", "activa", "activo"].includes(e)) return "en_curso";
  return "cotizando";
}

// ─── Categorías de compra ───────────────────────────────────────────────────
export interface CategoriaToken { icon: LucideIcon; bg: string; fg: string; label: string }

export const CATEGORIA_TOKENS: Record<string, CategoriaToken> = {
  construccion: { icon: HardHat,   bg: "#f6efdd", fg: "#8a6212", label: "Construcción" },
  carpinteria:  { icon: Ruler,     bg: "#f1e7db", fg: "#7a5a3a", label: "Carpintería" },
  electrico:    { icon: Zap,       bg: "#e4edf5", fg: "#1f5fb0", label: "Eléctrico" },
  electronica:  { icon: Cpu,       bg: "#ece8f5", fg: "#5a4a9a", label: "Electrónica" },
  mecanico:     { icon: Cog,       bg: "#e9e9e5", fg: "#5f594f", label: "Mecánico" },
  consumible:   { icon: Package,   bg: "#e6efe4", fg: "#2f6b3c", label: "Consumible" },
  oficina:      { icon: Briefcase, bg: "#e2eef0", fg: "#136b76", label: "Oficina" },
  otro:         { icon: Search,    bg: "#f1efea", fg: "#8a8478", label: "Otro" },
};

/** Tintes profundos para modo oscuro (fondo oscuro + ícono claro). */
export const CATEGORIA_TOKENS_DARK: Record<string, { bg: string; fg: string }> = {
  construccion: { bg: "#3a2f14", fg: "#e8c766" },
  carpinteria:  { bg: "#33261a", fg: "#c99a6f" },
  electrico:    { bg: "#16283f", fg: "#7fa8e0" },
  electronica:  { bg: "#251f38", fg: "#a99ce0" },
  mecanico:     { bg: "#2c2a24", fg: "#b3ada1" },
  consumible:   { bg: "#1c2f1e", fg: "#8ec79a" },
  oficina:      { bg: "#14302f", fg: "#6fc0c9" },
  otro:         { bg: "#2b2924", fg: "#b3ada1" },
};

export function categoriaToken(cat: string | null | undefined): CategoriaToken {
  const k = (cat ?? "").toLowerCase().trim().replace(/\s+/g, "_");
  return CATEGORIA_TOKENS[k] ?? CATEGORIA_TOKENS.otro;
}

/** Etiqueta legible de una categoría (soporta categorías custom del usuario). */
export function categoriaLabel(cat: string | null | undefined): string {
  const k = (cat ?? "").toLowerCase().trim().replace(/\s+/g, "_");
  if (CATEGORIA_TOKENS[k]) return CATEGORIA_TOKENS[k].label;
  if (!cat) return "Otro";
  return cat.charAt(0).toUpperCase() + cat.slice(1).replace(/_/g, " ");
}

// ─── Formato ────────────────────────────────────────────────────────────────
export const fmtCLP = (n: number) => `$${Math.round(n).toLocaleString("es-CL")}`;
