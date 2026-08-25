/**
 * Genera la imagen Open Graph de la portada (1200×630).
 *
 * Es estática a propósito: `next/og` la renderizaría en cada request y esta
 * imagen no cambia. Se regenera a mano si cambia el mensaje:
 *   node scripts/generar-og.mjs
 */
import sharp from "sharp";

const ANCHO = 1200;
const ALTO = 630;

const svg = `
<svg xmlns="http://www.w3.org/2000/svg" width="${ANCHO}" height="${ALTO}">
  <rect width="${ANCHO}" height="${ALTO}" fill="#faf9f6"/>
  <rect x="0" y="0" width="${ANCHO}" height="10" fill="#136b76"/>
  <g font-family="Georgia, 'Source Serif 4', serif" fill="#211d18">
    <text x="80" y="150" font-size="40" font-weight="600" fill="#136b76">Baiyer</text>
    <text x="80" y="290" font-size="74" font-weight="600" letter-spacing="-2">Tu proceso de compra</text>
    <text x="80" y="374" font-size="74" font-weight="600" letter-spacing="-2">completo, automatizado</text>
    <text x="80" y="466" font-size="30" fill="#635d52">Agentes de correo que cotizan por ti.</text>
    <text x="80" y="510" font-size="30" fill="#635d52">De semanas a minutos, al mejor precio.</text>
    <text x="80" y="580" font-size="24" fill="#8a8478">Procurement con IA para empresas en Chile · baiyer.cl</text>
  </g>
</svg>`;

await sharp(Buffer.from(svg)).png().toFile("public/landing/og.png");
console.log(`og.png generada · ${ANCHO}x${ALTO}`);
