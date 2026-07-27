"use client";
/**
 * Componentes base del design system "soft professional".
 * Los nombres antiguos (BtnPrimary, BtnSecondary, Card, Label, Badge, Input,
 * SectionRule, Divider) se mantienen para no romper pantallas existentes, pero
 * su implementación es la nueva.
 */
import { useEffect, useState, type CSSProperties, type ReactNode } from "react";
import { X, Moon, Sun, type LucideIcon } from "lucide-react";
import {
  ESTADO_TOKENS, normalizarEstado, categoriaToken, CATEGORIA_TOKENS_DARK,
  type EstadoUI,
} from "./tokens";

export * from "./tokens";

// ═══ Botones ════════════════════════════════════════════════════════════════
type ButtonVariant = "primary" | "secondary" | "ghost" | "danger";
type ButtonSize = "sm" | "md";

interface ButtonProps {
  children: ReactNode;
  onClick?: () => void;
  disabled?: boolean;
  type?: "button" | "submit" | "reset";
  className?: string;
  style?: CSSProperties;
  variant?: ButtonVariant;
  size?: ButtonSize;
  icon?: LucideIcon;
  title?: string;
}

const BTN_BASE: CSSProperties = {
  display: "inline-flex",
  alignItems: "center",
  justifyContent: "center",
  gap: 8,
  borderRadius: "var(--r-md)",
  fontFamily: "var(--font-sans)",
  fontWeight: 600,
  cursor: "pointer",
  transition: "background .15s ease, border-color .15s ease, opacity .15s ease",
  whiteSpace: "nowrap",
};

const BTN_VARIANT: Record<ButtonVariant, CSSProperties> = {
  primary:   { background: "var(--brand)", color: "#fff", border: "none" },
  secondary: { background: "var(--surface)", color: "var(--n-700)", border: "1px solid var(--n-300)" },
  ghost:     { background: "transparent", color: "var(--brand)", border: "1px solid transparent" },
  danger:    { background: "var(--surface)", color: "var(--danger)", border: "1px solid var(--n-300)" },
};

export function Button({
  children, onClick, disabled, type = "button", className = "",
  style, variant = "primary", size = "md", icon: Icon, title,
}: ButtonProps) {
  const [hover, setHover] = useState(false);
  const sizeStyle: CSSProperties = size === "sm"
    ? { padding: "7px 12px", fontSize: 13 }
    : { padding: "10px 16px", fontSize: 14 };

  const hoverStyle: CSSProperties = !disabled && hover
    ? variant === "primary" ? { background: "var(--brand-strong)" }
    : variant === "ghost"   ? { background: "var(--brand-50)" }
    : { background: "var(--surface-2)", borderColor: "var(--n-400)" }
    : {};

  const disabledStyle: CSSProperties = disabled
    ? variant === "primary"
      ? { background: "var(--n-400)", cursor: "not-allowed" }
      : { opacity: .5, cursor: "not-allowed" }
    : {};

  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled}
      title={title}
      className={className}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      style={{ ...BTN_BASE, ...BTN_VARIANT[variant], ...sizeStyle, ...hoverStyle, ...disabledStyle, ...style }}
    >
      {Icon && <Icon size={16} strokeWidth={1.75} />}
      {children}
    </button>
  );
}

export const BtnPrimary = (p: Omit<ButtonProps, "variant">) => <Button {...p} variant="primary" />;
export const BtnSecondary = (p: Omit<ButtonProps, "variant">) => <Button {...p} variant="secondary" />;
export const BtnGhost = (p: Omit<ButtonProps, "variant">) => <Button {...p} variant="ghost" />;

// ═══ Badge de estado ════════════════════════════════════════════════════════
export function Badge({
  status, children, tipo, style,
}: {
  status?: string;
  children?: ReactNode;
  /** Legacy: success | warning | error | info | default */
  tipo?: "success" | "warning" | "error" | "info" | "default";
  style?: CSSProperties;
}) {
  const legacyMap: Record<string, EstadoUI> = {
    success: "aprobada", warning: "cotizando", error: "rechazada",
    info: "en_curso", default: "cerrada",
  };
  const key: EstadoUI = status ? normalizarEstado(status) : legacyMap[tipo ?? "default"];
  const t = ESTADO_TOKENS[key];

  return (
    <span style={{
      display: "inline-flex", alignItems: "center", gap: 6,
      padding: "4px 11px", borderRadius: "var(--r-pill)",
      background: t.bg, color: t.fg,
      fontSize: 12.5, fontWeight: 600, lineHeight: 1.4,
      fontFamily: "var(--font-sans)", whiteSpace: "nowrap",
      ...style,
    }}>
      <span style={{ width: 6, height: 6, borderRadius: "50%", background: "currentColor", flexShrink: 0 }} />
      {children ?? t.label}
    </span>
  );
}

// ═══ Chip de categoría ══════════════════════════════════════════════════════
export function CategoryChip({
  categoria, size = 40, showLabel = false,
}: { categoria: string | null | undefined; size?: number; showLabel?: boolean }) {
  const t = categoriaToken(categoria);
  const dark = useIsDark();
  const key = (categoria ?? "").toLowerCase().trim().replace(/\s+/g, "_");
  const tint = dark ? (CATEGORIA_TOKENS_DARK[key] ?? CATEGORIA_TOKENS_DARK.otro) : t;
  const Icon = t.icon;

  const chip = (
    <span style={{
      width: size, height: size, flexShrink: 0,
      borderRadius: size >= 36 ? 8 : 6,
      background: tint.bg, color: tint.fg,
      display: "inline-flex", alignItems: "center", justifyContent: "center",
    }}>
      <Icon size={Math.round(size * 0.5)} strokeWidth={1.75} />
    </span>
  );

  if (!showLabel) return chip;
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 8 }}>
      {chip}
      <span style={{ fontSize: 13, color: "var(--n-600)" }}>{t.label}</span>
    </span>
  );
}

// ═══ Card ═══════════════════════════════════════════════════════════════════
export function Card({
  children, selected, className = "", style, padding = 18,
}: {
  children: ReactNode; selected?: boolean; className?: string;
  style?: CSSProperties; padding?: number;
}) {
  return (
    <div className={className} style={{
      background: "var(--surface)",
      border: `1px solid ${selected ? "var(--brand-200)" : "var(--n-200)"}`,
      borderRadius: "var(--r-lg)",
      boxShadow: selected ? "0 0 0 3px var(--brand-50)" : "var(--shadow-card)",
      padding,
      ...style,
    }}>
      {children}
    </div>
  );
}

// ═══ Input / Textarea ═══════════════════════════════════════════════════════
interface InputProps {
  label?: string;
  placeholder?: string;
  value?: string;
  onChange?: (e: React.ChangeEvent<HTMLInputElement>) => void;
  onKeyDown?: (e: React.KeyboardEvent<HTMLInputElement>) => void;
  type?: string;
  error?: string;
  hint?: string;
  disabled?: boolean;
  autoFocus?: boolean;
  mono?: boolean;
  style?: CSSProperties;
}

const fieldStyle = (focus: boolean, error?: string, mono?: boolean): CSSProperties => ({
  width: "100%",
  height: 42,
  padding: "0 12px",
  background: "var(--surface)",
  color: "var(--n-900)",
  border: error
    ? "1.5px solid #c8623f"
    : focus ? "1.5px solid var(--brand)" : "1px solid var(--n-300)",
  borderRadius: "var(--r-md)",
  boxShadow: error
    ? "0 0 0 3px var(--st-rechazada-bg)"
    : focus ? "0 0 0 3px var(--brand-50)" : "none",
  fontFamily: mono ? "var(--font-mono)" : "var(--font-sans)",
  fontVariantNumeric: mono ? "tabular-nums" : undefined,
  fontSize: 14,
  outline: "none",
  transition: "border-color .15s ease, box-shadow .15s ease",
});

export function Input({
  label, placeholder, value, onChange, onKeyDown, type = "text",
  error, hint, disabled, autoFocus, mono, style,
}: InputProps) {
  const [focus, setFocus] = useState(false);
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
      {label && <FieldLabel>{label}</FieldLabel>}
      <input
        type={type} value={value} onChange={onChange} onKeyDown={onKeyDown}
        placeholder={placeholder} disabled={disabled} autoFocus={autoFocus}
        style={{ ...fieldStyle(focus, error, mono), opacity: disabled ? .6 : 1, ...style }}
        onFocus={() => setFocus(true)} onBlur={() => setFocus(false)}
      />
      {error && <span style={{ fontSize: 12.5, color: "var(--danger)" }}>{error}</span>}
      {!error && hint && <span style={{ fontSize: 12.5, color: "var(--n-500)" }}>{hint}</span>}
    </div>
  );
}

export function Textarea({
  label, placeholder, value, onChange, rows = 3, error, hint, style,
}: {
  label?: string; placeholder?: string; value?: string;
  onChange?: (e: React.ChangeEvent<HTMLTextAreaElement>) => void;
  rows?: number; error?: string; hint?: string; style?: CSSProperties;
}) {
  const [focus, setFocus] = useState(false);
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
      {label && <FieldLabel>{label}</FieldLabel>}
      <textarea
        value={value} onChange={onChange} placeholder={placeholder} rows={rows}
        style={{ ...fieldStyle(focus, error), height: "auto", padding: "10px 12px", resize: "vertical", lineHeight: 1.6, ...style }}
        onFocus={() => setFocus(true)} onBlur={() => setFocus(false)}
      />
      {error && <span style={{ fontSize: 12.5, color: "var(--danger)" }}>{error}</span>}
      {!error && hint && <span style={{ fontSize: 12.5, color: "var(--n-500)" }}>{hint}</span>}
    </div>
  );
}

export function FieldLabel({ children }: { children: ReactNode }) {
  return <span style={{ fontSize: 13, fontWeight: 500, color: "var(--n-700)" }}>{children}</span>;
}

// ═══ Tipografía auxiliar ════════════════════════════════════════════════════
export function Label({ children, style }: { children: ReactNode; style?: CSSProperties }) {
  return <span style={{ fontSize: 12, fontWeight: 500, color: "var(--n-500)", lineHeight: 1.5, ...style }}>{children}</span>;
}

/** Montos y códigos, mono + cifras tabulares. */
export function Mono({ children, style }: { children: ReactNode; style?: CSSProperties }) {
  return <span style={{ fontFamily: "var(--font-mono)", fontVariantNumeric: "tabular-nums", ...style }}>{children}</span>;
}

export function PageHeader({
  eyebrow, title, subtitle, actions,
}: { eyebrow?: string; title: string; subtitle?: string; actions?: ReactNode }) {
  return (
    <div style={{ marginBottom: 24, display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 16, flexWrap: "wrap" }}>
      <div>
        {eyebrow && <div style={{ fontSize: 13, fontWeight: 500, color: "var(--brand)", marginBottom: 4 }}>{eyebrow}</div>}
        <h1 style={{ fontSize: 26, lineHeight: 1.2, fontWeight: 600, color: "var(--n-900)", margin: 0, letterSpacing: "-0.015em" }}>{title}</h1>
        {subtitle && <p style={{ fontSize: 14, color: "var(--n-600)", margin: "6px 0 0", lineHeight: 1.6 }}>{subtitle}</p>}
      </div>
      {actions && <div style={{ display: "flex", gap: 8, alignItems: "center" }}>{actions}</div>}
    </div>
  );
}

/** Legacy, antes era una barra roja. Ahora no dibuja nada (el header ya separa). */
export function SectionRule() { return null; }

export function Divider({ style }: { style?: CSSProperties }) {
  return <hr style={{ border: "none", borderTop: "1px solid var(--n-200)", margin: "24px 0", ...style }} />;
}

// ═══ Tabla estilo base de datos ═════════════════════════════════════════════
export function Table({ children, style }: { children: ReactNode; style?: CSSProperties }) {
  return (
    <div style={{
      background: "var(--surface)", border: "1px solid var(--n-200)",
      borderRadius: "var(--r-lg)", overflow: "hidden", ...style,
    }}>
      {children}
    </div>
  );
}

export function TableHead({ cols, children }: { cols: string; children: ReactNode }) {
  return (
    <div style={{
      display: "grid", gridTemplateColumns: cols, gap: 12,
      padding: "10px 16px", background: "var(--canvas)",
      borderBottom: "1px solid var(--n-200)",
      fontSize: 12, fontWeight: 600, color: "var(--n-600)",
    }}>
      {children}
    </div>
  );
}

export function TableRow({
  cols, children, onClick, zebra, last,
}: {
  cols: string; children: ReactNode; onClick?: () => void;
  zebra?: boolean; last?: boolean;
}) {
  const [hover, setHover] = useState(false);
  return (
    <div
      onClick={onClick}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      style={{
        display: "grid", gridTemplateColumns: cols, gap: 12, alignItems: "center",
        padding: "12px 16px",
        borderBottom: last ? "none" : "1px solid var(--n-100)",
        background: hover && onClick ? "var(--surface-2)" : zebra ? "var(--canvas)" : "transparent",
        cursor: onClick ? "pointer" : "default",
        transition: "background .12s ease",
        fontSize: 14,
      }}
    >
      {children}
    </div>
  );
}

// ═══ Modal ══════════════════════════════════════════════════════════════════
export function Modal({
  open, onClose, title, children, footer, width = 460, icon: Icon,
}: {
  open: boolean; onClose: () => void; title?: string;
  children: ReactNode; footer?: ReactNode; width?: number; icon?: LucideIcon;
}) {
  useEffect(() => {
    if (!open) return;
    const h = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [open, onClose]);

  if (!open) return null;
  return (
    <div
      onClick={onClose}
      style={{
        position: "fixed", inset: 0, zIndex: 200,
        background: "rgba(33,29,24,.4)", backdropFilter: "blur(2px)",
        display: "flex", alignItems: "center", justifyContent: "center", padding: 20,
      }}
    >
      <div
        onClick={e => e.stopPropagation()}
        style={{
          width, maxWidth: "100%", maxHeight: "90vh", overflowY: "auto",
          background: "var(--surface)", borderRadius: "var(--r-xl)",
          boxShadow: "var(--shadow-modal)", padding: 22,
        }}
      >
        {(title || Icon) && (
          <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 16 }}>
            {Icon && (
              <span style={{
                width: 40, height: 40, borderRadius: "var(--r-md)", flexShrink: 0,
                background: "var(--brand-50)", color: "var(--brand)",
                display: "inline-flex", alignItems: "center", justifyContent: "center",
              }}>
                <Icon size={20} strokeWidth={1.75} />
              </span>
            )}
            {title && <h2 style={{ fontSize: 20, fontWeight: 600, color: "var(--n-900)", margin: 0, flex: 1 }}>{title}</h2>}
            <button onClick={onClose} aria-label="Cerrar" style={{
              background: "none", border: "none", cursor: "pointer",
              color: "var(--n-500)", padding: 4, borderRadius: "var(--r-sm)",
              display: "inline-flex",
            }}>
              <X size={18} strokeWidth={1.75} />
            </button>
          </div>
        )}
        {children}
        {footer && <div style={{ display: "flex", gap: 10, marginTop: 20 }}>{footer}</div>}
      </div>
    </div>
  );
}

/** Panel de resumen dentro de un modal o card. */
export function SummaryPanel({ children, style }: { children: ReactNode; style?: CSSProperties }) {
  return (
    <div style={{
      background: "var(--surface-2)", border: "1px solid var(--n-200)",
      borderRadius: "var(--r-md)", padding: 14, ...style,
    }}>
      {children}
    </div>
  );
}

/** Bloque destacado, p.ej. "mejor precio". */
export function Highlight({ children, style }: { children: ReactNode; style?: CSSProperties }) {
  return (
    <div style={{
      background: "var(--brand-50)", border: "1px solid var(--brand-100)",
      borderRadius: "var(--r-md)", padding: 12, ...style,
    }}>
      {children}
    </div>
  );
}

// ═══ Empty state ════════════════════════════════════════════════════════════
export function EmptyState({
  icon: Icon, title, description, action,
}: { icon?: LucideIcon | ReactNode; title: string; description?: string; action?: ReactNode }) {
  const iconEl = typeof Icon === "function"
    ? <Icon size={26} strokeWidth={1.5} />
    : Icon;
  return (
    <div style={{ padding: "56px 20px", textAlign: "center", display: "flex", flexDirection: "column", alignItems: "center", gap: 12 }}>
      {iconEl && (
        <span style={{
          width: 56, height: 56, borderRadius: "var(--r-lg)",
          background: "var(--brand-50)", color: "var(--brand)",
          display: "inline-flex", alignItems: "center", justifyContent: "center",
        }}>
          {iconEl}
        </span>
      )}
      <div style={{ fontSize: 16, fontWeight: 600, color: "var(--n-900)" }}>{title}</div>
      {description && (
        <p style={{ fontSize: 13.5, color: "var(--n-600)", maxWidth: 380, lineHeight: 1.6, margin: 0 }}>{description}</p>
      )}
      {action && <div style={{ marginTop: 4 }}>{action}</div>}
    </div>
  );
}

export function Spinner({ label = "Cargando…" }: { label?: string }) {
  return (
    <div style={{ padding: "48px 0", textAlign: "center", fontSize: 13.5, color: "var(--n-500)" }}>
      {label}
    </div>
  );
}

// ═══ Tema ═══════════════════════════════════════════════════════════════════
export function useIsDark() {
  const [dark, setDark] = useState(false);
  useEffect(() => {
    const read = () => setDark(document.documentElement.getAttribute("data-theme") === "dark");
    read();
    const obs = new MutationObserver(read);
    obs.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    return () => obs.disconnect();
  }, []);
  return dark;
}

export function ThemeToggle({ compact }: { compact?: boolean }) {
  const dark = useIsDark();
  const toggle = () => {
    const next = dark ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", next);
    try { localStorage.setItem("baiyer-theme", next); } catch { /* ignore */ }
  };
  const Icon = dark ? Sun : Moon;
  return (
    <button
      onClick={toggle}
      title={dark ? "Cambiar a modo claro" : "Cambiar a modo oscuro"}
      aria-label={dark ? "Cambiar a modo claro" : "Cambiar a modo oscuro"}
      style={{
        display: "inline-flex", alignItems: "center", gap: 10,
        background: "transparent", border: "none", cursor: "pointer",
        color: "var(--n-600)", padding: compact ? 8 : "8px 10px",
        borderRadius: "var(--r-md)", fontSize: 14, fontFamily: "var(--font-sans)",
      }}
    >
      <Icon size={18} strokeWidth={1.75} />
      {!compact && <span>{dark ? "Modo claro" : "Modo oscuro"}</span>}
    </button>
  );
}
