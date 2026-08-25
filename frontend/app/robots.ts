import type { MetadataRoute } from "next";
import { SITIO } from "@/components/landing/datos";

/**
 * `robots.txt` generado por Next.
 *
 * Se indexa sólo lo público. Todo lo que hay detrás de sesión (dashboard,
 * listas, cotizaciones, configuración) se excluye explícitamente: no debería
 * ser alcanzable sin login, pero un `Disallow` evita que una URL filtrada por
 * un enlace o un referer termine en el índice.
 *
 * Los magic links (`/aprobar`, `/oc`, `/rating`) también quedan fuera: llevan
 * un token en la URL y no tienen por qué acabar en un buscador.
 */
export default function robots(): MetadataRoute.Robots {
  return {
    rules: [
      {
        userAgent: "*",
        allow: "/",
        disallow: [
          "/api/", "/auth/", "/dashboard", "/listas", "/cotizar", "/proyectos",
          "/proveedores", "/oc", "/facturas", "/settings", "/conversaciones",
          "/estadisticas", "/calendario", "/reportes", "/recurrencias",
          "/aprobar", "/rating", "/mcp/autorizar", "/chat", "/developers",
        ],
      },
    ],
    sitemap: `${SITIO}/sitemap.xml`,
    host: SITIO,
  };
}
