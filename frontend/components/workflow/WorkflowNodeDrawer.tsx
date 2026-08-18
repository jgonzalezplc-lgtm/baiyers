"use client";

import { useEffect, useState } from "react";
import { Plus, Trash2, X } from "lucide-react";
import { BtnGhost, BtnPrimary, Input } from "@/components/ui";
import { InterpretedField } from "./InterpretedField";
import { CollapsibleNodeSummary } from "./CollapsibleNodeSummary";
import { NodeCommunicationsPanel, type ReglaComunicacion } from "./NodeCommunicationsPanel";
import {
  ROLES_BASE, CAMPOS_CONDICION, OPERADORES, TIPOS, entradaFallback, procesoFallback, prefersReducedMotion,
  type Nodo, type Conexion, type AsignacionNodo, type ResponsableInfo, type ErrorValidacion,
} from "./canvasTypes";

export function WorkflowNodeDrawer({
  nodo, nodos, conexiones, onClose, onUpdateNodo, onDeleteNodo,
  puedeEditarConfiguracion, asignaciones, responsablesOrg,
  asignandoRol, setAsignandoRol, nuevoNombre, setNuevoNombre, nuevoEmail, setNuevoEmail,
  guardandoResponsable, modoAsignacionPorRol, setModoAsignacionPorRol,
  asignarExistente, crearYAsignar, quitarAsignacion,
  workflowId, reglasComunicacion, esAdmin, workflowEstado, crearVersionConCambios, cargarConfiguracion,
  errores,
}: {
  nodo: Nodo;
  nodos: Nodo[];
  conexiones: Conexion[];
  onClose: () => void;
  onUpdateNodo: (id: string, cambios: Partial<Nodo>) => void;
  onDeleteNodo: (id: string) => void;
  puedeEditarConfiguracion: boolean;
  asignaciones: AsignacionNodo[];
  responsablesOrg: ResponsableInfo[];
  asignandoRol: string | null;
  setAsignandoRol: (rol: string | null) => void;
  nuevoNombre: string;
  setNuevoNombre: (v: string) => void;
  nuevoEmail: string;
  setNuevoEmail: (v: string) => void;
  guardandoResponsable: boolean;
  modoAsignacionPorRol: Record<string, "individual" | "paralelo" | "secuencial">;
  setModoAsignacionPorRol: (updater: (prev: Record<string, "individual" | "paralelo" | "secuencial">) => Record<string, "individual" | "paralelo" | "secuencial">) => void;
  asignarExistente: (rol: string, responsableId: string) => void;
  crearYAsignar: (rol: string) => void;
  quitarAsignacion: (rol: string, assignmentId: string) => void;
  workflowId: string;
  reglasComunicacion: ReglaComunicacion[];
  esAdmin: boolean;
  workflowEstado: string;
  crearVersionConCambios: (navegar?: boolean) => Promise<string | null>;
  cargarConfiguracion: () => Promise<void>;
  errores: ErrorValidacion[] | null;
}) {
  const [visible, setVisible] = useState(false);
  useEffect(() => {
    const t = setTimeout(() => setVisible(true), 10);
    return () => clearTimeout(t);
  }, [nodo.id]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      const tag = (document.activeElement?.tagName || "").toLowerCase();
      if (tag === "input" || tag === "textarea") return;
      onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const transition = prefersReducedMotion() ? "none" : "transform 240ms ease, opacity 240ms ease";
  const eliminable = nodo.tipo !== "inicio" && nodo.tipo !== "fin";
  const tipoLabel = TIPOS.find(t => t.valor === nodo.tipo)?.label ?? nodo.tipo;

  return (
    <div
      role="dialog"
      aria-label={`Propiedades de ${nodo.nombre}`}
      style={{
        position: "fixed", top: 0, right: 0, bottom: 0, width: "min(400px, 92vw)",
        background: "var(--surface)", borderLeft: "1px solid var(--n-200)", boxShadow: "var(--shadow-modal)",
        zIndex: 40, display: "flex", flexDirection: "column",
        transform: visible ? "translateX(0)" : "translateX(24px)",
        opacity: visible ? 1 : 0, transition,
      }}
    >
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 8, padding: "16px 16px 12px", borderBottom: "1px solid var(--n-200)", flexShrink: 0 }}>
        <div style={{ minWidth: 0 }}>
          <div style={{ fontSize: 15, fontWeight: 600, color: "var(--n-900)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{nodo.nombre}</div>
          <div style={{ fontSize: 11.5, color: "var(--n-500)", marginTop: 2 }}>{tipoLabel}</div>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 6, flexShrink: 0 }}>
          {eliminable && (
            <button
              aria-label="Eliminar tarjeta"
              title="Eliminar tarjeta"
              onClick={() => { onDeleteNodo(nodo.id); onClose(); }}
              style={{ border: 0, background: "none", cursor: "pointer", color: "var(--n-400)", padding: 4 }}
            >
              <Trash2 size={15} />
            </button>
          )}
          <button aria-label="Cerrar" title="Cerrar" onClick={onClose} style={{ border: 0, background: "none", cursor: "pointer", color: "var(--n-500)", padding: 4 }}>
            <X size={17} />
          </button>
        </div>
      </div>

      <div style={{ flex: 1, overflowY: "auto", padding: 16, display: "flex", flexDirection: "column", gap: 12 }}>
        <Input label="Nombre" value={nodo.nombre} onChange={e => onUpdateNodo(nodo.id, { nombre: e.target.value })} />

        {nodo.tipo !== "inicio" && nodo.tipo !== "fin" && (
          <>
            <InterpretedField
              label="Entrada interpretada"
              value={nodo.entrada || ""}
              fallback={entradaFallback(nodo, nodos, conexiones)}
              placeholder="Ej: la lista de ítems con sus definitivos"
              onSave={v => onUpdateNodo(nodo.id, { entrada: v })}
            />
            <InterpretedField
              label="Qué debe hacer"
              value={nodo.proceso || ""}
              fallback={procesoFallback(nodo)}
              placeholder="Ej: revisar y decidir si autoriza la compra"
              onSave={v => onUpdateNodo(nodo.id, { proceso: v })}
            />
          </>
        )}

        {["tarea_humana", "revision", "autorizacion", "homologacion"].includes(nodo.tipo) && (
          <div>
            <div style={{ fontSize: 12, fontWeight: 600, color: "var(--n-600)", marginBottom: 6 }}>Roles</div>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 5 }}>
              {ROLES_BASE.map(r => {
                const activo = (nodo.roles || []).includes(r);
                return (
                  <button key={r} onClick={() => {
                    const roles = activo ? (nodo.roles || []).filter(x => x !== r) : [...(nodo.roles || []), r];
                    onUpdateNodo(nodo.id, { roles });
                  }} style={{
                    fontSize: 11.5, padding: "4px 8px", borderRadius: "var(--r-sm)",
                    border: `1px solid ${activo ? "var(--brand)" : "var(--n-300)"}`,
                    background: activo ? "var(--brand-50)" : "var(--surface)",
                    color: activo ? "var(--brand)" : "var(--n-700)", cursor: "pointer",
                  }}>{r}</button>
                );
              })}
            </div>
          </div>
        )}

        {["tarea_humana", "revision", "autorizacion", "homologacion"].includes(nodo.tipo) && (nodo.roles || []).map(rol => {
          const asignados = asignaciones.filter(a => a.nodo_id === nodo.id && a.rol_clave === rol);
          const disponibles = responsablesOrg.filter(r => r.activo && !asignados.some(a => a.responsables?.id === r.id));
          return (
            <div key={rol}>
              <div style={{ display: "flex", justifyContent: "space-between", gap: 6, alignItems: "center", marginBottom: 6 }}>
                <div style={{ fontSize: 11.5, fontWeight: 600, color: "var(--n-600)" }}>Responsables de &quot;{rol}&quot;</div>
                <select
                  disabled={!puedeEditarConfiguracion}
                  value={modoAsignacionPorRol[rol] || asignados[0]?.modo || "individual"}
                  onChange={e => setModoAsignacionPorRol(prev => ({ ...prev, [rol]: e.target.value as "individual" | "paralelo" | "secuencial" }))}
                  style={{ padding: "3px 5px", fontSize: 10.5, border: "1px solid var(--n-300)", background: "var(--surface)", color: "var(--n-700)" }}
                >
                  <option value="individual">Uno</option><option value="paralelo">Paralelo</option><option value="secuencial">Secuencial</option>
                </select>
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: 5, marginBottom: 6 }}>
                {asignados.length === 0 && <div style={{ fontSize: 11.5, color: "var(--n-500)" }}>Nadie asignado todavía.</div>}
                {asignados.map(a => (
                  <div key={a.id} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 6, fontSize: 11.5, padding: "4px 7px", background: "var(--surface-2)", borderRadius: "var(--r-sm)" }}>
                    <span>{a.modo === "secuencial" && a.orden ? `${a.orden}. ` : ""}{a.responsables?.nombre} <span style={{ color: "var(--n-500)" }}>· {a.responsables?.email}</span></span>
                    {puedeEditarConfiguracion && (
                      <button
                        aria-label={`Quitar a ${a.responsables?.nombre} de ${rol}`}
                        onClick={() => quitarAsignacion(rol, a.id)}
                        disabled={guardandoResponsable}
                        style={{ border: 0, background: "none", color: "var(--n-400)", cursor: "pointer", padding: 0, flexShrink: 0 }}
                      >
                        <Trash2 size={11} />
                      </button>
                    )}
                  </div>
                ))}
              </div>
              {!puedeEditarConfiguracion ? null : asignandoRol === rol ? (
                <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
                  {disponibles.length > 0 && (
                    <>
                      <select
                        defaultValue=""
                        disabled={guardandoResponsable}
                        onChange={e => { if (e.target.value) asignarExistente(rol, e.target.value); }}
                        style={{ width: "100%", padding: "5px 6px", fontSize: 11.5, borderRadius: "var(--r-sm)", border: "1px solid var(--n-300)", background: "var(--surface)", color: "var(--n-900)" }}
                      >
                        <option value="">Elegir existente…</option>
                        {disponibles.map(r => <option key={r.id} value={r.id}>{r.nombre} · {r.email}</option>)}
                      </select>
                      <div style={{ fontSize: 10, color: "var(--n-500)", marginTop: -2 }}>Se asigna al instante, no hace falta llenar nada más abajo.</div>
                    </>
                  )}
                  <div style={{ fontSize: 10.5, color: "var(--n-500)", marginTop: 4 }}>o crear uno nuevo:</div>
                  <input placeholder="Nombre" value={nuevoNombre} onChange={e => setNuevoNombre(e.target.value)} style={{ padding: "5px 6px", fontSize: 11.5, borderRadius: "var(--r-sm)", border: "1px solid var(--n-300)", background: "var(--surface)", color: "var(--n-900)" }} />
                  <input placeholder="Email" type="email" value={nuevoEmail} onChange={e => setNuevoEmail(e.target.value)} style={{ padding: "5px 6px", fontSize: 11.5, borderRadius: "var(--r-sm)", border: "1px solid var(--n-300)", background: "var(--surface)", color: "var(--n-900)" }} />
                  <div style={{ display: "flex", gap: 5 }}>
                    <BtnGhost onClick={() => { setAsignandoRol(null); setNuevoNombre(""); setNuevoEmail(""); }} size="sm">Cancelar</BtnGhost>
                    <BtnPrimary onClick={() => crearYAsignar(rol)} disabled={!nuevoNombre.trim() || !nuevoEmail.trim() || guardandoResponsable} size="sm">Crear y asignar</BtnPrimary>
                  </div>
                </div>
              ) : (
                <button onClick={() => setAsignandoRol(rol)} style={{ display: "inline-flex", alignItems: "center", gap: 4, border: 0, background: "none", color: "var(--brand)", fontSize: 11.5, cursor: "pointer", padding: 0 }}>
                  <Plus size={11} /> Agregar responsable
                </button>
              )}
            </div>
          );
        })}

        {nodo.tipo !== "inicio" && nodo.tipo !== "fin" && (
          <div>
            <div style={{ fontSize: 12, fontWeight: 600, color: "var(--n-600)", marginBottom: 4 }}>
              {nodo.tipo === "decision" || nodo.tipo === "autorizacion"
                ? "Ramas de decisión"
                : <>Ramas de decisión <span style={{ fontWeight: 400, color: "var(--n-500)" }}>· opcional</span></>}
            </div>
            <div style={{ fontSize: 10.5, color: "var(--n-500)", marginBottom: 6, lineHeight: 1.4 }}>
              Solo si esta etapa se ramifica en varios caminos alternativos (ej: aprobado / rechazado).
              Cada rama necesita una flecha de salida hacia otro nodo. Si el flujo simplemente
              continúa al siguiente paso, <strong>dejalo vacío</strong>. No uses este campo
              para describir qué datos produce la etapa (para eso está &quot;Qué debe hacer&quot;).
            </div>
            <Input
              value={(nodo.resultados || []).join(", ")}
              onChange={e => onUpdateNodo(nodo.id, { resultados: e.target.value.split(",").map(s => s.trim()).filter(Boolean) })}
              placeholder={nodo.tipo === "decision" || nodo.tipo === "autorizacion" ? "aprobado, rechazado" : "vacío = una sola salida"}
            />
            {nodo.tipo === "autorizacion" && (
              <div style={{ fontSize: 10.5, color: "var(--n-500)", marginTop: 4, lineHeight: 1.4 }}>
                El motor real hoy solo distingue aprobado/rechazado (&quot;con observaciones&quot; ya existe como variante de aprobado en el correo de autorización). Salidas adicionales quedan documentadas en el grafo pero no cambian el ruteo todavía.
              </div>
            )}
            {!["decision", "autorizacion"].includes(nodo.tipo) && (nodo.resultados || []).length > 0 && (
              <div style={{ fontSize: 10.5, color: "var(--n-500)", marginTop: 4, lineHeight: 1.4 }}>
                Esta etapa todavía no tiene ejecución real conectada (solo el paso de autorización la tiene) — las ramas quedan como documentación del proceso y validan el grafo.
              </div>
            )}
          </div>
        )}

        {nodo.tipo === "decision" && (
          <div>
            <div style={{ fontSize: 12, fontWeight: 600, color: "var(--n-600)", marginBottom: 6 }}>Condición</div>
            <select
              value={nodo.condicion_entrada?.campo ?? ""}
              onChange={e => onUpdateNodo(nodo.id, { condicion_entrada: { campo: e.target.value, operador: nodo.condicion_entrada?.operador ?? ">", valor: nodo.condicion_entrada?.valor ?? "" } })}
              style={{ width: "100%", padding: "7px 8px", fontSize: 12.5, borderRadius: "var(--r-sm)", border: "1px solid var(--n-300)", background: "var(--surface)", color: "var(--n-900)", marginBottom: 6 }}
            >
              <option value="">Sin condición</option>
              {CAMPOS_CONDICION.map(c => <option key={c} value={c}>{c}</option>)}
            </select>
            {nodo.condicion_entrada?.campo && (
              <div style={{ display: "flex", gap: 6 }}>
                <select
                  value={nodo.condicion_entrada?.operador ?? ">"}
                  onChange={e => onUpdateNodo(nodo.id, { condicion_entrada: { ...nodo.condicion_entrada!, operador: e.target.value } })}
                  style={{ flex: 1, padding: "7px 8px", fontSize: 12.5, borderRadius: "var(--r-sm)", border: "1px solid var(--n-300)", background: "var(--surface)", color: "var(--n-900)" }}
                >
                  {OPERADORES.map(o => <option key={o} value={o}>{o}</option>)}
                </select>
                <input
                  value={String(nodo.condicion_entrada?.valor ?? "")}
                  onChange={e => onUpdateNodo(nodo.id, { condicion_entrada: { ...nodo.condicion_entrada!, valor: e.target.value } })}
                  style={{ flex: 1, padding: "7px 8px", fontSize: 12.5, borderRadius: "var(--r-sm)", border: "1px solid var(--n-300)", background: "var(--surface)", color: "var(--n-900)" }}
                />
              </div>
            )}
          </div>
        )}

        {reglasComunicacion.some(r => r.nodo_id === nodo.id && ["rfq_requested", "rfq_followup"].includes(r.evento_plantilla)) && (
          <div style={{ borderTop: "1px solid var(--n-200)", paddingTop: 12 }}>
            <div style={{ fontSize: 12, fontWeight: 600, color: "var(--n-700)", marginBottom: 6 }}>Cierre agregado de cotizaciones</div>
            <select
              value={nodo.criterio_cierre || "todos_resueltos"}
              onChange={e => onUpdateNodo(nodo.id, { criterio_cierre: e.target.value as Nodo["criterio_cierre"] })}
              style={{ width: "100%", padding: "7px 8px", fontSize: 12.5, borderRadius: "var(--r-sm)", border: "1px solid var(--n-300)", background: "var(--surface)", color: "var(--n-900)" }}
            >
              <option value="todos_resueltos">Todos respondieron o fueron descartados</option>
              <option value="minimo_respuestas">Alcanzar un mínimo de respuestas</option>
              <option value="cierre_manual">Cierre manual</option>
            </select>
            {(nodo.criterio_cierre || "todos_resueltos") === "minimo_respuestas" && (
              <div style={{ marginTop: 7 }}>
                <Input
                  label="Respuestas completas requeridas"
                  type="number"
                  value={String(nodo.minimo_respuestas || 1)}
                  onChange={e => onUpdateNodo(nodo.id, { minimo_respuestas: Math.max(1, Number(e.target.value) || 1) })}
                />
              </div>
            )}
            <div style={{ fontSize: 10.5, color: "var(--n-500)", marginTop: 5, lineHeight: 1.4 }}>
              El criterio se evalúa por proveedor. Una respuesta incompleta mantiene abierto solamente su loop.
            </div>
          </div>
        )}

        {nodo.tipo === "homologacion" && (
          <div style={{ borderTop: "1px solid var(--n-200)", paddingTop: 12 }}>
            <div style={{ fontSize: 12, fontWeight: 600, color: "var(--n-700)", marginBottom: 5 }}>Antecedentes requeridos</div>
            <div style={{ fontSize: 10.5, color: "var(--n-500)", marginBottom: 6, lineHeight: 1.4 }}>
              Uno por línea. Evita pedir credenciales, claves o documentos personales innecesarios.
            </div>
            <textarea
              value={(nodo.requisitos_homologacion || []).join("\n")}
              onChange={e => onUpdateNodo(nodo.id, { requisitos_homologacion: e.target.value.split("\n").map(v => v.trim()).filter(Boolean) })}
              placeholder={"Razón social, RUT, giro y domicilio\nCertificado bancario de titularidad\nCondiciones de pago"}
              rows={5}
              style={{ width: "100%", resize: "vertical", padding: 8, fontFamily: "inherit", fontSize: 11.5, lineHeight: 1.45, border: "1px solid var(--n-300)", background: "var(--surface)", color: "var(--n-900)", borderRadius: "var(--r-sm)" }}
            />
          </div>
        )}

        {nodo.tipo !== "inicio" && nodo.tipo !== "fin" && (
          <div style={{ borderTop: "1px solid var(--n-200)", paddingTop: 12 }}>
            <NodeCommunicationsPanel
              workflowId={workflowId}
              nodoId={nodo.id}
              roles={nodo.roles || []}
              resultados={nodo.resultados || []}
              reglas={reglasComunicacion.filter(r => r.nodo_id === nodo.id)}
              readOnly={!puedeEditarConfiguracion}
              esAdmin={esAdmin}
              onCrearBorrador={workflowEstado === "activo" ? () => crearVersionConCambios(false) : undefined}
              onChanged={cargarConfiguracion}
            />
          </div>
        )}

        {nodo.tipo !== "inicio" && nodo.tipo !== "fin" && (
          <CollapsibleNodeSummary>
            <div style={{ fontSize: 11.5, lineHeight: 1.55, color: "var(--n-600)", padding: 9, background: "var(--canvas)", border: "1px solid var(--n-200)" }}>
              {(nodo.roles || []).length > 0
                ? `${(nodo.roles || []).join(", ")} ejecuta “${nodo.nombre}”. `
                : `“${nodo.nombre}” no tiene roles humanos. `}
              {asignaciones.filter(a => a.nodo_id === nodo.id).length} responsable(s) asignado(s) y {reglasComunicacion.filter(r => r.nodo_id === nodo.id).length} comunicación(es) configurada(s).
              {reglasComunicacion.filter(r => r.nodo_id === nodo.id && r.repetir_cada_dias).map(r => ` Repite ${r.evento_plantilla} cada ${r.repetir_cada_dias} días hasta ${r.evento_termino || "un evento pendiente"}.`).join("")}
            </div>
            {(errores || []).filter(e => e.nodo_id === nodo.id).map((e, i) => (
              <div key={`${e.codigo}-${i}`} style={{ fontSize: 11, color: "var(--danger)", marginTop: 5 }}>· {e.mensaje}</div>
            ))}
          </CollapsibleNodeSummary>
        )}
      </div>
    </div>
  );
}
