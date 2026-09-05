import type { Metadata } from "next";
import { redirect } from "next/navigation";
import LandingContent from "@/components/landing/LandingContent";
import { ETAPAS, FAQS, SITIO } from "@/components/landing/datos";

/**
 * SEO / AEO / GEO de la portada.
 *
 * - **SEO**: title y description con las palabras que se buscan en Chile
 *   ("cotizaciones", "proveedores", "órdenes de compra"), canonical, Open Graph
 *   y Twitter card.
 * - **AEO** (answer engines): el bloque `FAQPage` de abajo es lo que se cita en
 *   los "featured snippets" y en los resúmenes de asistentes. Las respuestas
 *   salen del MISMO módulo que renderiza la página: structured data que no
 *   coincide con el contenido visible es motivo de penalización.
 * - **GEO** (generative engines): describe la entidad "Baiyer" de forma
 *   explícita y verificable — qué es, dónde opera, con qué se integra, en qué
 *   idioma — para que un modelo pueda responder "¿qué es Baiyer?" sin inferir.
 */
export const metadata: Metadata = {
  metadataBase: new URL(SITIO),
  title: "Baiyer · El empleado digital para tus compras",
  description:
    "Baiyer es un empleado digital de procurement para empresas en Chile. Cotiza con proveedores, compara precios, gestiona autorizaciones, homologa proveedores, emite órdenes de compra y concilia facturas.",
  keywords: [
    "procurement Chile", "cotizaciones automáticas", "software de compras",
    "comparar precios proveedores", "orden de compra automática",
    "agentes de IA para compras", "abastecimiento empresas Chile",
  ],
  authors: [{ name: "Baiyer" }],
  creator: "Baiyer",
  publisher: "Baiyer",
  alternates: { canonical: "/" },
  robots: {
    index: true,
    follow: true,
    googleBot: { index: true, follow: true, "max-image-preview": "large", "max-snippet": -1 },
  },
  openGraph: {
    type: "website",
    locale: "es_CL",
    url: SITIO,
    siteName: "Baiyer",
    title: "Baiyer · El empleado digital de compras",
    description:
      "Baiyer cotiza, compara, sigue proveedores y compra sólo cuando tu equipo lo aprueba.",
    images: [{ url: "/landing/og.png", width: 1200, height: 630, alt: "Baiyer — procurement automatizado con IA" }],
  },
  twitter: {
    card: "summary_large_image",
    title: "Baiyer · Empleado digital de compras",
    description: "Baiyer cotiza, compara y prepara compras bajo las reglas de tu empresa.",
    images: ["/landing/og.png"],
  },
  category: "business software",
};

/** Un solo `<script>` con un @graph: menos ruido que varios bloques sueltos. */
function jsonLd() {
  return {
    "@context": "https://schema.org",
    "@graph": [
      {
        "@type": "Organization",
        "@id": `${SITIO}/#organizacion`,
        name: "Baiyer",
        url: SITIO,
        description:
          "Plataforma chilena de procurement con un empleado digital que automatiza cotización, comparación, aprobaciones y compras.",
        areaServed: { "@type": "Country", name: "Chile" },
        knowsLanguage: ["es-CL"],
        contactPoint: {
          "@type": "ContactPoint",
          contactType: "sales",
          email: "j.gonzalez.plc@gmail.com",
          areaServed: "CL",
          availableLanguage: ["Spanish"],
        },
      },
      {
        "@type": "WebSite",
        "@id": `${SITIO}/#sitio`,
        url: SITIO,
        name: "Baiyer",
        inLanguage: "es-CL",
        publisher: { "@id": `${SITIO}/#organizacion` },
      },
      {
        "@type": "SoftwareApplication",
        "@id": `${SITIO}/#producto`,
        name: "Baiyer",
        applicationCategory: "BusinessApplication",
        applicationSubCategory: "Procurement",
        operatingSystem: "Web",
        url: SITIO,
        inLanguage: "es-CL",
        publisher: { "@id": `${SITIO}/#organizacion` },
        description:
          "Software de compras con un empleado digital que identifica pedidos, busca proveedores, solicita cotizaciones por correo, compara precios y prepara compras tras la aprobación interna.",
        featureList: ETAPAS.map(e => e.label),
        // Sin `offers`: los precios públicos se retiraron de la landing y
        // declarar un precio que no se muestra es structured data engañoso.
      },
      {
        // El grafo del ciclo de compra es la lista real de capacidades, y en
        // la página aparece como tarjetas animadas. Declararla como ItemList
        // ordenada le da a un buscador el proceso completo, en orden, sin
        // depender de que interprete el grafo visual.
        "@type": "ItemList",
        "@id": `${SITIO}/#capacidades`,
        name: "Ciclo de compra que ejecuta Baiyer",
        inLanguage: "es-CL",
        itemListOrder: "https://schema.org/ItemListOrderAscending",
        itemListElement: ETAPAS.map((e, i) => ({
          "@type": "ListItem",
          position: i + 1,
          name: e.label,
          description: e.role,
        })),
      },
      {
        "@type": "FAQPage",
        "@id": `${SITIO}/#faq`,
        inLanguage: "es-CL",
        mainEntity: FAQS.map(f => ({
          "@type": "Question",
          name: f.q,
          acceptedAnswer: { "@type": "Answer", text: f.a },
        })),
      },
    ],
  };
}

export default async function LandingPage({
  searchParams,
}: {
  searchParams: Promise<{ code?: string }>;
}) {
  // Salvavidas OAuth: si Supabase redirige el código de login a la raíz
  // (por fallback de Site URL), lo reenviamos al handler que crea la sesión.
  const { code } = await searchParams;
  if (code) redirect(`/auth/callback?code=${code}&next=/dashboard`);

  return (
    <>
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd()) }}
      />
      <LandingContent />
    </>
  );
}
