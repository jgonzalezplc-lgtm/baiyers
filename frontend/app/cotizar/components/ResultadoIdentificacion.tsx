"use client";
import { useState } from "react";
import { Card, Badge, Input, BtnPrimary, BtnSecondary } from "@/components/ui";

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

const CONFIANZA_BADGE: Record<string, "success" | "warning" | "error"> = {
  alto: "success",
  medio: "warning",
  bajo: "error",
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
  const tipoConfianza = CONFIANZA_BADGE[resultado.confianza] ?? "default";

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
        display: "flex", justifyContent: "space-between", alignItems: "center",
        marginBottom: 16,
      }}>
        <span style={{ fontSize: 13.5, color: "var(--n-700)" }}>Ítem identificado</span>
        <Badge tipo={tipoConfianza}>Confianza {resultado.confianza}</Badge>
      </div>

      {/* Card principal */}
      <Card style={{ marginBottom: 16 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 16 }}>
          <div>
            <div style={{ fontSize: 12, fontWeight: 600, color: "var(--n-500)", marginBottom: 4, textTransform: "uppercase", letterSpacing: "0.02em" }}>
              {resultado.categoria}
            </div>
            <h2 style={{ fontSize: 18, fontWeight: 600, color: "var(--n-900)", margin: 0, letterSpacing: "-0.01em" }}>
              {resultado.nombre_tecnico}
            </h2>
          </div>
        </div>

        <div style={{
          display: "grid", gridTemplateColumns: "1fr 1fr", gap: 1, marginBottom: 16,
          border: "1px solid var(--n-200)", borderRadius: "var(--r-md)", overflow: "hidden",
        }}>
          {[
            { label: "Marca", value: resultado.marca ?? "No identificada", hasValue: !!resultado.marca },
            { label: "Número de parte", value: resultado.numero_parte ?? "No identificado", hasValue: !!resultado.numero_parte },
          ].map((field, i) => (
            <div key={field.label} style={{
              background: "var(--canvas)",
              padding: "10px 12px",
              borderRight: i === 0 ? "1px solid var(--n-200)" : "none",
            }}>
              <div style={{ fontSize: 12, color: "var(--n-500)", marginBottom: 4 }}>{field.label}</div>
              <div style={{ fontSize: 13.5, color: field.hasValue ? "var(--n-900)" : "var(--n-500)", fontWeight: 500 }}>
                {field.value}
              </div>
            </div>
          ))}
        </div>

        {/* Categorías, orientan qué fuentes se consultan en la búsqueda */}
        <div style={{ marginBottom: 16 }}>
          <div style={{ fontSize: 12, color: "var(--n-500)", marginBottom: 8 }}>
            Categorías — selecciona una o más para orientar la búsqueda
          </div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
            {CATEGORIAS.map(c => {
              const activa = categorias.has(c.key);
              return (
                <button
                  key={c.key}
                  onClick={() => toggleCategoria(c.key)}
                  style={{
                    fontSize: 13, fontWeight: 500, fontFamily: "var(--font-sans)",
                    color: activa ? "#fff" : "var(--n-700)",
                    background: activa ? "var(--brand)" : "var(--canvas)",
                    border: `1px solid ${activa ? "var(--brand)" : "var(--n-200)"}`,
                    borderRadius: "var(--r-pill)",
                    padding: "5px 12px",
                    cursor: "pointer",
                  }}
                >
                  {activa ? "✓ " : ""}{c.label}
                </button>
              );
            })}
          </div>
        </div>

        <div style={{ marginBottom: 12 }}>
          <div style={{ fontSize: 12, color: "var(--n-500)", marginBottom: 8 }}>Términos de búsqueda, español</div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
            {resultado.terminos_busqueda_es.map((t, i) => (
              <span key={i} style={{
                fontSize: 12.5, color: "var(--brand-700)",
                background: "var(--brand-50)",
                border: "1px solid var(--brand-100)",
                borderRadius: "var(--r-pill)",
                padding: "3px 10px",
              }}>{t}</span>
            ))}
          </div>
        </div>

        <div>
          <div style={{ fontSize: 12, color: "var(--n-500)", marginBottom: 8 }}>Search terms, English</div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
            {resultado.terminos_busqueda_en.map((t, i) => (
              <span key={i} style={{
                fontSize: 12.5, color: "var(--n-600)",
                background: "var(--canvas)",
                border: "1px solid var(--n-200)",
                borderRadius: "var(--r-pill)",
                padding: "3px 10px",
              }}>{t}</span>
            ))}
          </div>
        </div>
      </Card>

      {/* Nombre de lista / proyecto (opcional) */}
      <div style={{ marginBottom: 16 }}>
        <Input
          label="Nombre de lista de cotización o proyecto, opcional"
          value={nombreLista}
          onChange={e => setNombreLista(e.target.value)}
          placeholder='Ej: "Mantención bodega julio", se usa si agrupas varios ítems'
        />
      </div>

      {/* Acciones */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 2fr", gap: 8 }}>
        <BtnSecondary onClick={onCorregir} style={{ width: "100%" }}>
          Corregir
        </BtnSecondary>
        <BtnPrimary
          onClick={() => onConfirmar(Array.from(categorias), nombreLista.trim())}
          disabled={guardando}
          style={{ width: "100%" }}
        >
          {guardando ? "Guardando…" : isLoggedIn ? "Confirmar y buscar proveedores →" : "Continuar sin guardar →"}
        </BtnPrimary>
      </div>

      {!isLoggedIn && (
        <p style={{ textAlign: "center", fontSize: 13, color: "var(--n-500)", marginTop: 10 }}>
          <a href="/register" style={{ color: "var(--brand)", textDecoration: "none" }}>Crea una cuenta gratis</a> para guardar tus cotizaciones
        </p>
      )}
    </div>
  );
}
