"use client";
import { useState, useRef } from "react";
import { createClient } from "@/lib/supabase/client";
import { authFetch } from "@/lib/authFetch";
import Link from "next/link";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface PreviewRow {
  [key: string]: string | null;
}

export default function ImportarProveedoresPage() {
  const [userId, setUserId] = useState<string | null>(null);
  const [arrastrando, setArrastrando] = useState(false);
  const [archivo, setArchivo] = useState<File | null>(null);
  const [preview, setPreview] = useState<PreviewRow[]>([]);
  const [cargando, setCargando] = useState(false);
  const [resultado, setResultado] = useState<{ importados: number; actualizados: number; omitidos: number; errores: string[] } | null>(null);
  const [error, setError] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  useState(() => {
    createClient().auth.getUser().then(({ data }) => setUserId(data.user?.id ?? null));
  });

  const procesarArchivo = (file: File) => {
    setArchivo(file);
    setResultado(null);
    setError("");
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setArrastrando(false);
    const file = e.dataTransfer.files[0];
    if (file) procesarArchivo(file);
  };

  const handleImportar = async () => {
    if (!archivo || !userId) return;
    setCargando(true);
    setError("");
    try {
      const form = new FormData();
      form.append("file", archivo);
      const res = await authFetch(`${API_URL}/api/proveedores/importar`, {
        method: "POST",
        body: form,
      });
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      setPreview(data.preview || []);
      setResultado({ importados: data.importados, actualizados: data.actualizados, omitidos: data.omitidos ?? 0, errores: data.errores ?? [] });
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Error importando");
    } finally {
      setCargando(false);
    }
  };

  const handlePlantilla = () => {
    window.open(`${API_URL}/api/proveedores/plantilla`, "_blank");
  };

  const columnas = preview.length > 0 ? Object.keys(preview[0]) : [];

  return (
    <div style={{ minHeight: "100vh", background: "var(--canvas)", padding: "24px 20px" }}>
      <div style={{ maxWidth: 760, margin: "0 auto" }}>

        {/* Header */}
        <div style={{ marginBottom: 24 }}>
          <Link href="/proveedores" style={{ fontSize: 10, color: "var(--n-600)", textDecoration: "none" }}>← Proveedores</Link>
          <div style={{ fontSize: 10, color: "var(--brand)", letterSpacing: "0.15em", marginTop: 8, marginBottom: 4 }}>Importación</div>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end" }}>
            <h1 style={{ fontSize: 20, fontWeight: 800, color: "var(--n-900)", margin: 0 }}>Importar base de proveedores</h1>
            <button onClick={handlePlantilla} style={{ fontSize: 10, color: "var(--success)", background: "var(--success)11", border: "1px solid var(--success)33", borderRadius: 6, padding: "7px 14px", cursor: "pointer", fontFamily: "inherit" }}>
              Descargar plantilla Excel
            </button>
          </div>
          <p style={{ fontSize: 11, color: "var(--n-600)", marginTop: 6 }}>
            Acepta .xlsx, .xls, .csv, Gemini mapea las columnas automáticamente sin importar el formato.
          </p>
        </div>

        {/* Drop zone */}
        <div
          onDragOver={e => { e.preventDefault(); setArrastrando(true); }}
          onDragLeave={() => setArrastrando(false)}
          onDrop={handleDrop}
          onClick={() => inputRef.current?.click()}
          style={{
            border: `2px dashed ${arrastrando ? "var(--brand)" : archivo ? "var(--success)66" : "var(--n-200)"}`,
            borderRadius: 12, padding: "40px 20px", textAlign: "center", cursor: "pointer",
            background: arrastrando ? "var(--brand)08" : archivo ? "var(--success)08" : "var(--surface)",
            transition: "all 0.15s", marginBottom: 20,
          }}
        >
          <input
            ref={inputRef}
            type="file"
            accept=".xlsx,.xls,.csv"
            style={{ display: "none" }}
            onChange={e => e.target.files?.[0] && procesarArchivo(e.target.files[0])}
          />
          <div style={{ fontSize: 28, marginBottom: 10 }}>{archivo ? "📋" : "📁"}</div>
          {archivo ? (
            <>
              <div style={{ fontSize: 13, fontWeight: 700, color: "var(--success)", marginBottom: 4 }}>{archivo.name}</div>
              <div style={{ fontSize: 11, color: "var(--n-600)" }}>{(archivo.size / 1024).toFixed(1)} KB, click para cambiar</div>
            </>
          ) : (
            <>
              <div style={{ fontSize: 13, fontWeight: 700, color: "var(--n-900)", marginBottom: 4 }}>Arrastra tu archivo aquí</div>
              <div style={{ fontSize: 11, color: "var(--n-600)" }}>o haz clic para seleccionar · Excel o CSV</div>
            </>
          )}
        </div>

        {archivo && !resultado && (
          <button
            onClick={handleImportar}
            disabled={cargando}
            style={{ width: "100%", padding: 13, fontWeight: 700, fontSize: 12, background: cargando ? "var(--n-200)" : "var(--brand)", color: cargando ? "var(--n-600)" : "#fff", border: "none", borderRadius: 8, cursor: cargando ? "not-allowed" : "pointer", fontFamily: "inherit", marginBottom: 20 }}
          >
            {cargando ? "Analizando con Gemini e importando..." : "Importar proveedores"}
          </button>
        )}

        {error && (
          <div style={{ background: "var(--st-rechazada-bg)", border: "1px solid var(--danger)33", borderRadius: 8, padding: "12px 16px", fontSize: 11, color: "var(--danger)", marginBottom: 16 }}>
            {error}
          </div>
        )}

        {/* Resultado */}
        {resultado && (
          <div style={{ background: "var(--st-aprobada-bg)", border: "1px solid var(--success)33", borderRadius: 10, padding: "20px", marginBottom: 20 }}>
            <div style={{ fontSize: 13, fontWeight: 700, color: "var(--success)", marginBottom: 12 }}>Importación completada</div>
            <div style={{ display: "flex", gap: 24 }}>
              <div>
                <div style={{ fontSize: 28, fontWeight: 800, color: "var(--success)" }}>{resultado.importados}</div>
                <div style={{ fontSize: 10, color: "var(--n-600)" }}>Nuevos</div>
              </div>
              <div>
                <div style={{ fontSize: 28, fontWeight: 800, color: "var(--brand)" }}>{resultado.actualizados}</div>
                <div style={{ fontSize: 10, color: "var(--n-600)" }}>Actualizados</div>
              </div>
              {resultado.omitidos > 0 && <div>
                <div style={{ fontSize: 28, fontWeight: 800, color: "var(--warning)" }}>{resultado.omitidos}</div>
                <div style={{ fontSize: 10, color: "var(--n-600)" }}>Omitidos sin nombre</div>
              </div>}
            </div>
            {resultado.errores.length > 0 && (
              <div style={{ marginTop: 12, fontSize: 11, color: "var(--danger)" }}>
                {resultado.errores.slice(0, 3).map((e, i) => <div key={i}>{e}</div>)}
              </div>
            )}
            <Link href="/proveedores" style={{ display: "inline-block", marginTop: 14, fontSize: 11, color: "var(--brand)", fontWeight: 700, textDecoration: "none" }}>
              Ver todos los proveedores →
            </Link>
          </div>
        )}

        {/* Preview */}
        {preview.length > 0 && (
          <div>
            <div style={{ fontSize: 11, color: "var(--n-600)", letterSpacing: "0.1em", marginBottom: 8, fontWeight: 700 }}>
              Preview, primeras {preview.length} filas
            </div>
            <div style={{ background: "var(--surface)", border: "1px solid var(--n-200)", borderRadius: 8, overflow: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 11 }}>
                <thead>
                  <tr>
                    {columnas.map(col => (
                      <th key={col} style={{ padding: "8px 12px", borderBottom: "1px solid var(--n-200)", textAlign: "left", color: "var(--n-600)", fontSize: 10, letterSpacing: "0.08em", whiteSpace: "nowrap" }}>{col}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {preview.map((row, i) => (
                    <tr key={i} style={{ borderBottom: i < preview.length - 1 ? "1px solid var(--surface-2)" : "none" }}>
                      {columnas.map(col => (
                        <td key={col} style={{ padding: "8px 12px", color: "var(--n-500)", maxWidth: 160, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                          {row[col] ?? "—"}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
