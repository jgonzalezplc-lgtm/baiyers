"use client";
/**
 * Identificación de VARIOS ítems (lista de cotización).
 * Una pestaña por ítem; en cada una se puede ajustar la categoría.
 * Al confirmar se crean N cotizaciones + la lista, y se cotiza ítem por ítem.
 */
import { useState } from "react";
import { CATEGORIAS } from "./ResultadoIdentificacion";

export interface ItemIdentificado {
  nombre_tecnico: string;
  marca: string | null;
  numero_parte: string | null;
  categoria: string;
  cantidad?: number;
  terminos_busqueda_es: string[];
  terminos_busqueda_en: string[];
  confianza: "alto" | "medio" | "bajo";
}

interface Props {
  items: ItemIdentificado[];
  // categorías/cantidades ya filtradas a los ítems incluidos; indices apunta a `items`
  onConfirmar: (categoriasPorItem: string[][], nombreLista: string, cantidades: number[], indices: number[]) => void;
  onCorregir: () => void;
  guardando: boolean;
  nombreListaInicial?: string;
  // true cuando el usuario describió un objetivo y la IA generó la lista de materiales
  esProyecto?: boolean;
}

const CONF_COLOR: Record<string, string> = {
  alto: "var(--text-success)", medio: "var(--text-warning)", bajo: "var(--text-error)",
};

export default function ResultadoIdentificacionMulti({ items, onConfirmar, onCorregir, guardando, nombreListaInicial = "", esProyecto = false }: Props) {
  const [tab, setTab] = useState(0);
  const [nombreLista, setNombreLista] = useState(nombreListaInicial);
  // ítems incluidos en la lista (en proyectos se pueden descartar sugerencias)
  const [incluidos, setIncluidos] = useState<boolean[]>(() => items.map(() => true));
  // categorías seleccionadas por ítem (parte con la detectada por la IA)
  const [cats, setCats] = useState<Set<string>[]>(() =>
    items.map(it => new Set([CATEGORIAS.some(c => c.key === it.categoria) ? it.categoria : "otro"]))
  );
  // cantidades por ítem (parte con las detectadas por la IA en el prompt)
  const [cants, setCants] = useState<number[]>(() => items.map(it => it.cantidad ?? 1));

  const toggleCat = (idx: number, key: string) => {
    setCats(prev => prev.map((s, i) => {
      if (i !== idx) return s;
      const next = new Set(s);
      if (next.has(key)) { if (next.size > 1) next.delete(key); } else next.add(key);
      return next;
    }));
  };

  const item = items[tab];

  return (
    <div>
      {/* Aviso de lista */}
      <div style={{
        background: "var(--bg-inverse)", color: "var(--text-inverse)",
        padding: "10px 16px", marginBottom: 16, fontSize: 11,
        display: "flex", justifyContent: "space-between", alignItems: "center",
        fontFamily: "var(--font-mono)",
      }}>
        <span>
          {esProyecto
            ? `Proyecto detectado — la IA armó la lista de ${items.length} materiales. Revisa, ajusta cantidades y quita lo que no necesites.`
            : `${items.length} ítems identificados — se cotizarán en paralelo como lista`}
        </span>
      </div>

      {/* Nombre de la lista */}
      <div style={{ background: "var(--bg-surface)", border: "1px solid var(--border-default)", padding: "12px 16px", marginBottom: 16 }}>
        <div className="label" style={{ color: "var(--text-muted)", marginBottom: 6 }}>
          Nombre de la lista de cotización / proyecto
        </div>
        <input
          type="text"
          value={nombreLista}
          onChange={e => setNombreLista(e.target.value)}
          placeholder={`Ej: "Compra materiales ${new Date().toLocaleDateString("es-CL", { month: "long" })}"`}
          style={{
            width: "100%", boxSizing: "border-box",
            background: "var(--bg-base)", border: "1px solid var(--border-default)",
            padding: "8px 12px", fontSize: 11, color: "var(--text-primary)",
            fontFamily: "var(--font-mono)", outline: "none",
          }}
        />
      </div>

      {/* Tabs por ítem */}
      <div style={{ display: "flex", flexWrap: "wrap", borderBottom: "1px solid var(--border-default)", background: "var(--bg-surface)" }}>
        {items.map((it, i) => (
          <button
            key={i}
            onClick={() => setTab(i)}
            className="label"
            style={{
              padding: "8px 14px", cursor: "pointer", border: "none",
              background: tab === i ? "var(--bg-inverse)" : "transparent",
              color: tab === i ? "var(--text-inverse)" : "var(--text-muted)",
              fontFamily: "var(--font-mono)", fontWeight: 700,
              textDecoration: incluidos[i] ? "none" : "line-through",
              opacity: incluidos[i] ? 1 : 0.45,
            }}
          >
            {i + 1}. {it.nombre_tecnico.length > 22 ? it.nombre_tecnico.slice(0, 22) + "…" : it.nombre_tecnico}{cants[i] > 1 ? ` ×${cants[i]}` : ""}
          </button>
        ))}
      </div>

      {/* Detalle del ítem activo */}
      <div style={{ background: "var(--bg-surface)", border: "1px solid var(--border-default)", borderTop: "none", padding: 20, marginBottom: 16 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 14 }}>
          <h2 style={{ fontSize: 16, fontWeight: 800, color: "var(--text-primary)", margin: 0 }}>
            {item.nombre_tecnico}
          </h2>
          <span style={{ display: "inline-flex", gap: 6, alignItems: "center" }}>
            <span className="label" style={{
              color: CONF_COLOR[item.confianza] ?? "var(--text-muted)",
              border: `1px solid ${CONF_COLOR[item.confianza] ?? "var(--text-muted)"}`,
              padding: "3px 8px", whiteSpace: "nowrap",
            }}>
              {item.confianza.toUpperCase()}
            </span>
            <button
              onClick={() => setIncluidos(prev => prev.map((v, i) => (i === tab ? !v : v)))}
              disabled={incluidos[tab] && incluidos.filter(Boolean).length <= 1}
              className="label"
              title={incluidos[tab] ? "Quitar este ítem de la lista" : "Volver a incluir"}
              style={{
                color: incluidos[tab] ? "var(--text-error)" : "var(--text-success)",
                border: `1px solid ${incluidos[tab] ? "var(--border-accent)" : "var(--palette-green-500)"}`,
                background: "none", padding: "3px 8px", cursor: "pointer",
                fontFamily: "var(--font-mono)", whiteSpace: "nowrap",
              }}
            >
              {incluidos[tab] ? "× Quitar" : "↩ Incluir"}
            </button>
          </span>
        </div>

        <div style={{ display: "flex", gap: 16, marginBottom: 14, flexWrap: "wrap", alignItems: "center" }}>
          <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
            <span className="label" style={{ color: "var(--text-muted)" }}>CANTIDAD</span>
            <input
              type="number"
              min={1}
              value={cants[tab]}
              onChange={e => {
                const v = parseFloat(e.target.value) || 1;
                setCants(prev => prev.map((c, i) => (i === tab ? v : c)));
              }}
              style={{
                width: 60, background: "var(--bg-base)", border: "1px solid var(--border-default)",
                padding: "4px 8px", fontSize: 12, color: "var(--text-primary)",
                fontFamily: "var(--font-mono)", outline: "none", textAlign: "right",
              }}
            />
          </span>
          {item.marca && <span className="label" style={{ color: "var(--text-secondary)" }}>Marca: <strong>{item.marca}</strong></span>}
          {item.numero_parte && <span className="label" style={{ color: "var(--text-secondary)" }}>N/P: <strong>{item.numero_parte}</strong></span>}
        </div>

        <div style={{ marginBottom: 14 }}>
          <div className="label" style={{ color: "var(--text-muted)", marginBottom: 8 }}>
            Categorías — orientan la búsqueda de este ítem
          </div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
            {CATEGORIAS.map(c => {
              const activa = cats[tab].has(c.key);
              return (
                <button
                  key={c.key}
                  onClick={() => toggleCat(tab, c.key)}
                  className="label"
                  style={{
                    color: activa ? "var(--text-inverse)" : "var(--text-secondary)",
                    background: activa ? "var(--bg-inverse)" : "var(--bg-base)",
                    border: `1px solid ${activa ? "var(--border-strong)" : "var(--border-default)"}`,
                    padding: "4px 10px", cursor: "pointer", fontFamily: "var(--font-mono)",
                  }}
                >
                  {activa ? "✓ " : ""}{c.label}
                </button>
              );
            })}
          </div>
        </div>

        <div>
          <div className="label" style={{ color: "var(--text-muted)", marginBottom: 6 }}>Términos de búsqueda</div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
            {[...item.terminos_busqueda_es, ...item.terminos_busqueda_en].map((t, i) => (
              <span key={i} className="label" style={{
                color: "var(--text-secondary)", background: "var(--bg-base)",
                border: "1px solid var(--border-default)", padding: "3px 8px",
              }}>{t}</span>
            ))}
          </div>
        </div>
      </div>

      {/* Acciones */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 2fr", gap: 8 }}>
        <button onClick={onCorregir} className="btn-swiss-secondary" style={{ padding: 12 }}>
          Corregir
        </button>
        <button
          onClick={() => {
            const idx = items.map((_, i) => i).filter(i => incluidos[i]);
            onConfirmar(
              idx.map(i => Array.from(cats[i])),
              nombreLista.trim(),
              idx.map(i => cants[i]),
              idx,
            );
          }}
          disabled={guardando}
          className={guardando ? "btn-swiss-secondary" : "btn-swiss-primary"}
          style={{ padding: 12 }}
        >
          {guardando ? "Creando lista..." : `Crear lista y cotizar ${incluidos.filter(Boolean).length} ítems →`}
        </button>
      </div>
    </div>
  );
}
