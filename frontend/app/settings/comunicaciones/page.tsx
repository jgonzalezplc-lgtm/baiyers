"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowLeft, Mail } from "lucide-react";
import { authFetch } from "@/lib/authFetch";
import { BtnPrimary, BtnSecondary, Card, Input, Textarea, SkeletonBox, CascadeWrapper } from "@/components/ui";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface Plantilla {
  evento: string;
  audiencia: "internal" | "external";
  descripcion: string;
  variables_permitidas: string[];
  subject: string;
  body: string;
  origen: "default" | "organizacion" | "workflow" | "nodo";
  version: number;
}

function Insignia({ personalizada }: { personalizada: boolean }) {
  return (
    <span style={{
      fontSize: 11, padding: "3px 9px", borderRadius: 999,
      background: personalizada ? "var(--brand-50)" : "var(--n-100)",
      color: personalizada ? "var(--brand)" : "var(--n-500)",
      border: `1px solid ${personalizada ? "var(--brand-100)" : "var(--n-200)"}`,
    }}>
      {personalizada ? "Personalizada" : "Default"}
    </span>
  );
}

export default function ComunicacionesPage() {
  const router = useRouter();
  const [cargando, setCargando] = useState(true);
  const [esAdmin, setEsAdmin] = useState(false);
  const [plantillas, setPlantillas] = useState<Plantilla[]>([]);
  const [editando, setEditando] = useState<Plantilla | null>(null);

  const cargar = async () => {
    setCargando(true);
    try {
      const [org, lista] = await Promise.all([
        authFetch(`${API_URL}/api/organizacion/mia`).then(r => r.json()).catch(() => ({})),
        authFetch(`${API_URL}/api/mail-templates`).then(r => r.json()).catch(() => []),
      ]);
      setEsAdmin(!!org.es_admin);
      setPlantillas(Array.isArray(lista) ? lista : []);
    } finally {
      setCargando(false);
    }
  };

  useEffect(() => { cargar(); }, []);

  const internas = plantillas.filter(p => p.audiencia === "internal");
  const externas = plantillas.filter(p => p.audiencia === "external");

  const renderGrupo = (titulo: string, items: Plantilla[]) => (
    <div style={{ marginBottom: 24 }}>
      <h2 style={{ fontSize: 14, fontWeight: 600, color: "var(--n-700)", margin: "0 0 10px" }}>{titulo}</h2>
      <Card padding={0}>
        {items.map((p, i) => (
          <div
            key={p.evento}
            onClick={() => setEditando(p)}
            style={{
              display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12,
              padding: "13px 16px", cursor: "pointer",
              borderBottom: i === items.length - 1 ? "none" : "1px solid var(--n-100)",
            }}
          >
            <div style={{ minWidth: 0 }}>
              <div style={{ fontSize: 13.5, fontWeight: 500, color: "var(--n-900)" }}>{p.descripcion}</div>
              <div style={{ fontSize: 12, color: "var(--n-500)", marginTop: 2 }}>{p.evento}</div>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 10, flexShrink: 0 }}>
              <Insignia personalizada={p.origen !== "default"} />
              <span style={{ fontSize: 12.5, color: "var(--brand)" }}>{esAdmin ? "Editar →" : "Ver →"}</span>
            </div>
          </div>
        ))}
      </Card>
    </div>
  );

  if (cargando) {
    return (
      <div style={{ maxWidth: 680, margin: "0 auto" }}>
        <SkeletonBox height={13} width={120} style={{ marginBottom: 16 }} />
        <SkeletonBox height={26} width={280} style={{ marginBottom: 8 }} />
        <SkeletonBox height={13} width={380} style={{ marginBottom: 20 }} />
        <CascadeWrapper>
          <Card padding={18}><SkeletonBox height={120} width="100%" /></Card>
          <Card padding={18} style={{ marginTop: 16 }}><SkeletonBox height={160} width="100%" /></Card>
        </CascadeWrapper>
      </div>
    );
  }

  return (
    <div style={{ maxWidth: 680, margin: "0 auto" }}>
      <button onClick={() => router.push("/settings")} style={{ border: 0, background: "none", color: "var(--n-600)", cursor: "pointer", display: "inline-flex", alignItems: "center", gap: 6, marginBottom: 16, fontSize: 13.5 }}>
        <ArrowLeft size={16} /> Configuración
      </button>

      <div style={{ marginBottom: 20 }}>
        <h1 style={{ fontSize: 22, fontWeight: 600, color: "var(--n-900)", margin: "0 0 4px", display: "flex", alignItems: "center", gap: 8 }}>
          <Mail size={20} strokeWidth={1.75} /> Comunicaciones
        </h1>
        <p style={{ fontSize: 13.5, color: "var(--n-600)", margin: 0 }}>
          {esAdmin
            ? "Los correos que salen a tu equipo y a tus proveedores. Personaliza cualquiera sin tocar código."
            : "Los correos que salen a tu equipo y a tus proveedores. Solo un admin puede editarlos."}
        </p>
      </div>

      {renderGrupo("Comunicaciones internas", internas)}
      {renderGrupo("Comunicaciones externas", externas)}

      {editando && (
        <EditorPlantilla
          plantilla={editando}
          esAdmin={esAdmin}
          onClose={() => setEditando(null)}
          onGuardado={() => { setEditando(null); cargar(); }}
        />
      )}
    </div>
  );
}

function EditorPlantilla({ plantilla, esAdmin, onClose, onGuardado }: {
  plantilla: Plantilla; esAdmin: boolean; onClose: () => void; onGuardado: () => void;
}) {
  const [subject, setSubject] = useState(plantilla.subject);
  const [body, setBody] = useState(plantilla.body);
  const [campoConFoco, setCampoConFoco] = useState<"subject" | "body">("body");
  const [previsualizacion, setPrevisualizacion] = useState<{ subject: string; body: string } | null>(null);
  const [cargandoPreview, setCargandoPreview] = useState(false);
  const [guardando, setGuardando] = useState(false);
  const [restaurando, setRestaurando] = useState(false);
  const [error, setError] = useState("");

  const insertarVariable = (v: string) => {
    const placeholder = `{{${v}}}`;
    if (campoConFoco === "subject") setSubject(s => `${s}${placeholder}`);
    else setBody(b => `${b}${placeholder}`);
  };

  const previsualizar = async () => {
    setCargandoPreview(true);
    setError("");
    try {
      const res = await authFetch(`${API_URL}/api/mail-templates/preview`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          evento: plantilla.evento, subject, body,
          variables_declaradas: plantilla.variables_permitidas,
        }),
      });
      if (!res.ok) { const e = await res.json().catch(() => ({})); throw new Error(e.detail || "No se pudo previsualizar"); }
      setPrevisualizacion(await res.json());
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo previsualizar");
    } finally {
      setCargandoPreview(false);
    }
  };

  const guardar = async () => {
    setGuardando(true);
    setError("");
    try {
      const res = await authFetch(`${API_URL}/api/mail-templates`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          evento: plantilla.evento, subject, body,
          variables_declaradas: plantilla.variables_permitidas, origen: "user_edit",
        }),
      });
      if (!res.ok) { const e = await res.json().catch(() => ({})); throw new Error(e.detail || "No se pudo guardar"); }
      onGuardado();
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo guardar");
      setGuardando(false);
    }
  };

  const restaurar = async () => {
    setRestaurando(true);
    setError("");
    try {
      const res = await authFetch(`${API_URL}/api/mail-templates/restaurar-default`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ evento: plantilla.evento }),
      });
      if (!res.ok) { const e = await res.json().catch(() => ({})); throw new Error(e.detail || "No se pudo restaurar"); }
      onGuardado();
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo restaurar");
      setRestaurando(false);
    }
  };

  return (
    <div onClick={onClose} style={{
      position: "fixed", inset: 0, background: "rgba(0,0,0,.45)", zIndex: 200,
      display: "flex", alignItems: "flex-start", justifyContent: "center", padding: "40px 16px", overflowY: "auto",
    }}>
      <div onClick={e => e.stopPropagation()} style={{
        background: "var(--surface)", borderRadius: "var(--r-lg)", width: "100%", maxWidth: 560,
        padding: 24, boxShadow: "var(--shadow-pop)",
      }}>
        <div style={{ fontSize: 16, fontWeight: 600, color: "var(--n-900)", marginBottom: 4 }}>{plantilla.descripcion}</div>
        <div style={{ fontSize: 12, color: "var(--n-500)", marginBottom: 16 }}>{plantilla.evento} · versión {plantilla.version || "default"}</div>

        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <div onFocus={() => setCampoConFoco("subject")}>
            <Input label="Asunto" value={subject} onChange={e => setSubject(e.target.value)} disabled={!esAdmin} />
          </div>
          <div onFocus={() => setCampoConFoco("body")}>
            <Textarea label="Cuerpo" value={body} onChange={e => setBody(e.target.value)} rows={8} />
          </div>

          {esAdmin && (
            <div>
              <div style={{ fontSize: 11.5, color: "var(--n-500)", marginBottom: 6 }}>
                Variables disponibles — clic para insertar en &quot;{campoConFoco === "subject" ? "Asunto" : "Cuerpo"}&quot;:
              </div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                {plantilla.variables_permitidas.map(v => (
                  <button
                    key={v} type="button" onClick={() => insertarVariable(v)}
                    style={{
                      fontSize: 11.5, padding: "4px 10px", borderRadius: 999,
                      background: "var(--n-100)", color: "var(--n-700)", border: "1px solid var(--n-200)",
                      cursor: "pointer", fontFamily: "var(--font-mono)",
                    }}
                  >
                    {`{{${v}}}`}
                  </button>
                ))}
              </div>
            </div>
          )}

          <BtnSecondary onClick={previsualizar} disabled={cargandoPreview}>
            {cargandoPreview ? "Generando…" : "Vista previa"}
          </BtnSecondary>

          {previsualizacion && (
            <Card padding={14} style={{ background: "var(--canvas)" }}>
              <div style={{ fontSize: 10.5, color: "var(--n-500)", textTransform: "uppercase", letterSpacing: ".04em", marginBottom: 6 }}>
                Vista previa · datos de ejemplo
              </div>
              <div style={{ fontSize: 13.5, fontWeight: 600, color: "var(--n-900)", marginBottom: 6 }}>{previsualizacion.subject}</div>
              <div style={{ fontSize: 13, color: "var(--n-700)", whiteSpace: "pre-wrap" }}>{previsualizacion.body}</div>
            </Card>
          )}

          {error && <div style={{ fontSize: 12.5, color: "var(--danger)" }}>{error}</div>}

          <div style={{ display: "flex", gap: 8, marginTop: 4 }}>
            <BtnSecondary onClick={onClose} style={{ flex: 1 }}>Cerrar</BtnSecondary>
            {esAdmin && (
              <>
                <BtnSecondary onClick={restaurar} disabled={restaurando || plantilla.origen === "default"} style={{ flex: 1 }}>
                  {restaurando ? "Restaurando…" : "Restaurar default"}
                </BtnSecondary>
                <BtnPrimary onClick={guardar} disabled={guardando} style={{ flex: 1 }}>
                  {guardando ? "Guardando…" : "Guardar"}
                </BtnPrimary>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
