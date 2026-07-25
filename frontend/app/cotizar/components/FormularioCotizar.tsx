"use client";
import { useState, useRef, DragEvent, ChangeEvent } from "react";
import { ImagePlus, ArrowUp, X } from "lucide-react";

interface Props {
  onSubmit: (descripcion: string, imagenBase64: string | null, imagenMime: string) => void;
  loading: boolean;
  initialDescripcion?: string;
}

const EJEMPLOS = [
  "Rodamiento SKF 6205-2RS eje 25mm",
  "3 taladros percutores y 50 tornillos M6",
  "Materiales para construir una bodega de 20m²",
];

export default function FormularioCotizar({ onSubmit, loading, initialDescripcion = "" }: Props) {
  const [descripcion, setDescripcion] = useState(initialDescripcion);
  const [imagen, setImagen] = useState<{ base64: string; mime: string; preview: string } | null>(null);
  const [dragging, setDragging] = useState(false);
  const [focus, setFocus] = useState(false);
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

  const canSubmit = !!(descripcion.trim() || imagen) && !loading;

  return (
    <div style={{ width: "100%" }}>
      {/* Composer estilo Claude */}
      <div
        onDrop={onDrop}
        onDragOver={e => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        style={{
          background: "var(--surface)",
          border: `1.5px solid ${dragging || focus ? "var(--brand)" : "var(--n-300)"}`,
          borderRadius: "var(--r-xl)",
          boxShadow: dragging || focus ? "0 0 0 4px var(--brand-50)" : "var(--shadow-card)",
          transition: "border-color .15s ease, box-shadow .15s ease",
          padding: 14,
        }}
      >
        {/* Preview de imagen adjunta */}
        {imagen && (
          <div style={{ position: "relative", display: "inline-block", marginBottom: 12 }}>
            <img
              src={imagen.preview}
              alt="Imagen adjunta"
              style={{ maxHeight: 120, maxWidth: "100%", borderRadius: "var(--r-md)", border: "1px solid var(--n-200)", display: "block" }}
            />
            <button
              onClick={() => { setImagen(null); if (inputRef.current) inputRef.current.value = ""; }}
              aria-label="Quitar imagen"
              style={{
                position: "absolute", top: 6, right: 6,
                width: 24, height: 24, borderRadius: "50%",
                background: "rgba(33,29,24,.72)", color: "#fff",
                border: "none", cursor: "pointer",
                display: "inline-flex", alignItems: "center", justifyContent: "center",
              }}
            >
              <X size={14} strokeWidth={2} />
            </button>
          </div>
        )}

        <textarea
          value={descripcion}
          onChange={e => setDescripcion(e.target.value)}
          onFocus={() => setFocus(true)}
          onBlur={() => setFocus(false)}
          onKeyDown={e => {
            if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) handleSubmit();
          }}
          placeholder="Busca un ítem específico o describe tu proyecto…"
          rows={3}
          autoFocus
          style={{
            width: "100%",
            border: "none",
            background: "transparent",
            color: "var(--n-900)",
            fontSize: 16,
            lineHeight: 1.6,
            outline: "none",
            resize: "none",
            fontFamily: "var(--font-sans)",
            padding: "2px 4px",
            boxSizing: "border-box",
          }}
        />

        {/* Barra inferior: adjuntar + enviar */}
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginTop: 8 }}>
          <button
            onClick={() => inputRef.current?.click()}
            title="Adjuntar una foto"
            style={{
              display: "inline-flex", alignItems: "center", gap: 7,
              background: "transparent", border: "1px solid var(--n-300)",
              color: "var(--n-600)", cursor: "pointer",
              padding: "7px 11px", borderRadius: "var(--r-md)",
              fontSize: 13.5, fontFamily: "var(--font-sans)",
            }}
          >
            <ImagePlus size={16} strokeWidth={1.75} />
            Foto
          </button>

          <button
            onClick={handleSubmit}
            disabled={!canSubmit}
            aria-label="Enviar"
            title="Enviar (⌘+Enter)"
            style={{
              width: 36, height: 36, borderRadius: "50%",
              background: canSubmit ? "var(--brand)" : "var(--n-300)",
              color: "#fff", border: "none",
              cursor: canSubmit ? "pointer" : "not-allowed",
              display: "inline-flex", alignItems: "center", justifyContent: "center",
              transition: "background .15s ease",
              flexShrink: 0,
            }}
          >
            <ArrowUp size={19} strokeWidth={2.25} />
          </button>
        </div>

        <input ref={inputRef} type="file" accept="image/*" onChange={onFileChange} style={{ display: "none" }} />
      </div>

      {/* Hint */}
      <p style={{ textAlign: "center", fontSize: 13, color: "var(--n-500)", margin: "12px 0 0" }}>
        {loading
          ? "Entendiendo tu compra…"
          : "Escribe uno o varios ítems, con cantidades si quieres, la IA los separa y arma la lista."}
      </p>

      {/* Ejemplos clicables */}
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8, justifyContent: "center", marginTop: 16 }}>
        {EJEMPLOS.map(ej => (
          <button
            key={ej}
            onClick={() => setDescripcion(ej)}
            style={{
              background: "var(--surface)", border: "1px solid var(--n-200)",
              color: "var(--n-600)", cursor: "pointer",
              padding: "7px 12px", borderRadius: "var(--r-pill)",
              fontSize: 13, fontFamily: "var(--font-sans)",
              transition: "background .12s ease, border-color .12s ease",
            }}
            onMouseEnter={e => { e.currentTarget.style.background = "var(--surface-2)"; e.currentTarget.style.borderColor = "var(--n-300)"; }}
            onMouseLeave={e => { e.currentTarget.style.background = "var(--surface)"; e.currentTarget.style.borderColor = "var(--n-200)"; }}
          >
            {ej}
          </button>
        ))}
      </div>
    </div>
  );
}
