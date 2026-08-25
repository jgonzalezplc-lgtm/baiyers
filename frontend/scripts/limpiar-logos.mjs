/**
 * Quita el fondo blanco opaco de los wordmarks del hero de la landing.
 *
 * Los PNG del handoff son RGBA pero con el fondo pintado de blanco sólido
 * (verificado leyendo el píxel: [255,255,255,255]). El diseño original lo
 * disimulaba con `mix-blend-mode: multiply` sobre papel claro; acá se necesita
 * transparencia real.
 *
 * No basta con "blanco → alfa 0": los bordes de las letras están
 * antialiaseados contra ese blanco, así que un corte duro deja un halo
 * dentado. Los tonos intermedios reciben un alfa proporcional.
 *
 * Se corre a mano cuando cambian los assets:
 *   node scripts/limpiar-logos.mjs
 */
import sharp from "sharp";

const LOGOS = ["logo-claude-wordmark", "logo-chatgpt-wordmark"];
const OPACO = 200;   // por debajo de esto el píxel es tinta: se conserva entero
const FONDO = 235;   // por encima de esto es fondo: transparente

for (const nombre of LOGOS) {
  const ruta = `public/landing/${nombre}.png`;
  const { data, info } = await sharp(ruta).ensureAlpha().raw()
    .toBuffer({ resolveWithObject: true });
  const { width, height, channels } = info;

  let transparentes = 0;
  let suavizados = 0;
  for (let i = 0; i < data.length; i += channels) {
    const min = Math.min(data[i], data[i + 1], data[i + 2]);
    if (min >= FONDO) {
      data[i + 3] = 0;
      transparentes++;
    } else if (min > OPACO) {
      data[i + 3] = Math.round((255 * (FONDO - min)) / (FONDO - OPACO));
      suavizados++;
    }
  }

  await sharp(data, { raw: { width, height, channels } }).png().toFile(ruta);
  console.log(`${nombre}: ${width}x${height} · ${transparentes} px transparentes, ${suavizados} suavizados`);
}
