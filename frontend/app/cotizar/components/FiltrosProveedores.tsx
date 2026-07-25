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

function Segmento<T extends string>({ opciones, valor, onChange }: {
  opciones: { val: T; label: string }[];
  valor: T;
  onChange: (v: T) => void;
}) {
  return (
    <div style={{
      display: "inline-flex", gap: 2, padding: 3,
      background: "var(--surface-2)", borderRadius: "var(--r-md)",
      border: "1px solid var(--n-200)",
    }}>
      {opciones.map(f => {
        const activo = valor === f.val;
        return (
          <button
            key={f.val}
            onClick={() => onChange(f.val)}
            style={{
              padding: "5px 12px", cursor: "pointer",
              border: "none", borderRadius: "var(--r-sm)",
              background: activo ? "var(--surface)" : "transparent",
              color: activo ? "var(--n-900)" : "var(--n-500)",
              fontWeight: activo ? 600 : 500, fontSize: 13,
              fontFamily: "var(--font-sans)",
              boxShadow: activo ? "var(--shadow-card)" : "none",
              transition: "background .12s ease, color .12s ease",
            }}
          >
            {f.label}
          </button>
        );
      })}
    </div>
  );
}

export default function FiltrosProveedores({ filtroPrecio, filtroPais, orden, total, onFiltroPrecio, onFiltroPais, onOrden }: Props) {
  return (
    <div style={{ display: "flex", flexWrap: "wrap", gap: 10, alignItems: "center", paddingBottom: 16, borderBottom: "1px solid var(--n-200)", marginBottom: 16 }}>
      <span style={{ fontSize: 13, color: "var(--n-500)", marginRight: 2 }}>{total} resultados</span>

      <Segmento<FiltroPrecio>
        valor={filtroPrecio}
        onChange={onFiltroPrecio}
        opciones={[
          { val: "todos", label: "Todos" },
          { val: "con_precio", label: "Con precio" },
          { val: "sin_precio", label: "A cotizar" },
        ]}
      />

      <Segmento<FiltroPais>
        valor={filtroPais}
        onChange={onFiltroPais}
        opciones={[
          { val: "todos", label: "Todos" },
          { val: "chile", label: "Chile" },
          { val: "internacional", label: "Internacional" },
        ]}
      />

      <select
        value={orden}
        onChange={e => onOrden(e.target.value as Orden)}
        style={{
          marginLeft: "auto",
          padding: "7px 12px", height: 36,
          fontSize: 13,
          background: "var(--surface)",
          border: "1px solid var(--n-300)",
          borderRadius: "var(--r-md)",
          color: "var(--n-700)",
          fontFamily: "var(--font-sans)",
          cursor: "pointer",
          outline: "none",
        }}
      >
        <option value="relevancia">Relevancia</option>
        <option value="precio_asc">Precio menor</option>
        <option value="precio_desc">Precio mayor</option>
      </select>
    </div>
  );
}
