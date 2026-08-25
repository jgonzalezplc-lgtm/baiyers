/**
 * Contenido de la landing, en un módulo sin `"use client"`.
 *
 * Vive aparte para que el mismo texto alimente dos cosas y no puedan
 * desincronizarse: la pantalla (componente cliente) y el JSON-LD que emite el
 * servidor. Un FAQPage cuyas respuestas no coincidan con lo que la página
 * muestra es exactamente lo que Google penaliza como structured data engañoso.
 */

export const SITIO = "https://www.baiyer.cl";
export const HERO_VIDEO = "/landing/videos/baiyer-mcp-claude-screen-progressive-chat.mp4";
export const HERO_POSTER = "/landing/posters/baiyer-mcp-claude-screen-progressive-chat.webp";

export const DEMO_URL = "https://calendar.app.google/LPZDEfVNZU7EM8CR8";

export interface Feature {
  name: string;
  title: string;
  desc: string;
  note: string;
  video: string;
  /** Frame del video, para pintar algo antes de que llegue el mp4. */
  poster: string;
}

export const FEATURES: Feature[] = [
  {
    name: "Describe",
    title: "Describe qué necesitas comprar",
    desc: "Escribe con tus palabras, una foto o un archivo lo que necesitas comprar. Baiyer entiende cada ítem y cantidad, comienza la búsqueda y te ayuda a dimensionar la compra.",
    note: "Todo tu proyecto en un prompt",
    video: "/landing/videos/baiyer-describir-desktop.mp4",
    poster: "/landing/posters/baiyer-describir-desktop.webp",
  },
  {
    name: "Cotizamos por correo",
    title: "Agentes de correo cotizan por ti",
    desc: "Baiyer envía las cotizaciones a tus proveedores desde tu cuenta de correo, lee las respuestas y arma automáticamente el cuadro comparativo para encontrar al mejor proveedor.",
    note: "Para Gmail y Outlook",
    video: "/landing/videos/baiyer-cotizar-por-correo-desktop.mp4",
    poster: "/landing/posters/baiyer-cotizar-por-correo-desktop.webp",
  },
  {
    name: "Compara precios",
    title: "Compara y elige al mejor precio",
    desc: "Compara los precios que tus proveedores de confianza envían por correo con los publicados en tiendas chilenas, MercadoLibre, Google Shopping y proveedores en el extranjero.",
    note: "Informes automáticos con los mejores precios posibles",
    video: "/landing/videos/baiyer-comparar-por-correo-desktop.mp4",
    poster: "/landing/posters/baiyer-comparar-por-correo-desktop.webp",
  },
  {
    name: "Usa tu data",
    title: "Toda tu información en un solo lugar",
    desc: "Conecta tu IA favorita y consulta precios, proveedores y cotizaciones al instante, con tus palabras y sin abrir planillas desactualizadas.",
    note: "Toda tu información al alcance de un prompt",
    video: "/landing/videos/baiyer-consultar-con-ia-desktop.mp4",
    poster: "/landing/posters/baiyer-consultar-con-ia-desktop.webp",
  },
  {
    name: "Aprobaciones y OC",
    title: "Aprueba, genera y envía la orden de compra",
    desc: "Flujo de aprobación con magic link y generación automática de órdenes de compra al aprobar.",
    note: "Nos adaptamos a tu proceso interno y lo automatizamos",
    video: "/landing/videos/baiyer-ordenar-y-aprobar-desktop.mp4",
    poster: "/landing/posters/baiyer-ordenar-y-aprobar-desktop.webp",
  },
  {
    name: "Integraciones",
    title: "Conéctalo a tus sistemas",
    desc: "Conecta Baiyer a tu correo (Gmail u Outlook) y a tu IA preferida (Claude, ChatGPT) para automatizar tus procesos de compra sin roce.",
    note: "Automatiza tu proceso de compras completo en menos de lo que tardas en hacerte un café",
    video: "/landing/videos/baiyer-integraciones-mcp-desktop.mp4",
    poster: "/landing/posters/baiyer-integraciones-mcp-desktop.webp",
  },
];

export const FAQS = [
  {
    q: "¿Qué es Baiyer?",
    a: "Baiyer es una plataforma chilena de procurement que automatiza el ciclo de compra de una empresa: identifica qué necesitas comprar, busca proveedores, pide cotizaciones por correo, compara precios y genera la orden de compra tras la aprobación interna.",
  },
  {
    q: "¿Cómo cotizan los agentes de correo?",
    a: "Baiyer envía y responde cotizaciones desde el correo tuyo y de tu equipo, con reply-to a ti, y lee las respuestas para llenar precios y plazos automáticamente en el comparador.",
  },
  {
    q: "¿Se adapta a mi proceso de compra?",
    a: "Sí. El flujo se configura al proceso de cada empresa: categorías, listas multi-ítem, aprobaciones y proveedores propios. Tú no cambias tu forma de trabajar.",
  },
  {
    q: "¿De dónde salen los precios?",
    a: "De tiendas chilenas, MercadoLibre y Google Shopping, reunidos y filtrados por relevancia para descartar resultados que no corresponden a lo que buscas.",
  },
  {
    q: "¿Puedo conectarlo con mis sistemas?",
    a: "Sí, vía API pública para tu ERP y tus flujos, y un servidor MCP para que tus agentes de IA consulten y operen tus compras, además de correo (Gmail / Outlook).",
  },
  {
    q: "¿Mis datos están seguros?",
    a: "Tus cuentas y datos se mantienen bajo tu control. Los correos salen con reply-to a tu equipo y los agentes operan solo con los permisos que tú defines.",
  },
];

export const INTEGRACIONES = [
  { nombre: "Claude", src: "/landing/logos/claude.png", bg: "#d97757", padding: 9 },
  { nombre: "OpenAI", src: "/landing/logos/openai.png", bg: "#fff", padding: 6 },
  { nombre: "Gmail", src: "/landing/logos/gmail.png", bg: "#fff", padding: 3 },
  { nombre: "Outlook", src: "/landing/logos/outlook.png", bg: "#fff", padding: 9 },
  { nombre: "Slack", src: "/landing/logos/slack.png", bg: "#fff", padding: 9 },
  { nombre: "Teams", src: "/landing/logos/teams.png", bg: "#fff", padding: 9 },
  { nombre: "Discord", src: "/landing/logos/discord.png", bg: "#5865f2", padding: 9 },
];
