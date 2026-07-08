"use client";

type FiltroPrecio = "todos" | "con_precio" | "sin_precio";
type FiltroPais = "todos" | "chile" | "internacional";
type Orden = "relevancia" | "precio_asc" | "precio_desc";

interface Props {
  filtroPrecio: FiltroPrecio;
  filtroPais: FiltroPais;
  orden: Orden;
  total: number;
  onFiltroPrecio: (v: FiltroPrecio) => void;
  onFiltroPais: (v: FiltroPais) => void;
  onOrden: (v: Orden) => void;
}

function BtnFiltro({ activo, onClick, children }: { activo: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      onClick={onClick}
      className="label"
      style={{
        padding: "5px 10px",
        cursor: "pointer",
        fontFamily: "var(--font-mono)",
        border: "1px solid var(--border-default)",
        borderLeft: "none",
        background: activo ? "var(--fill-error)" : "var(--bg-surface)",
        color: activo ? "var(--accent)" : "var(--text-muted)",
        fontWeight: activo ? 700 : 400,
      }}
    >
      {children}
    </button>
  );
}

export default function FiltrosProveedores({ filtroPrecio, filtroPais, orden, total, onFiltroPrecio, onFiltroPais, onOrden }: Props) {
  return (
    <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center", padding: "12px 0", borderBottom: "1px solid var(--border-default)", marginBottom: 16 }}>
      <span className="label" style={{ color: "var(--text-muted)", marginRight: 4 }}>{total} resultados</span>

      <div style={{ display: "flex", border: "1px solid var(--border-default)" }}>
        {([
          { val: "todos", label: "Todos" },
          { val: "con_precio", label: "Con precio" },
          { val: "sin_precio", label: "A cotizar" },
        ] as { val: FiltroPrecio; label: string }[]).map(f => (
          <BtnFiltro key={f.val} activo={filtroPrecio === f.val} onClick={() => onFiltroPrecio(f.val)}>
            {f.label}
          </BtnFiltro>
        ))}
      </div>

      <div style={{ width: 1, height: 16, background: "var(--border-default)" }} />

      <div style={{ display: "flex", border: "1px solid var(--border-default)" }}>
        {([
          { val: "todos", label: "Todos" },
          { val: "chile", label: "Chile" },
          { val: "internacional", label: "Internacional" },
        ] as { val: FiltroPais; label: string }[]).map(f => (
          <BtnFiltro key={f.val} activo={filtroPais === f.val} onClick={() => onFiltroPais(f.val)}>
            {f.label}
          </BtnFiltro>
        ))}
      </div>

      <div style={{ width: 1, height: 16, background: "var(--border-default)" }} />

      <select
        value={orden}
        onChange={e => onOrden(e.target.value as Orden)}
        style={{
          padding: "5px 10px",
          fontSize: 10,
          background: "var(--bg-base)",
          border: "1px solid var(--border-default)",
          color: "var(--text-secondary)",
          fontFamily: "var(--font-mono)",
          cursor: "pointer",
          outline: "none",
          textTransform: "uppercase",
          letterSpacing: "0.05em",
        }}
      >
        <option value="relevancia">Relevancia</option>
        <option value="precio_asc">Precio menor</option>
        <option value="precio_desc">Precio mayor</option>
      </select>
    </div>
  );
}
