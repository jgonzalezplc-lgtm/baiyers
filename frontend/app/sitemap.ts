import type { MetadataRoute } from "next";
import { SITIO } from "@/components/landing/datos";

/**
 * Sólo las URLs públicas y con contenido propio. Deliberadamente corto: un
 * sitemap que lista páginas detrás de login o vacías desperdicia presupuesto de
 * rastreo y ensucia las señales.
 *
 * `/login` y `/register` van con prioridad baja — importan para que un usuario
 * que busca "baiyer iniciar sesión" llegue directo, no para posicionar.
 */
export default function sitemap(): MetadataRoute.Sitemap {
  const ahora = new Date();
  return [
    { url: SITIO, lastModified: ahora, changeFrequency: "weekly", priority: 1 },
    { url: `${SITIO}/docs`, lastModified: ahora, changeFrequency: "monthly", priority: 0.6 },
    { url: `${SITIO}/docs/mcp`, lastModified: ahora, changeFrequency: "monthly", priority: 0.6 },
    { url: `${SITIO}/login`, lastModified: ahora, changeFrequency: "yearly", priority: 0.3 },
    { url: `${SITIO}/register`, lastModified: ahora, changeFrequency: "yearly", priority: 0.3 },
  ];
}
