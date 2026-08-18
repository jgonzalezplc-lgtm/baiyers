"use client";

import { useState } from "react";
import { authFetch } from "@/lib/authFetch";
import { BtnPrimary, BtnSecondary, Card, Input, Textarea } from "@/components/ui";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export interface PlantillaCorreo {
  evento: string;
  audiencia: "internal" | "external";
  descripcion: string;
  variables_permitidas: string[];
  subject: string;
  body: string;
  origen: "default" | "organizacion" | "workflow" | "nodo";
  version: number;
  usos_en_nodos?: number;
}

export function MailTemplateEditor({ plantilla, esAdmin, workflowId, nodoId, onClose, onGuardado, crearBorrador }: {
  plantilla: PlantillaCorreo;
  esAdmin: boolean;
  workflowId?: string;
  nodoId?: string;
  onClose: () => void;
  onGuardado: (workflowDestinoId?: string) => void;
  crearBorrador?: () => Promise<string | null>;
}) {
  const [subject, setSubject] = useState(plantilla.subject);
  const [body, setBody] = useState(plantilla.body);
  const [campoConFoco, setCampoConFoco] = useState<"subject" | "body">("body");
  const [previsualizacion, setPrevisualizacion] = useState<{ subject: string; body: string } | null>(null);
  const [cargandoPreview, setCargandoPreview] = useState(false);
  const [guardando, setGuardando] = useState(false);
  const [restaurando, setRestaurando] = useState(false);
  const [error, setError] = useState("");

  const scope = workflowId ? (nodoId ? "esta tarjeta" : "este ciclo") : "toda la organización";
  const insertarVariable = (v: string) => {
    const placeholder = `{{${v}}}`;
    if (campoConFoco === "subject") setSubject(s => `${s}${placeholder}`);
    else setBody(b => `${b}${placeholder}`);
  };

  const previsualizar = async () => {
    setCargandoPreview(true); setError("");
    try {
      const res = await authFetch(`${API_URL}/api/mail-templates/preview`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ evento: plantilla.evento, subject, body, variables_declaradas: plantilla.variables_permitidas }),
      });
      if (!res.ok) { const e = await res.json().catch(() => ({})); throw new Error(e.detail || "No se pudo previsualizar"); }
      setPrevisualizacion(await res.json());
    } catch (e) { setError(e instanceof Error ? e.message : "No se pudo previsualizar"); }
    finally { setCargandoPreview(false); }
  };

  const guardar = async () => {
    setGuardando(true); setError("");
    try {
      const workflowDestinoId = crearBorrador ? await crearBorrador() : workflowId;
      if (crearBorrador && !workflowDestinoId) throw new Error("No se pudo crear el borrador para guardar el correo");
      const res = await authFetch(`${API_URL}/api/mail-templates`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          evento: plantilla.evento, subject, body,
          variables_declaradas: plantilla.variables_permitidas, origen: "user_edit",
          workflow_id: workflowDestinoId, nodo_id: nodoId,
        }),
      });
      if (!res.ok) { const e = await res.json().catch(() => ({})); throw new Error(e.detail || "No se pudo guardar"); }
      onGuardado(workflowDestinoId || undefined);
    } catch (e) { setError(e instanceof Error ? e.message : "No se pudo guardar"); setGuardando(false); }
  };

  const restaurar = async () => {
    setRestaurando(true); setError("");
    try {
      const workflowDestinoId = crearBorrador ? await crearBorrador() : workflowId;
      if (crearBorrador && !workflowDestinoId) throw new Error("No se pudo crear el borrador para restaurar el correo");
      const res = await authFetch(`${API_URL}/api/mail-templates/restaurar-default`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ evento: plantilla.evento, workflow_id: workflowDestinoId, nodo_id: nodoId }),
      });
      if (!res.ok) { const e = await res.json().catch(() => ({})); throw new Error(e.detail || "No se pudo restaurar"); }
      onGuardado(workflowDestinoId || undefined);
    } catch (e) { setError(e instanceof Error ? e.message : "No se pudo restaurar"); setRestaurando(false); }
  };

  return (
    <div onClick={onClose} style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,.45)", zIndex: 200, display: "flex", alignItems: "flex-start", justifyContent: "center", padding: "40px 16px", overflowY: "auto" }}>
      <div onClick={e => e.stopPropagation()} style={{ background: "var(--surface)", borderRadius: "var(--r-lg)", width: "100%", maxWidth: 560, padding: 24, boxShadow: "var(--shadow-pop)" }}>
        <div style={{ fontSize: 16, fontWeight: 600, color: "var(--n-900)", marginBottom: 4 }}>{plantilla.descripcion}</div>
        <div style={{ fontSize: 12, color: "var(--n-500)", marginBottom: 4 }}>{plantilla.evento} · versión {plantilla.version || "default"}</div>
        <div style={{ fontSize: 11.5, color: "var(--brand)", marginBottom: 16 }}>Este cambio aplica sólo a {scope}.</div>

        {crearBorrador && <div style={{ fontSize: 12.5, color: "var(--n-700)", background: "var(--brand-50)", border: "1px solid var(--brand-100)", borderRadius: "var(--r-md)", padding: "10px 12px", marginBottom: 16, lineHeight: 1.5 }}>
          Estás viendo el ciclo activo. Al guardar este correo, Baiyer creará automáticamente un borrador y continuará la edición allí.
        </div>}
        {!esAdmin && <div style={{ fontSize: 12.5, color: "var(--n-700)", background: "var(--brand-50)", border: "1px solid var(--brand-100)", borderRadius: "var(--r-md)", padding: "10px 12px", marginBottom: 16, lineHeight: 1.5 }}>
          Este correo es de solo lectura. Un administrador puede editarlo y Baiyer guardará el cambio automáticamente en un borrador.
        </div>}

        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <div onFocus={() => setCampoConFoco("subject")}><Input label="Asunto" value={subject} onChange={e => setSubject(e.target.value)} disabled={!esAdmin} /></div>
          <div onFocus={() => setCampoConFoco("body")}><Textarea label="Cuerpo" value={body} onChange={esAdmin ? e => setBody(e.target.value) : undefined} disabled={!esAdmin} rows={8} /></div>
          {esAdmin && <div>
            <div style={{ fontSize: 11.5, color: "var(--n-500)", marginBottom: 6 }}>Variables disponibles — clic para insertar:</div>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>{plantilla.variables_permitidas.map(v => (
              <button key={v} type="button" onClick={() => insertarVariable(v)} style={{ fontSize: 11.5, padding: "4px 10px", borderRadius: 999, background: "var(--n-100)", color: "var(--n-700)", border: "1px solid var(--n-200)", cursor: "pointer", fontFamily: "var(--font-mono)" }}>{`{{${v}}}`}</button>
            ))}</div>
          </div>}
          <BtnSecondary onClick={previsualizar} disabled={cargandoPreview}>{cargandoPreview ? "Generando…" : "Vista previa"}</BtnSecondary>
          {previsualizacion && <Card padding={14} style={{ background: "var(--canvas)" }}>
            <div style={{ fontSize: 10.5, color: "var(--n-500)", textTransform: "uppercase", letterSpacing: ".04em", marginBottom: 6 }}>Vista previa · datos de ejemplo</div>
            <div style={{ fontSize: 13.5, fontWeight: 600, color: "var(--n-900)", marginBottom: 6 }}>{previsualizacion.subject}</div>
            <div style={{ fontSize: 13, color: "var(--n-700)", whiteSpace: "pre-wrap" }}>{previsualizacion.body}</div>
          </Card>}
          {error && <div style={{ fontSize: 12.5, color: "var(--danger)" }}>{error}</div>}
          <div style={{ display: "flex", gap: 8, marginTop: 4 }}>
            <BtnSecondary onClick={onClose} style={{ flex: 1 }}>Cerrar</BtnSecondary>
            {esAdmin && <>
              <BtnSecondary onClick={restaurar} disabled={restaurando || (!workflowId && plantilla.origen === "default")} style={{ flex: 1 }}>{restaurando ? "Restaurando…" : workflowId ? "Restaurar herencia" : "Restaurar default"}</BtnSecondary>
              <BtnPrimary onClick={guardar} disabled={guardando} style={{ flex: 1 }}>{guardando ? "Guardando…" : "Guardar"}</BtnPrimary>
            </>}
          </div>
        </div>
      </div>
    </div>
  );
}
