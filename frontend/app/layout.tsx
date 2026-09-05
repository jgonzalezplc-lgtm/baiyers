import type { Metadata } from "next";
import { Inter, IBM_Plex_Mono, JetBrains_Mono } from "next/font/google";
import "./globals.css";

const inter = Inter({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  variable: "--font-inter",
  display: "swap",
});

const plexMono = IBM_Plex_Mono({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  variable: "--font-plex-mono",
  display: "swap",
});

// UI mono de la landing pública: etiquetas, precios, badges y footer. La app
// por dentro sigue con IBM Plex Mono; son dos monos distintos a propósito.
const jetbrains = JetBrains_Mono({
  subsets: ["latin"],
  weight: ["400", "500", "700"],
  variable: "--font-jetbrains",
  display: "swap",
});

export const metadata: Metadata = {
  title: "Baiyer · Cotizador inteligente",
  description: "Automatiza tus cotizaciones de repuestos y servicios con IA. Búsqueda global, correo automático, orden de compra instantánea.",
};

const APP_ENVIRONMENT = process.env.NEXT_PUBLIC_ENVIRONMENT ?? "production";

// Aplica el tema guardado antes del primer paint (evita flash de tema claro)
const THEME_INIT = `
(function(){try{var t=localStorage.getItem('baiyer-theme');
if(!t){t=window.matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light';}
document.documentElement.setAttribute('data-theme',t);}catch(e){}})();
`;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="es" className={`${inter.variable} ${plexMono.variable} ${jetbrains.variable}`} suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_INIT }} />
      </head>
      <body>
        {APP_ENVIRONMENT !== "production" && (
          <div className="environment-banner" role="status">
            ENTORNO DE TESTING · Los datos y acciones no corresponden a producción
          </div>
        )}
        {children}
      </body>
    </html>
  );
}
