// Tipos y constantes compartidos entre page.tsx y los componentes extraídos
// del canvas del workflow. Puramente presentacional/estructural — sin
// llamadas a red ni lógica de negocio.

export interface Posicion { x: number; y: number }

export interface Condicion {
  campo: string;
  operador: string;
  valor: string | number;
}

export interface Nodo {
  id: string;
  tipo: string;
  nombre: string;
  roles?: string[];
  resultados?: string[];
  condicion_entrada?: Condicion | null;
  posicion?: Posicion;
  entrada?: string;
  proceso?: string;
  criterio_cierre?: "todos_resueltos" | "minimo_respuestas" | "cierre_manual";
  minimo_respuestas?: number;
  requisitos_homologacion?: string[];
}

export interface Conexion {
  origen_nodo_id: string;
  destino_nodo_id: string;
  resultado?: string;
}

export interface ResponsableInfo {
  id: string;
  nombre: string;
  cargo?: string | null;
  email: string | null;
  telefono?: string | null;
  activo: boolean;
}

export interface AsignacionRol {
  id: string;
  rol_clave: string;
  orden_autorizacion: number | null;
  responsables: ResponsableInfo;
}

export interface AsignacionNodo {
  id: string;
  nodo_id: string;
  rol_clave: string;
  modo: "individual" | "paralelo" | "secuencial";
  orden: number | null;
  es_propietario_excepcion: boolean;
  responsables: ResponsableInfo;
}

export interface Workflow {
  id: string;
  nombre: string;
  estado: string;
  nodos: Nodo[];
  conexiones: Conexion[];
  roles?: { clave: string; nombre: string }[];
  responsables?: AsignacionRol[];
}

export interface ErrorValidacion {
  codigo: string;
  mensaje: string;
  nodo_id?: string;
}

export const TIPOS: { valor: string; label: string }[] = [
  { valor: "tarea_humana", label: "Tarea humana" },
  { valor: "revision", label: "Revisión" },
  { valor: "autorizacion", label: "Autorización" },
  { valor: "decision", label: "Decisión / condición" },
  { valor: "accion_automatica", label: "Acción automática" },
  { valor: "homologacion", label: "Homologación" },
  { valor: "emision_oc", label: "Emisión de OC" },
  { valor: "compra_sin_oc", label: "Compra sin OC" },
  { valor: "espera_documento", label: "Espera de documento" },
];

export const ROLES_BASE = ["cotizador", "revisor", "autorizador", "homologador", "comprador"];
export const CAMPOS_CONDICION = ["monto_total", "moneda", "categoria", "centro_costo", "proyecto", "proveedor_nuevo", "proveedor_homologado", "requiere_oc"];
export const OPERADORES = [">", ">=", "<", "<=", "==", "!=", "in", "not in"];

export const NODE_W = 168;
export const NODE_H = 60;

export const COLOR_RESULTADO: Record<string, string> = {
  aprobado: "var(--success)",
  rechazado: "var(--danger)",
  default: "var(--n-500)",
};

export function colorClaveResultado(resultado?: string): string {
  const r = (resultado || "").toLowerCase();
  if (r.includes("aprob")) return "aprobado";
  if (r.includes("rechaz")) return "rechazado";
  return "default";
}

export function colorNodo(tipo: string): string {
  if (tipo === "inicio") return "var(--success)";
  if (tipo === "fin") return "var(--n-700)";
  if (tipo === "decision") return "var(--st-cotizando-fg)";
  if (tipo === "autorizacion") return "var(--brand)";
  return "var(--n-500)";
}

// Texto legible cuando el workflow no trae `entrada`/`proceso` interpretados
// (workflows creados antes de que el backend los generara). Determinístico,
// a partir de nombres de nodos y conexiones — nunca IA nueva.
export function entradaFallback(nodo: Nodo, nodos: Nodo[], conexiones: Conexion[]): string {
  const entrantes = conexiones.filter(c => c.destino_nodo_id === nodo.id);
  if (entrantes.length === 0) {
    return "No tiene una etapa anterior conectada todavía — revisa las conexiones del grafo.";
  }
  const partes = entrantes.map(c => {
    const origen = nodos.find(n => n.id === c.origen_nodo_id);
    const nombreOrigen = origen?.nombre || c.origen_nodo_id;
    return c.resultado
      ? `lo que sale de "${nombreOrigen}" cuando el resultado es "${c.resultado}"`
      : `lo que produce "${nombreOrigen}"`;
  });
  return `Recibe ${partes.join(" y ")}.`;
}

export function procesoFallback(nodo: Nodo): string {
  const tipoLabel = TIPOS.find(t => t.valor === nodo.tipo)?.label || nodo.tipo;
  const roles = (nodo.roles || []).join(", ");
  const resultados = (nodo.resultados || []).join(" / ");
  let base = `Ejecuta "${nodo.nombre}" (${tipoLabel})`;
  if (roles) base += ` a cargo de ${roles}`;
  base += ".";
  if (resultados) base += ` Puede resolver en: ${resultados}.`;
  return base;
}

export function prefersReducedMotion(): boolean {
  return typeof window !== "undefined" && !!window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
}
