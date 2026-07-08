"use client";

// ─── Botón primario Swiss ──────────────────────────────────────────────────────
export function BtnPrimary({
  children,
  onClick,
  disabled,
  type = "button",
  className = "",
}: {
  children: React.ReactNode;
  onClick?: () => void;
  disabled?: boolean;
  type?: "button" | "submit" | "reset";
  className?: string;
}) {
  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled}
      className={`btn-swiss-primary disabled:opacity-40 disabled:cursor-not-allowed ${className}`}
    >
      {children}
    </button>
  );
}

// ─── Botón secundario Swiss ────────────────────────────────────────────────────
export function BtnSecondary({
  children,
  onClick,
  disabled,
  className = "",
}: {
  children: React.ReactNode;
  onClick?: () => void;
  disabled?: boolean;
  className?: string;
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className={`btn-swiss-secondary disabled:opacity-40 ${className}`}
    >
      {children}
    </button>
  );
}

// ─── Card Swiss ───────────────────────────────────────────────────────────────
export function Card({
  children,
  selected,
  className = "",
}: {
  children: React.ReactNode;
  selected?: boolean;
  className?: string;
}) {
  return (
    <div className={`${selected ? "card-selected" : "card-swiss"} p-6 ${className}`}>
      {children}
    </div>
  );
}

// ─── Label Swiss (uppercase tracking) ─────────────────────────────────────────
export function Label({ children }: { children: React.ReactNode }) {
  return <span className="label">{children}</span>;
}

// ─── Section rule (línea roja Swiss) ──────────────────────────────────────────
export function SectionRule() {
  return <div className="section-rule mb-4" />;
}

// ─── Badge de estado ──────────────────────────────────────────────────────────
type BadgeTipo = "success" | "warning" | "error" | "info" | "default";

const BADGE_STYLES: Record<BadgeTipo, string> = {
  success: "bg-success-fill text-success border border-success",
  warning: "bg-warning-fill text-warning border border-warning",
  error:   "bg-red-100 text-red-600 border border-red-400",
  info:    "bg-info-fill text-info border border-info",
  default: "bg-gray-100 text-gray-600 border border-gray-200",
};

export function Badge({
  tipo = "default",
  children,
}: {
  tipo?: BadgeTipo;
  children: React.ReactNode;
}) {
  return (
    <span className={`label px-2 py-1 ${BADGE_STYLES[tipo]}`}>
      {children}
    </span>
  );
}

// ─── Input Swiss ──────────────────────────────────────────────────────────────
export function Input({
  label,
  placeholder,
  value,
  onChange,
  type = "text",
  error,
}: {
  label?: string;
  placeholder?: string;
  value?: string;
  onChange?: (e: React.ChangeEvent<HTMLInputElement>) => void;
  type?: string;
  error?: string;
}) {
  return (
    <div className="flex flex-col gap-2">
      {label && <Label>{label}</Label>}
      <input
        type={type}
        value={value}
        onChange={onChange}
        placeholder={placeholder}
        className="w-full px-4 py-3 bg-[var(--bg-surface)] border border-[var(--border-default)]
                   text-[var(--text-primary)] font-mono text-sm
                   focus:outline-none focus:border-[var(--border-strong)]
                   placeholder:text-[var(--text-muted)]"
        style={{ borderRadius: "var(--radius-default)" }}
      />
      {error && <span className="text-xs text-red-500">{error}</span>}
    </div>
  );
}

// ─── Divider Swiss ────────────────────────────────────────────────────────────
export function Divider() {
  return <hr className="border-[var(--border-subtle)] my-6" />;
}
