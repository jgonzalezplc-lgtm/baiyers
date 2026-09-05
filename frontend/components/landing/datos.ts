/** Datos compartidos entre la landing visible y sus metadatos estructurados. */
export const SITIO = "https://www.baiyer.cl";
export const DEMO_URL =
  "https://calendar.google.com/calendar/appointments/schedules/AcZssZ2zYeSsbI9JFgNYuP0u0NRfL5PfmjfEyvmNpG6100iqW-wCC6SCTVsBvhBYaiX4Gx1SHTp4tUhG?gv=true";

/** Paleta del diseño. Es la landing pública: no usa los tokens del producto. */
export const C = {
  azul: "#1000FF",
  tinta: "#111111",
  cuerpo: "#3A3A38",
  mudo: "#6B6B68",
  papel: "#F7F7F5",
  panel: "#F0EFEC",
  regla: "#D6D4CF",
  reglaSuave: "#E2E1DD",
  azulTinte: "#EDEBFF",
  lavanda: "#E6E2FF",
  lavandaMuda: "#B8B0FF",
  verde: "#15803d",
  verdeTinte: "#DCFCE7",
  verdeOscuro: "#14532d",
  ambar: "#b45309",
  ambarOscuro: "#78350f",
  ambarTinte: "#FEF3C7",
  apagado: "#B4B3AE",
} as const;

/**
 * Display pixel-art, self-hosted vía `@font-face` en `globals.css`.
 * La mono la carga `next/font` en el layout, así que va por su variable: el
 * nombre "JetBrains Mono" a secas no resuelve (next/font ofusca la familia).
 */
export const DISPLAY = "'PP Mondwest',ui-monospace,monospace";
export const MONO = "var(--font-jetbrains),ui-monospace,monospace";

/** Frases que cicla el titular del hero. */
export const FRASES = [
  "Tu Agente Especial para compras está aquí!",
  "Reduzco el tiempo de compras de semanas a minutos",
  "Dime lo que necesitas y yo me encargo del resto :)",
];

/**
 * Títulos de sección. Cada uno es `[antes, destacado, después]`: el tramo del
 * medio se pinta azul con glow. El índice es el orden de tipeo, no el visual.
 */
export const TITULOS: [string, string, string][] = [
  ["Hola! Soy Baiyer, tu empleado digital para procurement", "", ""],
  ["Hago desde la cotización hasta el ", "pago", ""],
  ["No se me escapa ", "nada!", ""],
  ["Me ", "adapto", " a cada etapa de tu proceso de compra"],
  ["Preguntas ", "frecuentes", ""],
];

/** Etapas del ciclo de compra que recorre el grafo serpenteante. */
export const ACTORES = [
  { t: "GATILLO", bg: C.panel, fg: C.tinta, bd: C.tinta },
  { t: "BAIYER", bg: C.azulTinte, fg: C.azul, bd: C.azul },
  { t: "HUMANO", bg: C.verdeTinte, fg: C.verdeOscuro, bd: C.verde },
  { t: "FIRMA", bg: C.ambarTinte, fg: C.ambarOscuro, bd: C.ambar },
] as const;

export type Etapa = {
  label: string;
  role: string;
  actor: 0 | 1 | 2 | 3;
  edgeLabel?: string;
  edgeColor?: string;
  person?: string;
};

export const ETAPAS: Etapa[] = [
  { label: "Solicitud de cotización", role: "Pide 5 notebooks por chat", actor: 0, person: "Camila Rojas · Operaciones" },
  { label: "Cotiza con proveedores", role: "Baiyer escribe por correo y pide precio, plazo y stock", actor: 1 },
  { label: "Compara precios en internet", role: "Contrasta catálogos y precios de lista contra lo cotizado", actor: 1 },
  { label: "Arma el informe comparativo", role: "Ranking precio/calidad con plazos de entrega y garantías", actor: 1 },
  { label: "Revisor elige la mejor oferta", role: "Valida specs y selecciona la oferta", actor: 2, person: "Diego Fuentes · Líder TI" },
  { label: "Jefatura autoriza la compra", role: "Aprueba según monto y centro de costo", actor: 2, edgeLabel: "autorizado", edgeColor: C.verde, person: "Paula Vergara · Gerencia" },
  { label: "Solicita antecedentes de homologación", role: "Solo si el proveedor es nuevo: correos pidiendo documentos", actor: 1, edgeLabel: "proveedor nuevo" },
  { label: "Homologa y perfila riesgo", role: "Revisa documentos tributarios, laborales y de seguros", actor: 1 },
  { label: "Emite la orden de compra", role: "Genera la OC en el ERP y la envía al proveedor", actor: 1 },
  { label: "Ejecuta el pago", role: "Tarjeta virtual o transferencia; sobre el tope pide firma", actor: 3, person: "Firma: Rodrigo Salas · Finanzas" },
  { label: "Coordina el despacho", role: "Confirma fecha, tracking y recepción en planta", actor: 1 },
  { label: "Recibe y concilia la factura", role: "Cruza factura contra OC y guía de despacho", actor: 1 },
  { label: "Gestión de inventario", role: "Actualiza stock y avisa cuando toca reponer", actor: 1 },
];

/** Órdenes de compra abiertas + el borrador de correo que Baiyer propone. */
export const ORDENES = [
  {
    initial: "A", name: "Acme Industrial", meta: "Motores · OC-2318",
    status: "6 días de atraso", fg: C.ambar, date: "21 JUL", late: true,
    stage: "SEGUIMIENTO",
    note: "Atención: los 12 rodamientos de la OC-2318 de Acme Industrial estaban prometidos para el martes y aún no despachan. Redacté un seguimiento. ¿Lo envío?",
    to: "rtolbert@acmeindustrial.cl", subject: "OC-2318, fecha de despacho de 12 rodamientos",
    body: "Hola Ray, la OC-2318 (12 rodamientos) estaba comprometida para el 21 de julio y aún no despacha. ¿Puedes confirmarme hoy una fecha? La línea 4 se detiene el jueves sin ellos.",
    cta: "ENVIARLO",
  },
  {
    initial: "G", name: "Grainger", meta: "Repuestos línea 4 · OC-2321",
    status: "En tránsito", fg: C.mudo, date: "30 JUL", late: false,
    stage: "EN TRÁNSITO",
    note: "La OC-2321 salió de bodega ayer. Pedí el número de seguimiento para avisarle a mantención cuándo llega a planta.",
    to: "despachos@grainger.cl", subject: "OC-2321, número de seguimiento del despacho",
    body: "Hola, necesito el tracking de la OC-2321 (repuestos línea 4) para coordinar la recepción en Quilicura. ¿Sigue en pie la entrega del 30 de julio?",
    cta: "ENVIARLO",
  },
  {
    initial: "F", name: "Ferretería Lira", meta: "Insumos planta · OC-2309",
    status: "Entregado", fg: C.verde, date: "18 JUL", late: false,
    stage: "FACTURA",
    note: "Recepción conforme de la OC-2309. Comparé la factura con la orden: cuadra en cantidades y precio, queda lista para pago a 30 días.",
    to: "cobranza@ferreterialira.cl", subject: "OC-2309, factura 88421 conciliada",
    body: "Hola, recibimos completo el 18 de julio. La factura 88421 cuadra con la OC-2309 por $1.284.900 y queda programada para pago el 17 de agosto.",
    cta: "APROBAR PAGO",
  },
  {
    initial: "M", name: "MacOnline", meta: "5 notebooks · OC-2325",
    status: "En tránsito", fg: C.mudo, date: "02 AGO", late: false,
    stage: "DESPACHO",
    note: "Los 5 ThinkPad quedaron confirmados. Estoy pidiendo adelantar el despacho al viernes para que estén listos el lunes.",
    to: "ventas@maconline.cl", subject: "OC-2325, adelantar despacho al viernes",
    body: "Hola, la OC-2325 (5 notebooks) figura para el 2 de agosto. ¿Pueden despachar el viernes 30? Los equipos se entregan a los ingenieros el lunes.",
    cta: "ENVIARLO",
  },
];

/**
 * FAQ canónica. La misma lista alimenta el acordeón visible y el bloque
 * `FAQPage` de datos estructurados: structured data que no coincide con lo
 * visible es motivo de penalización, así que hay una sola fuente.
 */
export const FAQS = [
  { q: "¿Qué es Baiyer?", a: "Baiyer es un empleado digital de compras para empresas en Chile. Automatiza el proceso de procurement B2B: recibe solicitudes, busca proveedores, pide cotizaciones, compara alternativas, gestiona aprobaciones y prepara órdenes de compra." },
  { q: "¿Cómo le pido una compra a Baiyer?", a: "Por correo electrónico, Slack, Microsoft Teams o mediante MCP desde Claude y ChatGPT. También puedes enviarle una foto, un archivo o una lista de materiales." },
  { q: "¿Qué puede entender Baiyer de un pedido?", a: "Interpreta solicitudes escritas en lenguaje natural, listas de productos, cantidades, especificaciones y requerimientos de entrega. Si faltan antecedentes importantes, los solicita antes de cotizar." },
  { q: "¿Dónde busca proveedores y precios?", a: "En la red de proveedores de tu empresa, tiendas chilenas, MercadoLibre y Google Shopping. Los resultados se filtran por relevancia para comparar productos que correspondan al requerimiento." },
  { q: "¿Puede enviar cotizaciones a mis proveedores?", a: "Sí. Prepara y envía las solicitudes de cotización desde el correo de tu empresa, y centraliza las conversaciones con proveedores: precios, disponibilidad, plazos de entrega y condiciones de pago." },
  { q: "¿Cómo compara las cotizaciones?", a: "Organiza las respuestas de los proveedores en un comparativo de compras. El equipo evalúa precio, plazo de entrega, disponibilidad y condiciones comerciales antes de seleccionar una alternativa." },
  { q: "¿Baiyer puede comprar sin autorización?", a: "No. Opera bajo las reglas de compra definidas por tu empresa. Puedes establecer aprobaciones por monto, categoría, proveedor o responsable antes de emitir una orden de compra." },
  { q: "¿Se adapta al proceso de compras de mi empresa?", a: "Sí. Se configura con las categorías, proveedores, responsables y flujos de aprobación de cada empresa. Funciona con reglas simples o con procesos de varias etapas, roles y montos de autorización." },
  { q: "¿Qué pasa después de aprobar una compra?", a: "Baiyer ayuda a preparar y enviar la orden de compra. La plataforma conserva el registro de la decisión y permite seguir cotizaciones, conversaciones, entregas, facturas y compras recurrentes." },
  { q: "¿Sirve para proyectos o compras con muchos productos?", a: "Sí. Permite crear listas de compra multiítem, cotizar cada producto según su especificación y avanzar una compra completa por el flujo de aprobación de la empresa." },
  { q: "¿Qué trazabilidad entrega?", a: "Mantiene un historial de cada solicitud, cotización, respuesta de proveedor, aprobación y orden de compra. Así sabes qué se decidió, quién autorizó y bajo qué condiciones." },
];
