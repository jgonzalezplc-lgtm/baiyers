/**
 * Genera un `poster` por video de la landing.
 *
 * Sin poster, el navegador muestra un rectángulo vacío hasta que llegan los
 * primeros bytes del mp4 — con el hero de 3 MB eso castiga el LCP en móvil.
 * El poster es lo que se pinta primero y lo que mide Lighthouse.
 *
 * Se extrae el frame con QuickLook (`qlmanage`), que viene en macOS, en vez de
 * agregar ffmpeg como dependencia sólo para esto. Después sharp lo reencoda a
 * WebP: el PNG que devuelve QuickLook pesa ~175 KB y el WebP equivalente ~30 KB.
 *
 * Se corre a mano cuando cambian las grabaciones:
 *   node scripts/generar-posters.mjs
 */
import { execFileSync } from "node:child_process";
import { mkdtempSync, readdirSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import sharp from "sharp";

const DIR_VIDEOS = "public/landing/videos";
const DIR_POSTERS = "public/landing/posters";
const ANCHO = 1280;

const videos = readdirSync(DIR_VIDEOS).filter(f => f.endsWith(".mp4")).sort();
const temporal = mkdtempSync(join(tmpdir(), "posters-"));

try {
  await sharp({ create: { width: 1, height: 1, channels: 3, background: "#fff" } })
    .toFile(join(temporal, ".probe.png"));  // fuerza carga de sharp antes del loop

  for (const video of videos) {
    execFileSync("qlmanage", ["-t", "-s", String(ANCHO), "-o", temporal, join(DIR_VIDEOS, video)],
      { stdio: "ignore" });

    const generado = readdirSync(temporal).find(f => f.startsWith(video));
    if (!generado) {
      console.error(`✗ ${video}: QuickLook no devolvió miniatura`);
      continue;
    }

    const destino = join(DIR_POSTERS, video.replace(/\.mp4$/, ".webp"));
    const { size } = await sharp(join(temporal, generado))
      .resize({ width: ANCHO, withoutEnlargement: true })
      .webp({ quality: 80 })
      .toFile(destino);

    console.log(`${video} → ${destino} · ${Math.round(size / 1024)} KB`);
  }
} finally {
  rmSync(temporal, { recursive: true, force: true });
}
