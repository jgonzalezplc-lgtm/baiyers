"use client";
/**
 * Identificación de VARIOS ítems (lista de cotización).
 * Lista expandible tipo accordion (multi-abierto) con animación suave tipo iOS.
 * Cada bullet muestra nombre completo + cantidad; al expandir se editan
 * categorías y términos de búsqueda. El usuario puede agregar ítems que el
 * modelo no haya incluido.
 */
import { useState, useEffect } from "react";
import { ChevronRight, Plus, X, Undo2, Calculator } from "lucide-react";
import { CATEGORIAS } from "./ResultadoIdentificacion";

export interface ItemIdentificado {
  nombre_tecnico: string;
  marca: string | null;
  numero_parte: string | null;
  categoria: string;
  cantidad?: number;
  unidad?: string;
  partida?: string | null;
  terminos_busqueda_es: string[];
  terminos_busqueda_en: string[];
  confianza: "alto" | "medio" | "bajo";
  cubicacion?: {
    cantidad_neta: number; unidad: string; cantidad_compra: number;
    unidad_compra: string; cantidad_comercial: number; calculo: string;
    supuestos?: string[]; advertencias?: string[];
  };
}

interface Props {
  items: ItemIdentificado[];
  onConfirmar: (categoriasPorItem: string[][], nombreLista: string, cantidades: number[], unidades: string[], itemsFinales: ItemIdentificado[]) => void;
  onCorregir: () => void;
  guardando: boolean;
  nombreListaInicial?: string;
  esProyecto?: boolean;
}

export default function ResultadoIdentificacionMulti({ items, onConfirmar, onCorregir, guardando, nombreListaInicial = "" }: Props) {
  const [allItems, setAllItems] = useState<ItemIdentificado[]>(() => [...items]);
  const [nombreLista, setNombreLista] = useState(nombreListaInicial);
  const [incluidos, setIncluidos] = useState<boolean[]>(() => items.map(() => true));
  const [cats, setCats] = useState<Set<string>[]>(() =>
    items.map(it => new Set([CATEGORIAS.some(c => c.key === it.categoria) ? it.categoria : "otro"]))
  );
  const [cants, setCants] = useState<number[]>(() => items.map(it => it.cantidad ?? 1));
  const [unidades, setUnidades] = useState<string[]>(() => items.map(it => it.unidad ?? ""));
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

  // Categorías: mostrar solo las activas; "+" despliega las demás
  const [catsAbierto, setCatsAbierto] = useState<Record<number, boolean>>({});
  const toggleCatsAbierto = (i: number) => setCatsAbierto(prev => ({ ...prev, [i]: !prev[i] }));

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
    setCats(prev => prev.map((s, i) => i === idx ? new Set(s).add(key) : s));
    setNuevaCat(prev => ({ ...prev, [idx]: "" }));
  };

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
      categoria: "otro", cantidad: 1, unidad: "unidad", partida: null,
      terminos_busqueda_es: [nombre.toLowerCase()],
      terminos_busqueda_en: [], confianza: "medio",
    };
    const newIdx = allItems.length;
    setAllItems(prev => [...prev, nuevo]);
    setIncluidos(prev => [...prev, true]);
    setCats(prev => [...prev, new Set(["otro"])]);
    setCants(prev => [...prev, 1]);
    setUnidades(prev => [...prev, "unidad"]);
    setTerminos(prev => [...prev, [nombre.toLowerCase()]]);
    setAbiertos(prev => new Set(prev).add(newIdx));
    setNuevoNombre("");
    setMostrarFormAgregar(false);
  };

  const totalIncluidos = incluidos.filter(Boolean).length;

  // Sincroniza el nombre de la lista con el breadcrumb superior (AppShell)
  useEffect(() => {
    window.dispatchEvent(new CustomEvent("baiyer:breadcrumb", { detail: nombreLista.trim() || null }));
  }, [nombreLista]);
  useEffect(() => () => {
    window.dispatchEvent(new CustomEvent("baiyer:breadcrumb", { detail: null }));
  }, []);

  // ── Estilos reutilizables ──
  const chipInput: React.CSSProperties = {
    background: "var(--surface)", border: "1px dashed var(--n-300)",
    borderRadius: "var(--r-pill)", padding: "5px 12px", fontSize: 13,
    color: "var(--n-900)", fontFamily: "var(--font-sans)", outline: "none",
  };

  return (
    <div>
      {/* Título editable estilo Notion */}
      <div style={{ marginBottom: 8 }}>
        <input
          type="text"
          value={nombreLista}
          onChange={e => setNombreLista(e.target.value)}
          placeholder="Lista sin nombre"
          aria-label="Nombre de la lista"
          style={{
            width: "100%", boxSizing: "border-box",
            background: "transparent", border: "none", outline: "none",
            padding: "4px 6px", borderRadius: "var(--r-md)",
            fontFamily: "var(--font-sans)", fontSize: 32, fontWeight: 700,
            letterSpacing: "-0.02em", color: "var(--n-900)", textAlign: "center",
          }}
          onFocus={e => { e.currentTarget.style.background = "var(--surface-2)"; }}
          onBlur={e => { e.currentTarget.style.background = "transparent"; }}
        />
      </div>

      {/* Lista de ítems (accordion) */}
      <div style={{
        border: "1px solid var(--n-200)", borderRadius: "var(--r-lg)",
        overflow: "hidden", marginBottom: 16, background: "var(--surface)",
      }}>
        {allItems.map((it, i) => {
          const abierto = abiertos.has(i);
          const excluido = !incluidos[i];
          return (
            <div key={i} style={{ borderTop: i > 0 ? "1px solid var(--n-200)" : undefined }}>
              {/* Bullet header */}
              <button
                onClick={() => toggleAbierto(i)}
                style={{
                  width: "100%", display: "flex", alignItems: "center", gap: 12,
                  padding: "13px 16px", border: "none", cursor: "pointer",
                  background: abierto ? "var(--surface-2)" : "var(--surface)",
                  textAlign: "left", fontFamily: "var(--font-sans)",
                  opacity: excluido ? 0.45 : 1,
                  transition: "background .15s ease",
                }}
              >
                <ChevronRight
                  size={17} strokeWidth={2}
                  style={{
                    color: "var(--n-400)", flexShrink: 0,
                    transition: "transform .3s cubic-bezier(.4,0,.2,1)",
                    transform: abierto ? "rotate(90deg)" : "rotate(0deg)",
                  }}
                />
                <span style={{
                  fontSize: 14.5, fontWeight: 600, color: "var(--n-900)",
                  flex: 1, minWidth: 0,
                  textDecoration: excluido ? "line-through" : "none",
                }}>
                  {i + 1}. {it.nombre_tecnico}
                </span>
                <span style={{
                  flexShrink: 0, padding: "3px 9px", borderRadius: "var(--r-pill)",
                  fontSize: 12.5, fontWeight: 600, color: "var(--n-600)",
                  background: "var(--n-100)",
                  fontFamily: "var(--font-mono)", fontVariantNumeric: "tabular-nums",
                }}>
                  {cants[i]} {unidades[i] || "sin unidad"}
                </span>
              </button>

              {/* Panel expandido (animación iOS) */}
              <div className={`acc-panel${abierto ? " open" : ""}`}>
                <div className="acc-inner">
                  <div style={{ padding: "4px 16px 18px", background: "var(--surface-2)" }}>
                    {it.partida && <div className="label" style={{ marginBottom: 10 }}>{it.partida}</div>}
                    {/* Cantidad, unidad + quitar */}
                    <div style={{ display: "flex", gap: 14, marginBottom: 16, flexWrap: "wrap", alignItems: "center" }}>
                      <span style={{ display: "inline-flex", alignItems: "center", gap: 8 }}>
                        <span style={{ fontSize: 13, color: "var(--n-600)" }}>Cantidad</span>
                        <input
                          type="number" min={1} value={cants[i]}
                          onChange={e => {
                            const v = parseFloat(e.target.value) || 1;
                            setCants(prev => prev.map((c, j) => j === i ? v : c));
                          }}
                          style={{
                            width: 64, background: "var(--surface)", border: "1px solid var(--n-300)",
                            borderRadius: "var(--r-sm)", padding: "6px 8px", fontSize: 13,
                            color: "var(--n-900)", fontFamily: "var(--font-mono)",
                            fontVariantNumeric: "tabular-nums", outline: "none", textAlign: "right",
                          }}
                        />
                      </span>
                      <span style={{ display: "inline-flex", alignItems: "center", gap: 8 }}>
                        <span style={{ fontSize: 13, color: "var(--n-600)" }}>Unidad</span>
                        <input
                          type="text" value={unidades[i]}
                          onChange={e => setUnidades(prev => prev.map((u, j) => j === i ? e.target.value : u))}
                          placeholder="kg, m, un…"
                          style={{ width: 100, background: "var(--surface)", border: "1px solid var(--n-300)", padding: "6px 8px", fontSize: 13, color: "var(--n-900)" }}
                        />
                      </span>
                      {it.marca && <span style={{ fontSize: 13, color: "var(--n-600)" }}>Marca: <strong style={{ color: "var(--n-900)" }}>{it.marca}</strong></span>}
                      {it.numero_parte && <span style={{ fontSize: 13, color: "var(--n-600)" }}>N/P: <strong style={{ color: "var(--n-900)" }}>{it.numero_parte}</strong></span>}
                      <button
                        onClick={() => setIncluidos(prev => prev.map((v, j) => j === i ? !v : v))}
                        disabled={incluidos[i] && totalIncluidos <= 1}
                        style={{
                          marginLeft: "auto",
                          display: "inline-flex", alignItems: "center", gap: 6,
                          color: incluidos[i] ? "var(--danger)" : "var(--success)",
                          border: `1px solid ${incluidos[i] ? "var(--danger)" : "var(--success)"}`,
                          background: "var(--surface)", padding: "5px 12px", cursor: "pointer",
                          borderRadius: "var(--r-md)", fontSize: 13, fontWeight: 500,
                          fontFamily: "var(--font-sans)", whiteSpace: "nowrap",
                          opacity: incluidos[i] && totalIncluidos <= 1 ? 0.4 : 1,
                        }}
                      >
                        {incluidos[i] ? <><X size={14} strokeWidth={2} /> Quitar</> : <><Undo2 size={14} strokeWidth={2} /> Incluir</>}
                      </button>
                    </div>

                    {it.cubicacion && (
                      <div style={{ marginBottom: 16, padding: 14, border: "1px solid var(--brand-100)", borderRadius: "var(--r-md)", background: "var(--brand-50)" }}>
                        <div style={{ display: "flex", alignItems: "center", gap: 7, color: "var(--brand-700)", fontSize: 13, fontWeight: 600, marginBottom: 8 }}><Calculator size={16} /> Cubicación</div>
                        <div style={{ fontSize: 13, color: "var(--n-800)" }}>Neto: {it.cubicacion.cantidad_neta} {it.cubicacion.unidad} · Compra: {it.cubicacion.cantidad_compra} {it.cubicacion.unidad_compra} ({it.cubicacion.cantidad_comercial} {it.cubicacion.unidad})</div>
                        <div style={{ fontSize: 12, color: "var(--n-600)", marginTop: 5 }}>{it.cubicacion.calculo}</div>
                        {!!it.cubicacion.supuestos?.length && <div style={{ fontSize: 12, color: "var(--n-600)", marginTop: 8 }}><strong>Supuestos:</strong> {it.cubicacion.supuestos.join(" · ")}</div>}
                        {!!it.cubicacion.advertencias?.length && <div style={{ fontSize: 12, color: "var(--warning)", marginTop: 8 }}>{it.cubicacion.advertencias.join(" · ")}</div>}
                      </div>
                    )}

                    {/* Categorías: activas visibles; "+" despliega las demás */}
                    {(() => {
                      const disponibles = CATEGORIAS.filter(c => !cats[i].has(c.key));
                      const custom = Array.from(cats[i]).filter(k => !CATEGORIAS.some(c => c.key === k));
                      const catsOpen = !!catsAbierto[i];
                      return (
                        <div style={{ marginBottom: 16 }}>
                          <div style={{ fontSize: 13, fontWeight: 500, color: "var(--n-700)", marginBottom: 8 }}>Categorías</div>
                          <div style={{ display: "flex", flexWrap: "wrap", gap: 6, alignItems: "center" }}>
                            {/* Activas (predefinidas) */}
                            {CATEGORIAS.filter(c => cats[i].has(c.key)).map(c => (
                              <button
                                key={c.key}
                                onClick={() => toggleCat(i, c.key)}
                                style={{
                                  display: "inline-flex", alignItems: "center", gap: 6,
                                  color: "#fff", background: "var(--brand)", border: "1px solid var(--brand)",
                                  borderRadius: "var(--r-pill)", padding: "5px 10px 5px 12px",
                                  cursor: "pointer", fontSize: 13, fontWeight: 500, fontFamily: "var(--font-sans)",
                                }}
                              >
                                {c.label}
                                <X size={13} strokeWidth={2.5} style={{ opacity: 0.8 }} />
                              </button>
                            ))}
                            {/* Activas custom */}
                            {custom.map(k => (
                              <button
                                key={k}
                                onClick={() => toggleCat(i, k)}
                                style={{
                                  display: "inline-flex", alignItems: "center", gap: 6,
                                  color: "#fff", background: "var(--brand)", border: "1px solid var(--brand)",
                                  borderRadius: "var(--r-pill)", padding: "5px 10px 5px 12px",
                                  cursor: "pointer", fontSize: 13, fontWeight: 500, fontFamily: "var(--font-sans)",
                                }}
                              >
                                {k}
                                <X size={13} strokeWidth={2.5} style={{ opacity: 0.8 }} />
                              </button>
                            ))}
                            {/* Botón desplegar / colapsar */}
                            {disponibles.length > 0 && (
                              <button
                                onClick={() => toggleCatsAbierto(i)}
                                style={{
                                  display: "inline-flex", alignItems: "center", gap: 5,
                                  color: "var(--brand)", background: "var(--brand-50)",
                                  border: "1px solid var(--brand-100)", borderRadius: "var(--r-pill)",
                                  padding: "5px 12px", cursor: "pointer", fontSize: 13, fontWeight: 500,
                                  fontFamily: "var(--font-sans)",
                                }}
                              >
                                <Plus size={14} strokeWidth={2.25} style={{
                                  transition: "transform .3s cubic-bezier(.4,0,.2,1)",
                                  transform: catsOpen ? "rotate(45deg)" : "rotate(0deg)",
                                }} />
                                {catsOpen ? "Menos" : `${disponibles.length} más`}
                              </button>
                            )}
                          </div>

                          {/* Panel animado con las categorías disponibles + agregar */}
                          <div className={`acc-panel${catsOpen ? " open" : ""}`}>
                            <div className="acc-inner">
                              <div style={{ display: "flex", flexWrap: "wrap", gap: 6, alignItems: "center", paddingTop: 8 }}>
                                {disponibles.map(c => (
                                  <button
                                    key={c.key}
                                    onClick={() => toggleCat(i, c.key)}
                                    style={{
                                      color: "var(--n-600)", background: "var(--surface)",
                                      border: "1px solid var(--n-300)", borderRadius: "var(--r-pill)",
                                      padding: "5px 12px", cursor: "pointer", fontSize: 13, fontWeight: 500,
                                      fontFamily: "var(--font-sans)",
                                    }}
                                  >
                                    {c.label}
                                  </button>
                                ))}
                                <input
                                  type="text"
                                  value={nuevaCat[i] ?? ""}
                                  onChange={e => setNuevaCat(prev => ({ ...prev, [i]: e.target.value }))}
                                  onKeyDown={e => { if (e.key === "Enter") agregarCat(i); }}
                                  placeholder="+ agregar"
                                  style={{ ...chipInput, width: 110 }}
                                />
                              </div>
                            </div>
                          </div>
                        </div>
                      );
                    })()}

                    {/* Términos de búsqueda */}
                    <div>
                      <div style={{ fontSize: 13, fontWeight: 500, color: "var(--n-700)", marginBottom: 8 }}>Términos de búsqueda</div>
                      <div style={{ display: "flex", flexWrap: "wrap", gap: 6, alignItems: "center" }}>
                        {terminos[i].map((t, tIdx) => (
                          <span key={tIdx} style={{
                            display: "inline-flex", alignItems: "center", gap: 6,
                            fontSize: 13, color: "var(--n-700)", background: "var(--surface)",
                            border: "1px solid var(--n-200)", borderRadius: "var(--r-pill)",
                            padding: "5px 8px 5px 12px",
                          }}>
                            {t}
                            <button
                              onClick={() => quitarTermino(i, tIdx)}
                              title="Quitar término"
                              style={{ background: "none", border: "none", cursor: "pointer", color: "var(--n-400)", display: "inline-flex", padding: 0 }}
                            ><X size={13} strokeWidth={2.5} /></button>
                          </span>
                        ))}
                        <input
                          type="text"
                          value={nuevoTermino[i] ?? ""}
                          onChange={e => setNuevoTermino(prev => ({ ...prev, [i]: e.target.value }))}
                          onKeyDown={e => { if (e.key === "Enter") agregarTermino(i); }}
                          placeholder="+ agregar"
                          style={{ ...chipInput, width: 120 }}
                        />
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          );
        })}

        {/* Botón agregar ítem */}
        <div style={{ borderTop: "1px solid var(--n-200)" }}>
          {!mostrarFormAgregar ? (
            <button
              onClick={() => setMostrarFormAgregar(true)}
              style={{
                width: "100%", display: "flex", alignItems: "center", gap: 8,
                padding: "13px 16px", border: "none", cursor: "pointer",
                background: "var(--surface)", fontFamily: "var(--font-sans)", textAlign: "left",
                color: "var(--brand)", fontSize: 14, fontWeight: 500,
              }}
            >
              <Plus size={17} strokeWidth={2} />
              Agregar ítem
            </button>
          ) : (
            <div style={{ padding: "12px 16px", background: "var(--surface-2)", display: "flex", gap: 8, alignItems: "center" }}>
              <input
                type="text"
                value={nuevoNombre}
                onChange={e => setNuevoNombre(e.target.value)}
                onKeyDown={e => { if (e.key === "Enter") agregarItem(); if (e.key === "Escape") { setMostrarFormAgregar(false); setNuevoNombre(""); } }}
                placeholder="Nombre del ítem…"
                autoFocus
                style={{
                  flex: 1, background: "var(--surface)", border: "1px solid var(--n-300)",
                  borderRadius: "var(--r-md)", padding: "9px 12px", fontSize: 14,
                  color: "var(--n-900)", fontFamily: "var(--font-sans)", outline: "none",
                }}
              />
              <button onClick={agregarItem} disabled={!nuevoNombre.trim()} className="btn-swiss-primary" style={{ whiteSpace: "nowrap" }}>
                Agregar
              </button>
              <button onClick={() => { setMostrarFormAgregar(false); setNuevoNombre(""); }} style={{
                background: "none", border: "none", cursor: "pointer",
                color: "var(--n-500)", display: "inline-flex", padding: 6,
              }}>
                <X size={18} strokeWidth={2} />
              </button>
            </div>
          )}
        </div>
      </div>

      {/* Acciones */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 2fr", gap: 10 }}>
        <button onClick={onCorregir} className="btn-swiss-secondary">
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
              idx.map(i => unidades[i].trim()),
              itemsConTerminos,
            );
          }}
          disabled={guardando || incluidos.some((incluido, i) => incluido && (!(cants[i] > 0) || !unidades[i].trim()))}
          className="btn-swiss-primary"
        >
          {guardando ? "Creando lista…" : `Crear lista y cotizar ${totalIncluidos} ítems →`}
        </button>
      </div>
    </div>
  );
}
