import type { Metadata } from "next";
import { redirect } from "next/navigation";
import LandingContent from "@/components/landing/LandingContent";
import { FAQS, FEATURES, SITIO } from "@/components/landing/datos";

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
  title: "Baiyer · Cotiza y compra con agentes de IA | Procurement para empresas en Chile",
  description:
    "Baiyer automatiza tu proceso de compra: agentes de correo piden cotizaciones a tus proveedores, comparan precios de tiendas chilenas, MercadoLibre y Google Shopping, y generan la orden de compra tras la aprobación. Se conecta a Gmail, Outlook, Claude y ChatGPT.",
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
    title: "Baiyer · Tu proceso de compra completo desde Claude o ChatGPT",
    description:
      "Agentes de correo que cotizan por ti. De semanas a minutos, al mejor precio. Procurement automatizado para empresas en Chile.",
    images: [{ url: "/landing/og.png", width: 1200, height: 630, alt: "Baiyer — procurement automatizado con IA" }],
  },
  twitter: {
    card: "summary_large_image",
    title: "Baiyer · Procurement automatizado con IA",
    description: "Agentes de correo que cotizan por ti. De semanas a minutos, al mejor precio.",
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
          "Plataforma chilena de procurement que automatiza cotización, comparación de precios y órdenes de compra con agentes de IA.",
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
          "Software de compras que identifica qué necesitas comprar, busca proveedores, solicita cotizaciones por correo, compara precios y genera la orden de compra tras la aprobación interna.",
        featureList: FEATURES.map(f => f.title),
        // Sin `offers`: los precios públicos se retiraron de la landing y
        // declarar un precio que no se muestra es structured data engañoso.
      },
      {
        // La sección de producto muestra una tarjeta por vez, así que 5 de las
        // 6 descripciones nunca están en el DOM y ningún rastreador las ve.
        // Esta lista se las entrega completas, sin texto oculto en la página.
        "@type": "ItemList",
        "@id": `${SITIO}/#capacidades`,
        name: "Qué hace Baiyer",
        inLanguage: "es-CL",
        itemListElement: FEATURES.map((f, i) => ({
          "@type": "ListItem",
          position: i + 1,
          name: f.title,
          description: f.desc,
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
