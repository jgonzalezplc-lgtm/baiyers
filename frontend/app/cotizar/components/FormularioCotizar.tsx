"use client";
import { useState, useRef, DragEvent, ChangeEvent } from "react";

interface Props {
  onSubmit: (descripcion: string, imagenBase64: string | null, imagenMime: string) => void;
  loading: boolean;
  initialDescripcion?: string;
}

export default function FormularioCotizar({ onSubmit, loading, initialDescripcion = "" }: Props) {
  const [descripcion, setDescripcion] = useState(initialDescripcion);
  const [imagen, setImagen] = useState<{ base64: string; mime: string; preview: string } | null>(null);
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const procesarArchivo = (file: File) => {
    if (!file.type.startsWith("image/")) return;
    const reader = new FileReader();
    reader.onload = (e) => {
      const result = e.target?.result as string;
      const base64 = result.split(",")[1];
      setImagen({ base64, mime: file.type, preview: result });
    };
    reader.readAsDataURL(file);
  };

  const onDrop = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setDragging(false);
    const file = e.dataTransfer.files[0];
    if (file) procesarArchivo(file);
  };

  const onFileChange = (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) procesarArchivo(file);
  };

  const handleSubmit = () => {
    if (!descripcion.trim() && !imagen) return;
    onSubmit(descripcion, imagen?.base64 ?? null, imagen?.mime ?? "image/jpeg");
  };

  const canSubmit = (descripcion.trim() || imagen) && !loading;

  return (
    <div>
      {/* Intención de compra en lenguaje natural */}
      <div style={{ marginBottom: 16 }}>
        <textarea
          value={descripcion}
          onChange={e => setDescripcion(e.target.value)}
          onKeyDown={e => {
            if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) handleSubmit();
          }}
          placeholder={'Ej: "necesito 3 taladros percutores y 50 tornillos M6"  ·  "madera de pino para construir un mueble"  ·  "rodamiento SKF 6205-2RS eje 25mm"'}
          rows={4}
          autoFocus
          style={{
            width: "100%",
            padding: "14px",
            background: "var(--bg-base)",
            border: "1px solid var(--border-default)",
            color: "var(--text-primary)",
            fontSize: 13,
            outline: "none",
            resize: "vertical",
            fontFamily: "var(--font-mono)",
            boxSizing: "border-box",
            lineHeight: 1.6,
          }}
        />
        <div className="label" style={{ color: "var(--text-muted)", marginTop: 4 }}>
          Escribe uno o varios ítems, con cantidades si quieres — la IA los separa y arma la lista. ⌘+Enter para enviar.
        </div>
      </div>

      {/* Divider */}
      <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 16 }}>
        <div style={{ flex: 1, height: 1, background: "var(--border-default)" }} />
        <span className="label" style={{ color: "var(--text-muted)" }}>O</span>
        <div style={{ flex: 1, height: 1, background: "var(--border-default)" }} />
      </div>

      {/* Upload imagen */}
      {imagen ? (
        <div style={{ position: "relative", marginBottom: 16 }}>
          <img
            src={imagen.preview}
            alt="Preview"
            style={{ width: "100%", maxHeight: 220, objectFit: "contain", border: "1px solid var(--border-default)", background: "var(--bg-surface)" }}
          />
          <button
            onClick={() => { setImagen(null); if (inputRef.current) inputRef.current.value = ""; }}
            style={{
              position: "absolute", top: 8, right: 8,
              background: "var(--fill-error)",
              border: "1px solid var(--border-accent)",
              color: "var(--text-error)",
              padding: "4px 10px",
              fontSize: 10,
              cursor: "pointer",
              fontFamily: "var(--font-mono)",
            }}
          >
            Quitar foto
          </button>
        </div>
      ) : (
        <div
          onClick={() => inputRef.current?.click()}
          onDrop={onDrop}
          onDragOver={e => { e.preventDefault(); setDragging(true); }}
          onDragLeave={() => setDragging(false)}
          style={{
            border: `2px dashed ${dragging ? "var(--accent)" : "var(--border-default)"}`,
            padding: "28px 20px",
            textAlign: "center",
            cursor: "pointer",
            marginBottom: 16,
            background: dragging ? "var(--fill-error)" : "transparent",
            transition: "all 0.15s",
          }}
        >
          <div style={{ fontSize: 11, color: "var(--text-secondary)", marginBottom: 4, fontFamily: "var(--font-mono)" }}>
            Arrastra una foto o haz clic para subir
          </div>
          <div className="label" style={{ color: "var(--text-muted)" }}>JPG, PNG, WEBP — max 5MB</div>
        </div>
      )}
      <input ref={inputRef} type="file" accept="image/*" onChange={onFileChange} style={{ display: "none" }} />

      {/* Submit */}
      <button
        onClick={handleSubmit}
        disabled={!canSubmit}
        className={canSubmit ? "btn-swiss-primary" : "btn-swiss-secondary"}
        style={{ width: "100%", padding: "14px", fontSize: 13 }}
      >
        {loading ? "Entendiendo tu compra..." : "Comenzar compra →"}
      </button>

      <p className="label" style={{ textAlign: "center", color: "var(--text-muted)", marginTop: 10 }}>
        Usando Google Gemini 1.5 Flash · Gratis hasta 1.500 req/dia
      </p>
    </div>
  );
}
