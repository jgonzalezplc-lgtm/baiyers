import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Claria · Cotizador Inteligente",
  description: "Automatiza tus cotizaciones de repuestos y servicios con IA. Busqueda global, email automatico, Orden de Compra instantanea.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="es">
      <body>
        {children}
      </body>
    </html>
  );
}
