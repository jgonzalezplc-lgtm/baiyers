"use client";
import { useState, useRef } from "react";
import { createClient } from "@/lib/supabase/client";
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
  const [resultado, setResultado] = useState<{ importados: number; actualizados: number; errores: string[] } | null>(null);
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
      const res = await fetch(`${API_URL}/api/proveedores/importar?user_id=${userId}`, {
        method: "POST",
        body: form,
      });
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      setPreview(data.preview || []);
      setResultado({ importados: data.importados, actualizados: data.actualizados, errores: data.errores });
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
    <div style={{ minHeight: "100vh", background: "#060610", padding: "24px 20px" }}>
      <div style={{ maxWidth: 760, margin: "0 auto" }}>

        {/* Header */}
        <div style={{ marginBottom: 24 }}>
          <Link href="/proveedores" style={{ fontSize: 10, color: "#475569", textDecoration: "none" }}>← Proveedores</Link>
          <div style={{ fontSize: 10, color: "#6366f1", textTransform: "uppercase", letterSpacing: "0.15em", marginTop: 8, marginBottom: 4 }}>Importación</div>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end" }}>
            <h1 style={{ fontSize: 20, fontWeight: 800, color: "#f1f5f9", margin: 0 }}>Importar base de proveedores</h1>
            <button onClick={handlePlantilla} style={{ fontSize: 10, color: "#34d399", background: "#34d39911", border: "1px solid #34d39933", borderRadius: 6, padding: "7px 14px", cursor: "pointer", fontFamily: "inherit" }}>
              Descargar plantilla Excel
            </button>
          </div>
          <p style={{ fontSize: 11, color: "#475569", marginTop: 6 }}>
            Acepta .xlsx, .xls, .csv — Gemini mapea las columnas automáticamente sin importar el formato.
          </p>
        </div>

        {/* Drop zone */}
        <div
          onDragOver={e => { e.preventDefault(); setArrastrando(true); }}
          onDragLeave={() => setArrastrando(false)}
          onDrop={handleDrop}
          onClick={() => inputRef.current?.click()}
          style={{
            border: `2px dashed ${arrastrando ? "#6366f1" : archivo ? "#34d39966" : "#1a1a2e"}`,
            borderRadius: 12, padding: "40px 20px", textAlign: "center", cursor: "pointer",
            background: arrastrando ? "#6366f108" : archivo ? "#34d39908" : "#0a0a18",
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
              <div style={{ fontSize: 13, fontWeight: 700, color: "#34d399", marginBottom: 4 }}>{archivo.name}</div>
              <div style={{ fontSize: 11, color: "#475569" }}>{(archivo.size / 1024).toFixed(1)} KB — click para cambiar</div>
            </>
          ) : (
            <>
              <div style={{ fontSize: 13, fontWeight: 700, color: "#f1f5f9", marginBottom: 4 }}>Arrastra tu archivo aquí</div>
              <div style={{ fontSize: 11, color: "#475569" }}>o haz clic para seleccionar · Excel o CSV</div>
            </>
          )}
        </div>

        {archivo && !resultado && (
          <button
            onClick={handleImportar}
            disabled={cargando}
            style={{ width: "100%", padding: 13, fontWeight: 700, fontSize: 12, background: cargando ? "#1a1a2e" : "#6366f1", color: cargando ? "#475569" : "#fff", border: "none", borderRadius: 8, cursor: cargando ? "not-allowed" : "pointer", fontFamily: "inherit", marginBottom: 20 }}
          >
            {cargando ? "Analizando con Gemini e importando..." : "Importar proveedores"}
          </button>
        )}

        {error && (
          <div style={{ background: "#1a0000", border: "1px solid #f8717133", borderRadius: 8, padding: "12px 16px", fontSize: 11, color: "#f87171", marginBottom: 16 }}>
            {error}
          </div>
        )}

        {/* Resultado */}
        {resultado && (
          <div style={{ background: "#001a0a", border: "1px solid #34d39933", borderRadius: 10, padding: "20px", marginBottom: 20 }}>
            <div style={{ fontSize: 13, fontWeight: 700, color: "#34d399", marginBottom: 12 }}>Importación completada</div>
            <div style={{ display: "flex", gap: 24 }}>
              <div>
                <div style={{ fontSize: 28, fontWeight: 800, color: "#34d399" }}>{resultado.importados}</div>
                <div style={{ fontSize: 10, color: "#475569", textTransform: "uppercase" }}>Nuevos</div>
              </div>
              <div>
                <div style={{ fontSize: 28, fontWeight: 800, color: "#6366f1" }}>{resultado.actualizados}</div>
                <div style={{ fontSize: 10, color: "#475569", textTransform: "uppercase" }}>Actualizados</div>
              </div>
            </div>
            {resultado.errores.length > 0 && (
              <div style={{ marginTop: 12, fontSize: 11, color: "#f87171" }}>
                {resultado.errores.slice(0, 3).map((e, i) => <div key={i}>{e}</div>)}
              </div>
            )}
            <Link href="/proveedores" style={{ display: "inline-block", marginTop: 14, fontSize: 11, color: "#6366f1", fontWeight: 700, textDecoration: "none" }}>
              Ver todos los proveedores →
            </Link>
          </div>
        )}

        {/* Preview */}
        {preview.length > 0 && (
          <div>
            <div style={{ fontSize: 11, color: "#475569", textTransform: "uppercase", letterSpacing: "0.1em", marginBottom: 8, fontWeight: 700 }}>
              Preview — primeras {preview.length} filas
            </div>
            <div style={{ background: "#0a0a18", border: "1px solid #1a1a2e", borderRadius: 8, overflow: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 11 }}>
                <thead>
                  <tr>
                    {columnas.map(col => (
                      <th key={col} style={{ padding: "8px 12px", borderBottom: "1px solid #1a1a2e", textAlign: "left", color: "#475569", fontSize: 10, textTransform: "uppercase", letterSpacing: "0.08em", whiteSpace: "nowrap" }}>{col}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {preview.map((row, i) => (
                    <tr key={i} style={{ borderBottom: i < preview.length - 1 ? "1px solid #0d0d1a" : "none" }}>
                      {columnas.map(col => (
                        <td key={col} style={{ padding: "8px 12px", color: "#94a3b8", maxWidth: 160, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
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
