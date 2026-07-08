"use client";
/**
 * Informe de Cotización en PDF.
 * Botón que arma el informe con los proveedores del comparador: por cada uno,
 * descripción (de metadata o scrapeada de su página), precio y URL de origen.
 */
import { useState } from "react";
import { pdf, Document, Page, Text, View, Link as PdfLink, StyleSheet } from "@react-pdf/renderer";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface ProveedorInforme {
  proveedor: string | null;
  fuente: string | null;
  precio: number | null;
  moneda: string;
  precio_cotizado: number | null;
  plazo_entrega: string | null;
  ubicacion: string | null;
  contacto: string | null;
  url: string;
  descripcion: string | null;
}

interface DatosInforme {
  cotizacion: {
    nombre: string;
    marca: string | null;
    numero_parte: string | null;
    categoria: string | null;
    created_at: string | null;
  };
  proveedores: ProveedorInforme[];
}

const FUENTE_LABEL: Record<string, string> = {
  mercadolibre: "MercadoLibre", google: "Google Shopping",
  mouser: "Mouser", digikey: "DigiKey", tme: "TME", manual: "Manual",
  sodimac: "Sodimac", easy: "Easy", lasierra: "La Sierra", construmart: "Construmart",
  vitel: "Vitel", dartel: "Dartel", ferrelectrica: "Ferrelectrica", gobantes: "Gobantes", rhona: "Rhona",
  clcsa: "CLC Maderas", wmaderas: "W Maderas", ferramenta: "Ferramenta", maderas_dir: "Aserraderos CL",
};

// Estilo Swiss: blanco/negro, acento #c0392b, sin decoración
const s = StyleSheet.create({
  page: { backgroundColor: "#ffffff", padding: 44, fontFamily: "Helvetica", fontSize: 9, color: "#111111" },
  rule: { height: 3, width: 48, backgroundColor: "#c0392b", marginBottom: 14 },
  kicker: { fontSize: 8, color: "#666666", letterSpacing: 1.5, marginBottom: 5 },
  titulo: { fontSize: 20, fontFamily: "Helvetica-Bold", marginBottom: 4 },
  meta: { fontSize: 8, color: "#666666", marginBottom: 24 },
  card: { border: "1px solid #cccccc", marginBottom: 12, padding: 12 },
  cardTop: { flexDirection: "row", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 6 },
  provNombre: { fontSize: 11, fontFamily: "Helvetica-Bold" },
  provFuente: { fontSize: 8, color: "#c0392b", marginTop: 2 },
  precio: { fontSize: 13, fontFamily: "Helvetica-Bold", textAlign: "right" },
  precioSub: { fontSize: 7, color: "#666666", textAlign: "right", marginTop: 1 },
  descripcion: { fontSize: 8.5, color: "#333333", lineHeight: 1.5, marginBottom: 8 },
  filaDatos: { flexDirection: "row", borderTop: "1px solid #eeeeee", paddingTop: 6, marginBottom: 6 },
  dato: { flex: 1 },
  datoLabel: { fontSize: 6.5, color: "#999999", letterSpacing: 0.8, marginBottom: 2 },
  datoValor: { fontSize: 8.5 },
  url: { fontSize: 7, color: "#c0392b", textDecoration: "none" },
  footer: {
    position: "absolute", bottom: 26, left: 44, right: 44,
    borderTop: "1px solid #cccccc", paddingTop: 7,
    fontSize: 7, color: "#999999", textAlign: "center",
  },
});

function fmtPrecio(n: number, moneda: string) {
  return moneda === "CLP"
    ? `$${Math.round(n).toLocaleString("es-CL")}`
    : `${n.toLocaleString("en-US", { minimumFractionDigits: 2 })} ${moneda}`;
}

function InformePDF({ datos }: { datos: DatosInforme }) {
  const c = datos.cotizacion;
  const fecha = new Date().toLocaleDateString("es-CL", { day: "numeric", month: "long", year: "numeric" });

  return (
    <Document title={`Informe de cotización — ${c.nombre}`}>
      <Page size="A4" style={s.page}>
        <View style={s.rule} />
        <Text style={s.kicker}>INFORME DE COTIZACIÓN</Text>
        <Text style={s.titulo}>{c.nombre}</Text>
        <Text style={s.meta}>
          {[
            c.categoria ? c.categoria.toUpperCase() : null,
            c.marca,
            c.numero_parte ? `N/P: ${c.numero_parte}` : null,
            `Generado el ${fecha}`,
            `${datos.proveedores.length} proveedor${datos.proveedores.length !== 1 ? "es" : ""}`,
          ].filter(Boolean).join("  ·  ")}
        </Text>

        {datos.proveedores.map((p, i) => {
          const precioFinal = p.precio_cotizado ?? p.precio;
          const monedaFinal = p.precio_cotizado != null ? "CLP" : p.moneda;
          return (
            <View key={i} style={s.card} wrap={false}>
              <View style={s.cardTop}>
                <View style={{ flex: 1, paddingRight: 12 }}>
                  <Text style={s.provNombre}>#{i + 1}  {p.proveedor ?? "Proveedor"}</Text>
                  <Text style={s.provFuente}>
                    {FUENTE_LABEL[p.fuente ?? ""] ?? p.fuente ?? "—"}
                  </Text>
                </View>
                <View>
                  <Text style={s.precio}>
                    {precioFinal != null ? fmtPrecio(precioFinal, monedaFinal) : "Sin precio"}
                  </Text>
                  {p.precio_cotizado != null && p.precio != null && (
                    <Text style={s.precioSub}>búsqueda: {fmtPrecio(p.precio, p.moneda)}</Text>
                  )}
                </View>
              </View>

              {p.descripcion && <Text style={s.descripcion}>{p.descripcion}</Text>}

              <View style={s.filaDatos}>
                <View style={s.dato}>
                  <Text style={s.datoLabel}>UBICACIÓN</Text>
                  <Text style={s.datoValor}>{p.ubicacion ?? "—"}</Text>
                </View>
                <View style={s.dato}>
                  <Text style={s.datoLabel}>ENTREGA</Text>
                  <Text style={s.datoValor}>{p.plazo_entrega ?? "—"}</Text>
                </View>
                <View style={s.dato}>
                  <Text style={s.datoLabel}>CONTACTO</Text>
                  <Text style={s.datoValor}>{p.contacto ?? "vía web"}</Text>
                </View>
              </View>

              {p.url ? (
                <PdfLink src={p.url} style={s.url}>{p.url.length > 110 ? p.url.slice(0, 110) + "…" : p.url}</PdfLink>
              ) : null}
            </View>
          );
        })}

        <Text
          style={s.footer}
          render={({ pageNumber, totalPages }) => `cotizador.ai · Informe de cotización · Página ${pageNumber} de ${totalPages}`}
          fixed
        />
      </Page>
    </Document>
  );
}

export default function InformeCotizacion({ cotizacionId, nombreItem }: { cotizacionId: string; nombreItem: string }) {
  const [generando, setGenerando] = useState(false);
  const [error, setError] = useState("");

  const descargar = async () => {
    setGenerando(true);
    setError("");
    try {
      const res = await fetch(`${API_URL}/api/cotizaciones/${cotizacionId}/informe`);
      if (!res.ok) throw new Error("No se pudieron obtener los datos del informe");
      const datos: DatosInforme = await res.json();
      if (!datos.proveedores.length) throw new Error("No hay proveedores en el comparador");

      const blob = await pdf(<InformePDF datos={datos} />).toBlob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `Informe_cotizacion_${(nombreItem || "item").replace(/\s+/g, "_")}.pdf`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Error generando el informe");
      setTimeout(() => setError(""), 4000);
    } finally {
      setGenerando(false);
    }
  };

  return (
    <div style={{ display: "inline-flex", flexDirection: "column", alignItems: "flex-end", gap: 4 }}>
      <button
        onClick={descargar}
        disabled={generando}
        className="btn-swiss-secondary"
        style={{ fontSize: 10, whiteSpace: "nowrap", cursor: generando ? "wait" : "pointer" }}
      >
        {generando ? "GENERANDO INFORME..." : "INFORME PDF ↓"}
      </button>
      {error && <span className="label" style={{ color: "var(--text-error)" }}>{error}</span>}
    </div>
  );
}
