"use client";
import { useState } from "react";

interface Resultado {
  nombre_tecnico: string;
  marca: string | null;
  numero_parte: string | null;
  categoria: string;
  terminos_busqueda_es: string[];
  terminos_busqueda_en: string[];
  confianza: "alto" | "medio" | "bajo";
}

interface Props {
  resultado: Resultado;
  onConfirmar: (categorias: string[], nombreLista: string) => void;
  onCorregir: () => void;
  guardando: boolean;
  isLoggedIn: boolean;
}

const CONFIANZA_COLOR: Record<string, string> = {
  alto: "var(--text-success)",
  medio: "var(--text-warning)",
  bajo: "var(--text-error)",
};

const CONFIANZA_FILL: Record<string, string> = {
  alto: "var(--fill-success)",
  medio: "var(--fill-warning)",
  bajo: "var(--fill-error)",
};

// Mismas claves que categoria_mapper.py (backend)
export const CATEGORIAS: { key: string; label: string }[] = [
  { key: "industrial", label: "Industrial" },
  { key: "construccion", label: "Construcción" },
  { key: "carpinteria", label: "Carpintería / Madera" },
  { key: "electrico", label: "Eléctrico" },
  { key: "electronica", label: "Electrónica" },
  { key: "mecanico", label: "Mecánico" },
  { key: "hidraulico", label: "Hidráulico" },
  { key: "neumatico", label: "Neumático" },
  { key: "tuberias_valvulas", label: "Tuberías y válvulas" },
  { key: "insumos_medicos", label: "Insumos médicos" },
  { key: "consumible", label: "Consumible" },
  { key: "otro", label: "Otro" },
];

export default function ResultadoIdentificacion({ resultado, onConfirmar, onCorregir, guardando, isLoggedIn }: Props) {
  const confColor = CONFIANZA_COLOR[resultado.confianza] ?? "var(--text-muted)";
  const confFill = CONFIANZA_FILL[resultado.confianza] ?? "var(--bg-surface)";

  // La categoría identificada por la IA parte seleccionada; el usuario puede
  // agregar o quitar categorías para orientar la búsqueda de proveedores.
  const [categorias, setCategorias] = useState<Set<string>>(
    () => new Set(CATEGORIAS.some(c => c.key === resultado.categoria) ? [resultado.categoria] : ["otro"])
  );
  const [nombreLista, setNombreLista] = useState("");

  const toggleCategoria = (key: string) => {
    setCategorias(prev => {
      const next = new Set(prev);
      if (next.has(key)) {
        if (next.size > 1) next.delete(key); // siempre debe quedar al menos una
      } else {
        next.add(key);
      }
      return next;
    });
  };

  return (
    <div>
      {/* Header resultado */}
      <div style={{
        background: confFill,
        border: `1px solid ${confColor}`,
        padding: "10px 16px",
        fontSize: 11,
        color: confColor,
        marginBottom: 20,
        display: "flex",
        justifyContent: "space-between",
        alignItems: "center",
        fontFamily: "var(--font-mono)",
      }}>
        <span>Item identificado — confianza: <strong>{resultado.confianza}</strong></span>
        <span style={{ width: 8, height: 8, background: confColor, display: "inline-block" }} />
      </div>

      {/* Card principal */}
      <div style={{ background: "var(--bg-surface)", border: "1px solid var(--border-default)", padding: 20, marginBottom: 16 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 16 }}>
          <div>
            <div className="label" style={{ color: "var(--text-muted)", marginBottom: 4 }}>
              {resultado.categoria}
            </div>
            <h2 style={{ fontSize: 18, fontWeight: 800, color: "var(--text-primary)", margin: 0, letterSpacing: "-0.01em" }}>
              {resultado.nombre_tecnico}
            </h2>
          </div>
          <span className="label" style={{
            color: confColor,
            border: `1px solid ${confColor}`,
            padding: "3px 8px",
            whiteSpace: "nowrap",
          }}>
            {resultado.confianza.toUpperCase()}
          </span>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 1, marginBottom: 16, border: "1px solid var(--border-default)" }}>
          {[
            { label: "Marca", value: resultado.marca ?? "No identificada", hasValue: !!resultado.marca },
            { label: "Numero de parte", value: resultado.numero_parte ?? "No identificado", hasValue: !!resultado.numero_parte },
          ].map((field, i) => (
            <div key={field.label} style={{
              background: "var(--bg-base)",
              padding: "10px 12px",
              borderRight: i === 0 ? "1px solid var(--border-default)" : "none",
            }}>
              <div className="label" style={{ color: "var(--text-muted)", marginBottom: 4 }}>{field.label}</div>
              <div style={{ fontSize: 13, color: field.hasValue ? "var(--text-primary)" : "var(--text-muted)", fontWeight: 600 }}>
                {field.value}
              </div>
            </div>
          ))}
        </div>

        {/* Categorías — orientan qué fuentes se consultan en la búsqueda */}
        <div style={{ marginBottom: 16 }}>
          <div className="label" style={{ color: "var(--text-muted)", marginBottom: 8 }}>
            Categorías — selecciona una o más para orientar la búsqueda
          </div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
            {CATEGORIAS.map(c => {
              const activa = categorias.has(c.key);
              return (
                <button
                  key={c.key}
                  onClick={() => toggleCategoria(c.key)}
                  className="label"
                  style={{
                    color: activa ? "var(--text-inverse)" : "var(--text-secondary)",
                    background: activa ? "var(--bg-inverse)" : "var(--bg-base)",
                    border: `1px solid ${activa ? "var(--border-strong)" : "var(--border-default)"}`,
                    padding: "4px 10px",
                    cursor: "pointer",
                    fontFamily: "var(--font-mono)",
                  }}
                >
                  {activa ? "✓ " : ""}{c.label}
                </button>
              );
            })}
          </div>
        </div>

        <div style={{ marginBottom: 12 }}>
          <div className="label" style={{ color: "var(--text-muted)", marginBottom: 8 }}>Terminos de busqueda — Espanol</div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
            {resultado.terminos_busqueda_es.map((t, i) => (
              <span key={i} className="label" style={{
                color: "var(--accent)",
                background: "var(--fill-error)",
                border: "1px solid var(--border-accent)",
                padding: "3px 8px",
              }}>{t}</span>
            ))}
          </div>
        </div>

        <div>
          <div className="label" style={{ color: "var(--text-muted)", marginBottom: 8 }}>Search terms — English</div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
            {resultado.terminos_busqueda_en.map((t, i) => (
              <span key={i} className="label" style={{
                color: "var(--text-secondary)",
                background: "var(--bg-base)",
                border: "1px solid var(--border-default)",
                padding: "3px 8px",
              }}>{t}</span>
            ))}
          </div>
        </div>
      </div>

      {/* Nombre de lista / proyecto (opcional) */}
      <div style={{ background: "var(--bg-surface)", border: "1px solid var(--border-default)", padding: "12px 16px", marginBottom: 16 }}>
        <div className="label" style={{ color: "var(--text-muted)", marginBottom: 6 }}>
          Nombre de lista de cotización o proyecto — opcional
        </div>
        <input
          type="text"
          value={nombreLista}
          onChange={e => setNombreLista(e.target.value)}
          placeholder='Ej: "Mantención bodega julio" — se usa si agrupas varios ítems'
          style={{
            width: "100%", boxSizing: "border-box",
            background: "var(--bg-base)", border: "1px solid var(--border-default)",
            padding: "8px 12px", fontSize: 11, color: "var(--text-primary)",
            fontFamily: "var(--font-mono)", outline: "none",
          }}
        />
      </div>

      {/* Acciones */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 2fr", gap: 8 }}>
        <button onClick={onCorregir} className="btn-swiss-secondary" style={{ padding: 12 }}>
          Corregir
        </button>
        <button
          onClick={() => onConfirmar(Array.from(categorias), nombreLista.trim())}
          disabled={guardando}
          className={guardando ? "btn-swiss-secondary" : "btn-swiss-primary"}
          style={{ padding: 12 }}
        >
          {guardando ? "Guardando..." : isLoggedIn ? "Confirmar y buscar proveedores →" : "Continuar sin guardar →"}
        </button>
      </div>

      {!isLoggedIn && (
        <p className="label" style={{ textAlign: "center", color: "var(--text-muted)", marginTop: 10 }}>
          <a href="/register" style={{ color: "var(--accent)", textDecoration: "none" }}>Crea una cuenta gratis</a> para guardar tus cotizaciones
        </p>
      )}
    </div>
  );
}
