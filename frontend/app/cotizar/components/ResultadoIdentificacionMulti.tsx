"use client";
/**
 * Identificación de VARIOS ítems (lista de cotización).
 * Lista expandible tipo accordion (multi-abierto). Cada bullet muestra nombre
 * completo + cantidad; al expandir se editan categorías y términos de búsqueda.
 * El usuario puede agregar ítems que el modelo no haya incluido.
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
  onConfirmar: (categoriasPorItem: string[][], nombreLista: string, cantidades: number[], itemsFinales: ItemIdentificado[]) => void;
  onCorregir: () => void;
  guardando: boolean;
  nombreListaInicial?: string;
  esProyecto?: boolean;
}

export default function ResultadoIdentificacionMulti({ items, onConfirmar, onCorregir, guardando, nombreListaInicial = "", esProyecto = false }: Props) {
  const [allItems, setAllItems] = useState<ItemIdentificado[]>(() => [...items]);
  const [nombreLista, setNombreLista] = useState(nombreListaInicial);
  const [incluidos, setIncluidos] = useState<boolean[]>(() => items.map(() => true));
  const [cats, setCats] = useState<Set<string>[]>(() =>
    items.map(it => new Set([CATEGORIAS.some(c => c.key === it.categoria) ? it.categoria : "otro"]))
  );
  const [cants, setCants] = useState<number[]>(() => items.map(it => it.cantidad ?? 1));
  const [terminos, setTerminos] = useState<string[][]>(() =>
    items.map(it => [...it.terminos_busqueda_es, ...it.terminos_busqueda_en])
  );

  // Accordion: set de índices abiertos
  const [abiertos, setAbiertos] = useState<Set<number>>(() => new Set());
  const toggleAbierto = (i: number) =>
    setAbiertos(prev => { const n = new Set(prev); n.has(i) ? n.delete(i) : n.add(i); return n; });

  // Agregar ítem
  const [mostrarFormAgregar, setMostrarFormAgregar] = useState(false);
  const [nuevoNombre, setNuevoNombre] = useState("");

  // Agregar término / categoría custom a un ítem
  const [nuevoTermino, setNuevoTermino] = useState<Record<number, string>>({});
  const [nuevaCat, setNuevaCat] = useState<Record<number, string>>({});

  const toggleCat = (idx: number, key: string) => {
    setCats(prev => prev.map((s, i) => {
      if (i !== idx) return s;
      const next = new Set(s);
      if (next.has(key)) { if (next.size > 1) next.delete(key); } else next.add(key);
      return next;
    }));
  };

  const agregarCat = (idx: number) => {
    const raw = (nuevaCat[idx] ?? "").trim();
    if (!raw) return;
    const key = raw.toLowerCase().replace(/\s+/g, "_").normalize("NFD").replace(/[̀-ͯ]/g, "");
    setCats(prev => prev.map((s, i) => {
      if (i !== idx) return s;
      return new Set(s).add(key);
    }));
    setNuevaCat(prev => ({ ...prev, [idx]: "" }));
  };

  const catLabel = (key: string) => CATEGORIAS.find(c => c.key === key)?.label ?? key;

  const quitarTermino = (idx: number, tIdx: number) => {
    setTerminos(prev => prev.map((ts, i) => i === idx ? ts.filter((_, j) => j !== tIdx) : ts));
  };

  const agregarTermino = (idx: number) => {
    const t = (nuevoTermino[idx] ?? "").trim();
    if (!t) return;
    setTerminos(prev => prev.map((ts, i) => i === idx ? [...ts, t] : ts));
    setNuevoTermino(prev => ({ ...prev, [idx]: "" }));
  };

  const agregarItem = () => {
    const nombre = nuevoNombre.trim();
    if (!nombre) return;
    const nuevo: ItemIdentificado = {
      nombre_tecnico: nombre, marca: null, numero_parte: null,
      categoria: "otro", cantidad: 1,
      terminos_busqueda_es: [nombre.toLowerCase()],
      terminos_busqueda_en: [], confianza: "medio",
    };
    const newIdx = allItems.length;
    setAllItems(prev => [...prev, nuevo]);
    setIncluidos(prev => [...prev, true]);
    setCats(prev => [...prev, new Set(["otro"])]);
    setCants(prev => [...prev, 1]);
    setTerminos(prev => [...prev, [nombre.toLowerCase()]]);
    setAbiertos(prev => new Set(prev).add(newIdx));
    setNuevoNombre("");
    setMostrarFormAgregar(false);
  };

  const totalIncluidos = incluidos.filter(Boolean).length;

  return (
    <div>
      {/* Aviso */}
      <div style={{
        background: "var(--bg-inverse)", color: "var(--text-inverse)",
        padding: "10px 16px", marginBottom: 16, fontSize: 11,
        fontFamily: "var(--font-mono)",
      }}>
        {esProyecto
          ? `Proyecto detectado — la IA armó la lista de ${allItems.length} materiales. Revisa, ajusta cantidades y quita lo que no necesites.`
          : `${allItems.length} ítems identificados — se cotizarán en paralelo como lista`}
      </div>

      {/* Nombre de la lista */}
      <div style={{ background: "var(--bg-surface)", border: "1px solid var(--border-default)", padding: "12px 16px", marginBottom: 0 }}>
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

      {/* Lista de ítems (accordion) */}
      <div style={{ border: "1px solid var(--border-default)", borderTop: "none", marginBottom: 16 }}>
        {allItems.map((it, i) => {
          const abierto = abiertos.has(i);
          const excluido = !incluidos[i];
          return (
            <div key={i} style={{ borderTop: i > 0 ? "1px solid var(--border-default)" : undefined }}>
              {/* Bullet header */}
              <button
                onClick={() => toggleAbierto(i)}
                style={{
                  width: "100%", display: "flex", alignItems: "center", gap: 10,
                  padding: "10px 16px", border: "none", cursor: "pointer",
                  background: abierto ? "var(--bg-surface)" : "var(--bg-base)",
                  fontFamily: "var(--font-mono)", textAlign: "left",
                  opacity: excluido ? 0.4 : 1,
                }}
              >
                <span style={{
                  fontSize: 10, color: "var(--text-muted)", flexShrink: 0,
                  transition: "transform 0.15s",
                  transform: abierto ? "rotate(90deg)" : "rotate(0deg)",
                }}>
                  ▶
                </span>
                <span style={{
                  fontSize: 13, fontWeight: 700, color: "var(--text-primary)",
                  flex: 1, minWidth: 0,
                  textDecoration: excluido ? "line-through" : "none",
                }}>
                  {i + 1}. {it.nombre_tecnico}
                </span>
                <span className="label" style={{
                  flexShrink: 0, padding: "2px 6px",
                  color: "var(--text-muted)",
                  border: "1px solid var(--border-default)",
                }}>
                  ×{cants[i]}
                </span>
              </button>

              {/* Panel expandido */}
              {abierto && (
                <div style={{ padding: "0 16px 16px", background: "var(--bg-surface)" }}>
                  {/* Cantidad + quitar */}
                  <div style={{ display: "flex", gap: 12, marginBottom: 14, flexWrap: "wrap", alignItems: "center" }}>
                    <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
                      <span className="label" style={{ color: "var(--text-muted)" }}>CANTIDAD</span>
                      <input
                        type="number" min={1} value={cants[i]}
                        onChange={e => {
                          const v = parseFloat(e.target.value) || 1;
                          setCants(prev => prev.map((c, j) => j === i ? v : c));
                        }}
                        style={{
                          width: 60, background: "var(--bg-base)", border: "1px solid var(--border-default)",
                          padding: "4px 8px", fontSize: 12, color: "var(--text-primary)",
                          fontFamily: "var(--font-mono)", outline: "none", textAlign: "right",
                        }}
                      />
                    </span>
                    {it.marca && <span className="label" style={{ color: "var(--text-secondary)" }}>Marca: <strong>{it.marca}</strong></span>}
                    {it.numero_parte && <span className="label" style={{ color: "var(--text-secondary)" }}>N/P: <strong>{it.numero_parte}</strong></span>}
                    <button
                      onClick={() => setIncluidos(prev => prev.map((v, j) => j === i ? !v : v))}
                      disabled={incluidos[i] && totalIncluidos <= 1}
                      className="label"
                      style={{
                        marginLeft: "auto",
                        color: incluidos[i] ? "var(--text-error)" : "var(--text-success)",
                        border: `1px solid ${incluidos[i] ? "var(--border-accent)" : "var(--palette-green-500)"}`,
                        background: "none", padding: "3px 8px", cursor: "pointer",
                        fontFamily: "var(--font-mono)", whiteSpace: "nowrap",
                      }}
                    >
                      {incluidos[i] ? "× Quitar" : "↩ Incluir"}
                    </button>
                  </div>

                  {/* Categorías */}
                  <div style={{ marginBottom: 14 }}>
                    <div className="label" style={{ color: "var(--text-muted)", marginBottom: 6 }}>CATEGORÍAS</div>
                    <div style={{ display: "flex", flexWrap: "wrap", gap: 4, alignItems: "center" }}>
                      {CATEGORIAS.map(c => {
                        const activa = cats[i].has(c.key);
                        return (
                          <button
                            key={c.key}
                            onClick={() => toggleCat(i, c.key)}
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
                      {/* Categorías custom (no están en CATEGORIAS) */}
                      {Array.from(cats[i]).filter(k => !CATEGORIAS.some(c => c.key === k)).map(k => (
                        <span key={k} style={{
                          display: "inline-flex", alignItems: "center", gap: 4,
                          fontSize: 10, fontWeight: 700, letterSpacing: "0.04em",
                          textTransform: "uppercase",
                          color: "var(--text-inverse)", background: "var(--accent)",
                          padding: "4px 4px 4px 10px", fontFamily: "var(--font-mono)",
                        }}>
                          {k}
                          <button
                            onClick={() => toggleCat(i, k)}
                            style={{
                              background: "none", border: "none", cursor: "pointer",
                              color: "var(--text-inverse)", fontSize: 12, padding: "0 2px",
                              fontFamily: "var(--font-mono)", lineHeight: 1, opacity: 0.7,
                            }}
                          >×</button>
                        </span>
                      ))}
                      {/* Input agregar categoría */}
                      <span style={{ display: "inline-flex", alignItems: "center", gap: 2 }}>
                        <input
                          type="text"
                          value={nuevaCat[i] ?? ""}
                          onChange={e => setNuevaCat(prev => ({ ...prev, [i]: e.target.value }))}
                          onKeyDown={e => { if (e.key === "Enter") agregarCat(i); }}
                          placeholder="+ agregar"
                          style={{
                            width: 100, background: "var(--bg-base)", border: "1px dashed var(--border-default)",
                            padding: "4px 8px", fontSize: 10, color: "var(--text-primary)",
                            fontFamily: "var(--font-mono)", outline: "none",
                            fontWeight: 700, letterSpacing: "0.04em",
                          }}
                        />
                        {(nuevaCat[i] ?? "").trim() && (
                          <button
                            onClick={() => agregarCat(i)}
                            style={{
                              background: "var(--bg-inverse)", border: "none", cursor: "pointer",
                              color: "var(--text-inverse)", fontSize: 10, padding: "4px 8px",
                              fontFamily: "var(--font-mono)", fontWeight: 700,
                            }}
                          >+</button>
                        )}
                      </span>
                    </div>
                  </div>

                  {/* Términos de búsqueda */}
                  <div>
                    <div className="label" style={{ color: "var(--text-muted)", marginBottom: 6 }}>TÉRMINOS DE BÚSQUEDA</div>
                    <div style={{ display: "flex", flexWrap: "wrap", gap: 4, alignItems: "center" }}>
                      {terminos[i].map((t, tIdx) => (
                        <span key={tIdx} style={{
                          display: "inline-flex", alignItems: "center", gap: 4,
                          fontSize: 10, fontWeight: 700, letterSpacing: "0.04em",
                          textTransform: "uppercase",
                          color: "var(--text-secondary)", background: "var(--bg-base)",
                          border: "1px solid var(--border-default)", padding: "3px 4px 3px 8px",
                          fontFamily: "var(--font-mono)",
                        }}>
                          {t}
                          <button
                            onClick={() => quitarTermino(i, tIdx)}
                            style={{
                              background: "none", border: "none", cursor: "pointer",
                              color: "var(--text-muted)", fontSize: 12, padding: "0 2px",
                              fontFamily: "var(--font-mono)", lineHeight: 1,
                            }}
                            title="Quitar término"
                          >
                            ×
                          </button>
                        </span>
                      ))}
                      {/* Input para agregar término */}
                      <span style={{ display: "inline-flex", alignItems: "center", gap: 2 }}>
                        <input
                          type="text"
                          value={nuevoTermino[i] ?? ""}
                          onChange={e => setNuevoTermino(prev => ({ ...prev, [i]: e.target.value }))}
                          onKeyDown={e => { if (e.key === "Enter") agregarTermino(i); }}
                          placeholder="+ agregar"
                          style={{
                            width: 110, background: "var(--bg-base)", border: "1px dashed var(--border-default)",
                            padding: "3px 8px", fontSize: 10, color: "var(--text-primary)",
                            fontFamily: "var(--font-mono)", outline: "none",
                            fontWeight: 700, letterSpacing: "0.04em",
                          }}
                        />
                        {(nuevoTermino[i] ?? "").trim() && (
                          <button
                            onClick={() => agregarTermino(i)}
                            style={{
                              background: "var(--bg-inverse)", border: "none", cursor: "pointer",
                              color: "var(--text-inverse)", fontSize: 10, padding: "3px 8px",
                              fontFamily: "var(--font-mono)", fontWeight: 700,
                            }}
                          >
                            +
                          </button>
                        )}
                      </span>
                    </div>
                  </div>
                </div>
              )}
            </div>
          );
        })}

        {/* Botón agregar ítem */}
        <div style={{ borderTop: "1px solid var(--border-default)" }}>
          {!mostrarFormAgregar ? (
            <button
              onClick={() => setMostrarFormAgregar(true)}
              style={{
                width: "100%", display: "flex", alignItems: "center", gap: 10,
                padding: "10px 16px", border: "none", cursor: "pointer",
                background: "var(--bg-base)", fontFamily: "var(--font-mono)", textAlign: "left",
              }}
            >
              <span style={{ fontSize: 12, color: "var(--accent)", fontWeight: 700 }}>+</span>
              <span style={{ fontSize: 12, color: "var(--accent)", fontWeight: 700 }}>Agregar ítem</span>
            </button>
          ) : (
            <div style={{ padding: "10px 16px", background: "var(--bg-surface)", display: "flex", gap: 8, alignItems: "center" }}>
              <input
                type="text"
                value={nuevoNombre}
                onChange={e => setNuevoNombre(e.target.value)}
                onKeyDown={e => { if (e.key === "Enter") agregarItem(); if (e.key === "Escape") { setMostrarFormAgregar(false); setNuevoNombre(""); } }}
                placeholder="Nombre del ítem…"
                autoFocus
                style={{
                  flex: 1, background: "var(--bg-base)", border: "1px solid var(--border-default)",
                  padding: "8px 12px", fontSize: 12, color: "var(--text-primary)",
                  fontFamily: "var(--font-mono)", outline: "none",
                }}
              />
              <button onClick={agregarItem} disabled={!nuevoNombre.trim()} className="btn-swiss-primary" style={{ padding: "8px 14px", whiteSpace: "nowrap" }}>
                Agregar
              </button>
              <button onClick={() => { setMostrarFormAgregar(false); setNuevoNombre(""); }} style={{
                background: "none", border: "none", cursor: "pointer",
                color: "var(--text-muted)", fontSize: 14, fontFamily: "var(--font-mono)", padding: "4px 8px",
              }}>
                ×
              </button>
            </div>
          )}
        </div>
      </div>

      {/* Acciones */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 2fr", gap: 8 }}>
        <button onClick={onCorregir} className="btn-swiss-secondary" style={{ padding: 12 }}>
          Corregir
        </button>
        <button
          onClick={() => {
            const idx = allItems.map((_, i) => i).filter(i => incluidos[i]);
            const itemsConTerminos = idx.map(i => ({
              ...allItems[i],
              terminos_busqueda_es: terminos[i],
              terminos_busqueda_en: [],
            }));
            onConfirmar(
              idx.map(i => Array.from(cats[i])),
              nombreLista.trim(),
              idx.map(i => cants[i]),
              itemsConTerminos,
            );
          }}
          disabled={guardando}
          className={guardando ? "btn-swiss-secondary" : "btn-swiss-primary"}
          style={{ padding: 12 }}
        >
          {guardando ? "Creando lista..." : `Crear lista y cotizar ${totalIncluidos} ítems →`}
        </button>
      </div>
    </div>
  );
}
