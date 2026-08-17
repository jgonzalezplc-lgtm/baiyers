"use client";

import { useEffect, useMemo, useState } from "react";
import { Mail, Plus, RefreshCw, Trash2 } from "lucide-react";
import { authFetch } from "@/lib/authFetch";
import { BtnGhost, BtnPrimary, BtnSecondary } from "@/components/ui";
import { MailTemplateEditor, type PlantillaCorreo } from "./MailTemplateEditor";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export interface ReglaComunicacion {
  id: string;
  nodo_id: string;
  rol_clave?: string | null;
  evento_plantilla: string;
  audiencia: "internal" | "external";
  destinatario_tipo: string;
  disparador_tipo: string;
  disparador_evento?: string | null;
  demora_inicial_dias: number;
  repetir_cada_dias?: number | null;
  max_intentos?: number | null;
  evento_termino?: string | null;
  alcance_termino: string;
  resultado_al_terminar?: string | null;
  politica_agotamiento?: string | null;
  resultado_agotamiento?: string | null;
  activa: boolean;
}

const fieldStyle = { width: "100%", padding: "7px 8px", fontSize: 12, borderRadius: "var(--r-sm)", border: "1px solid var(--n-300)", background: "var(--surface)", color: "var(--n-900)" } as const;

export function NodeCommunicationsPanel({ workflowId, nodoId, roles, resultados, reglas, readOnly, onChanged }: {
  workflowId: string;
  nodoId: string;
  roles: string[];
  resultados: string[];
  reglas: ReglaComunicacion[];
  readOnly: boolean;
  onChanged: () => Promise<void>;
}) {
  const [plantillas, setPlantillas] = useState<PlantillaCorreo[]>([]);
  const [agregando, setAgregando] = useState(false);
  const [editandoPlantilla, setEditandoPlantilla] = useState<PlantillaCorreo | null>(null);
  const [guardando, setGuardando] = useState(false);
  const [error, setError] = useState("");
  const [form, setForm] = useState({
    evento_plantilla: "", rol_clave: roles[0] || "", destinatario_tipo: "proveedor",
    disparador_tipo: "al_entrar", disparador_evento: "", demora_inicial_dias: 0,
    repetir: false, repetir_cada_dias: 2, max_intentos: 3, evento_termino: "",
    alcance_termino: "tarjeta", resultado_al_terminar: "",
    politica_agotamiento: "pausar", resultado_agotamiento: "",
  });

  const cargarPlantillas = async () => {
    const data = await authFetch(`${API_URL}/api/mail-templates?workflow_id=${workflowId}&nodo_id=${encodeURIComponent(nodoId)}`).then(r => r.json()).catch(() => []);
    setPlantillas(Array.isArray(data) ? data : []);
  };
  useEffect(() => { cargarPlantillas(); }, [workflowId, nodoId]);

  const plantillaElegida = useMemo(() => plantillas.find(p => p.evento === form.evento_plantilla), [plantillas, form.evento_plantilla]);
  const elegirEvento = (evento: string) => {
    const p = plantillas.find(x => x.evento === evento);
    setForm(f => ({ ...f, evento_plantilla: evento, destinatario_tipo: p?.audiencia === "internal" ? "responsable_rol" : "proveedor" }));
  };

  const guardar = async () => {
    if (!form.evento_plantilla) return;
    setGuardando(true); setError("");
    try {
      const payload = {
        nodo_id: nodoId, rol_clave: form.rol_clave || null,
        evento_plantilla: form.evento_plantilla, destinatario_tipo: form.destinatario_tipo,
        disparador_tipo: form.disparador_tipo,
        disparador_evento: form.disparador_tipo === "al_ocurrir_evento" ? form.disparador_evento || null : null,
        demora_inicial_dias: Number(form.demora_inicial_dias) || 0,
        repetir_cada_dias: form.repetir ? Number(form.repetir_cada_dias) : null,
        max_intentos: form.repetir ? Number(form.max_intentos) : 1,
        evento_termino: form.repetir ? form.evento_termino || null : null,
        alcance_termino: form.alcance_termino,
        resultado_al_terminar: form.resultado_al_terminar || null,
        politica_agotamiento: form.repetir ? form.politica_agotamiento : null,
        resultado_agotamiento: form.repetir && form.politica_agotamiento === "avanzar_timeout" ? form.resultado_agotamiento || null : null,
      };
      const res = await authFetch(`${API_URL}/api/workflows/${workflowId}/reglas-comunicacion`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
      if (!res.ok) { const data = await res.json().catch(() => ({})); throw new Error(data.detail || "No se pudo guardar la regla"); }
      setAgregando(false); await onChanged();
    } catch (e) { setError(e instanceof Error ? e.message : "No se pudo guardar"); }
    finally { setGuardando(false); }
  };

  const eliminar = async (id: string) => {
    const res = await authFetch(`${API_URL}/api/workflows/${workflowId}/reglas-comunicacion/${id}`, { method: "DELETE" });
    if (res.ok) await onChanged();
  };

  const descripcionRegla = (r: ReglaComunicacion) => {
    const plantilla = plantillas.find(p => p.evento === r.evento_plantilla);
    const inicio = r.disparador_tipo === "al_entrar" ? "al entrar" : r.disparador_tipo === "manual" ? "manual" : r.disparador_tipo === "despues_demora" ? `después de ${r.demora_inicial_dias} días` : `cuando ocurra ${r.disparador_evento}`;
    const loop = r.repetir_cada_dias ? ` · cada ${r.repetir_cada_dias} días · máx. ${r.max_intentos || "sin límite"}` : " · una vez";
    return `${plantilla?.descripcion || r.evento_plantilla} · ${inicio}${loop}`;
  };

  return <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
      <div><div style={{ fontSize: 12, fontWeight: 600, color: "var(--n-700)" }}>Comunicaciones</div><div style={{ fontSize: 10.5, color: "var(--n-500)" }}>Plantilla, destinatario, cadencia y término.</div></div>
      {!readOnly && <BtnGhost size="sm" onClick={() => setAgregando(v => !v)}><Plus size={11} /> Agregar</BtnGhost>}
    </div>
    {reglas.length === 0 && !agregando && <div style={{ fontSize: 11.5, color: "var(--n-500)", padding: 9, border: "1px dashed var(--n-300)" }}>Esta tarjeta no envía correos.</div>}
    {reglas.map(r => <div key={r.id} style={{ padding: 9, border: "1px solid var(--n-200)", background: "var(--surface-2)" }}>
      <div style={{ display: "flex", gap: 6, justifyContent: "space-between" }}><div style={{ fontSize: 11.5, color: "var(--n-800)", lineHeight: 1.4 }}>{descripcionRegla(r)}</div>{!readOnly && <button onClick={() => eliminar(r.id)} style={{ border: 0, background: "none", color: "var(--n-400)", cursor: "pointer" }}><Trash2 size={12} /></button>}</div>
      <div style={{ fontSize: 10.5, color: "var(--n-500)", marginTop: 4 }}>{r.audiencia === "internal" ? "Interno" : "Externo"} → {r.destinatario_tipo}{r.evento_termino ? ` · termina con ${r.evento_termino}` : ""}</div>
      <button onClick={() => { const p = plantillas.find(x => x.evento === r.evento_plantilla); if (p) setEditandoPlantilla(p); }} style={{ border: 0, background: "none", color: "var(--brand)", fontSize: 10.5, padding: "5px 0 0", cursor: "pointer" }}><Mail size={10} /> Editar correo para esta tarjeta</button>
    </div>)}

    {agregando && <div style={{ padding: 10, border: "1px solid var(--brand-100)", background: "var(--brand-50)", display: "flex", flexDirection: "column", gap: 8 }}>
      <label style={{ fontSize: 10.5, color: "var(--n-600)" }}>Correo<select value={form.evento_plantilla} onChange={e => elegirEvento(e.target.value)} style={fieldStyle}><option value="">Seleccionar plantilla…</option>{plantillas.map(p => <option key={p.evento} value={p.evento}>{p.audiencia === "internal" ? "Interno" : "Externo"} · {p.descripcion}</option>)}</select></label>
      {roles.length > 0 && <label style={{ fontSize: 10.5, color: "var(--n-600)" }}>Rol dueño<select value={form.rol_clave} onChange={e => setForm(f => ({ ...f, rol_clave: e.target.value }))} style={fieldStyle}>{roles.map(r => <option key={r}>{r}</option>)}</select></label>}
      <label style={{ fontSize: 10.5, color: "var(--n-600)" }}>Destinatario<select value={form.destinatario_tipo} onChange={e => setForm(f => ({ ...f, destinatario_tipo: e.target.value }))} style={fieldStyle}>{plantillaElegida?.audiencia === "internal" ? <><option value="responsable_rol">Responsable del rol</option><option value="solicitante">Solicitante</option><option value="autorizador">Autorizador</option><option value="equipo">Equipo</option></> : <><option value="proveedor">Proveedor</option><option value="contacto_proveedor">Contacto del proveedor</option></>}</select></label>
      <label style={{ fontSize: 10.5, color: "var(--n-600)" }}>Disparador<select value={form.disparador_tipo} onChange={e => setForm(f => ({ ...f, disparador_tipo: e.target.value }))} style={fieldStyle}><option value="al_entrar">Al entrar a la tarjeta</option><option value="despues_demora">Después de una demora</option><option value="al_ocurrir_evento">Al ocurrir un evento</option><option value="manual">Manual</option></select></label>
      {form.disparador_tipo === "al_ocurrir_evento" && <input value={form.disparador_evento} onChange={e => setForm(f => ({ ...f, disparador_evento: e.target.value }))} placeholder="Evento disparador" style={fieldStyle} />}
      {form.disparador_tipo === "despues_demora" && <input type="number" min={0} value={form.demora_inicial_dias} onChange={e => setForm(f => ({ ...f, demora_inicial_dias: Number(e.target.value) }))} style={fieldStyle} />}
      <label style={{ fontSize: 11.5, display: "flex", gap: 6, alignItems: "center" }}><input type="checkbox" checked={form.repetir} onChange={e => setForm(f => ({ ...f, repetir: e.target.checked }))} /> Repetir hasta que ocurra un evento</label>
      {form.repetir && <><div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 6 }}><label style={{ fontSize: 10.5 }}>Cada X días<input type="number" min={1} value={form.repetir_cada_dias} onChange={e => setForm(f => ({ ...f, repetir_cada_dias: Number(e.target.value) }))} style={fieldStyle} /></label><label style={{ fontSize: 10.5 }}>Máx. intentos<input type="number" min={1} value={form.max_intentos} onChange={e => setForm(f => ({ ...f, max_intentos: Number(e.target.value) }))} style={fieldStyle} /></label></div><input value={form.evento_termino} onChange={e => setForm(f => ({ ...f, evento_termino: e.target.value }))} placeholder="Evento de término, ej: rfq_completa" style={fieldStyle} /><select value={form.politica_agotamiento} onChange={e => setForm(f => ({ ...f, politica_agotamiento: e.target.value }))} style={fieldStyle}><option value="pausar">Al agotar: pausar</option><option value="escalar">Al agotar: escalar</option><option value="descartar_entidad">Al agotar: descartar proveedor</option><option value="avanzar_timeout">Al agotar: avanzar por resultado</option></select>{form.politica_agotamiento === "avanzar_timeout" && <select value={form.resultado_agotamiento} onChange={e => setForm(f => ({ ...f, resultado_agotamiento: e.target.value }))} style={fieldStyle}><option value="">Resultado…</option>{resultados.map(r => <option key={r}>{r}</option>)}</select>}</>}
      {error && <div style={{ fontSize: 11.5, color: "var(--danger)" }}>{error}</div>}
      <div style={{ display: "flex", gap: 6 }}><BtnSecondary size="sm" onClick={() => setAgregando(false)}>Cancelar</BtnSecondary><BtnPrimary size="sm" onClick={guardar} disabled={guardando || !form.evento_plantilla}>{guardando ? "Guardando…" : "Guardar regla"}</BtnPrimary></div>
    </div>}
    <BtnSecondary size="sm" onClick={cargarPlantillas}><RefreshCw size={11} /> Actualizar plantillas</BtnSecondary>
    {editandoPlantilla && <MailTemplateEditor plantilla={editandoPlantilla} esAdmin={!readOnly} workflowId={workflowId} nodoId={nodoId} onClose={() => setEditandoPlantilla(null)} onGuardado={async () => { setEditandoPlantilla(null); await cargarPlantillas(); }} />}
  </div>;
}
