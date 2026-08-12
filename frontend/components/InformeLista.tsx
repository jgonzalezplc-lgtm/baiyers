"use client";
/**
 * Informe PDF de una lista de cotización completa:
 * - Resumen con total y ruta de compra final (definitivos)
 * - Una sección por ítem con todos sus proveedores comparados
 *   (descripción scrapeada, precio y URL de origen)
 */
import { useEffect, useRef, useState } from "react";
import { pdf, Document, Page, Text, View, Link as PdfLink, StyleSheet } from "@react-pdf/renderer";
import { authFetch } from "@/lib/authFetch";
import type { DetalleLista } from "@/app/listas/[id]/page";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const FUENTE_LABEL: Record<string, string> = {
  mercadolibre: "MercadoLibre", google: "Google Shopping",
  mouser: "Mouser", digikey: "DigiKey", tme: "TME", manual: "Manual",
  sodimac: "Sodimac", easy: "Easy", lasierra: "La Sierra", construmart: "Construmart",
  vitel: "Vitel", dartel: "Dartel", ferrelectrica: "Ferrelectrica", gobantes: "Gobantes", rhona: "Rhona",
  clcsa: "CLC Maderas", wmaderas: "W Maderas", ferramenta: "Ferramenta", maderas_dir: "Aserraderos CL",
};

const s = StyleSheet.create({
  page: { backgroundColor: "#ffffff", padding: 44, fontFamily: "Helvetica", fontSize: 9, color: "#111111" },
  rule: { height: 3, width: 48, backgroundColor: "#136b76", marginBottom: 14 },
  kicker: { fontSize: 8, color: "#666666", letterSpacing: 1.5, marginBottom: 5 },
  titulo: { fontSize: 20, fontFamily: "Helvetica-Bold", marginBottom: 4 },
  meta: { fontSize: 8, color: "#666666", marginBottom: 20 },
  seccion: { fontSize: 11, fontFamily: "Helvetica-Bold", marginTop: 14, marginBottom: 8, paddingBottom: 3, borderBottom: "2px solid #111111" },
  // ruta de compra
  rutaFila: { flexDirection: "row", borderBottom: "1px solid #eeeeee", paddingVertical: 5, alignItems: "center" },
  rutaItem: { flex: 1.2, fontFamily: "Helvetica-Bold", fontSize: 9 },
  rutaProv: { flex: 1.4 },
  rutaPrecio: { width: 80, textAlign: "right", fontFamily: "Helvetica-Bold" },
  totalFila: { flexDirection: "row", justifyContent: "space-between", backgroundColor: "#111111", color: "#ffffff", padding: "7 10", marginTop: 6 },
  // comparados por ítem
  card: { border: "1px solid #cccccc", marginBottom: 8, padding: 10 },
  cardTop: { flexDirection: "row", justifyContent: "space-between", marginBottom: 4 },
  provNombre: { fontSize: 10, fontFamily: "Helvetica-Bold" },
  provFuente: { fontSize: 7.5, color: "#136b76", marginTop: 1 },
  precio: { fontSize: 11, fontFamily: "Helvetica-Bold", textAlign: "right" },
  descripcion: { fontSize: 8, color: "#333333", lineHeight: 1.45, marginBottom: 5 },
  datos: { fontSize: 7.5, color: "#666666", marginBottom: 4 },
  url: { fontSize: 7, color: "#136b76", textDecoration: "none" },
  defBadge: { fontSize: 7, color: "#1a6e45", fontFamily: "Helvetica-Bold", marginBottom: 3 },
  footer: {
    position: "absolute", bottom: 26, left: 44, right: 44,
    borderTop: "1px solid #cccccc", paddingTop: 7,
    fontSize: 7, color: "#999999", textAlign: "center",
  },
});

const fmtCLP = (n: number) => `$${Math.round(n).toLocaleString("es-CL")}`;
const fmtPrecio = (n: number, m: string) =>
  m === "CLP" ? fmtCLP(n) : `${n.toLocaleString("en-US", { minimumFractionDigits: 2 })} ${m}`;

function ListaPDF({ datos, modo = "normal" }: { datos: DetalleLista; modo?: "normal" | "mejor_precio" }) {
  const fecha = new Date().toLocaleDateString("es-CL", { day: "numeric", month: "long", year: "numeric" });
  const definitivos = datos.items.filter(it => it.definitivo);
  const totalCLP = definitivos.reduce((a, it) => a + (it.definitivo?.precio_clp ?? 0) * (it.cantidad || 1), 0);
  const esMejorPrecio = modo === "mejor_precio";

  return (
    <Document title={`Informe lista, ${datos.nombre}`}>
      {/* Página 1: resumen + ruta de compra */}
      <Page size="A4" style={s.page}>
        <View style={s.rule} />
        <Text style={s.kicker}>
          {esMejorPrecio ? "INFORME DE LISTA, ESCENARIO MEJOR PRECIO" : "Informe de lista de cotización"}
        </Text>
        <Text style={s.titulo}>{datos.nombre}</Text>
        <Text style={s.meta}>
          Generado el {fecha}  ·  {datos.items.length} ítems  ·  {esMejorPrecio
            ? "opción más económica seleccionada automáticamente por ítem"
            : `${definitivos.length} con proveedor definitivo`}
        </Text>

        {definitivos.length > 0 && (
          <>
            <Text style={s.seccion}>{esMejorPrecio ? "Ruta de compra, mejor precio" : "Ruta de compra final"}</Text>
            {definitivos.map((it, i) => {
              const d = it.definitivo!;
              const cant = it.cantidad || 1;
              return (
                <View key={i} style={s.rutaFila}>
                  <Text style={s.rutaItem}>{it.nombre}  (x{cant})</Text>
                  <View style={s.rutaProv}>
                    <Text>{d.proveedor ?? "—"}  ({FUENTE_LABEL[d.fuente ?? ""] ?? d.fuente ?? "—"})</Text>
                    {d.url ? <PdfLink src={d.url} style={s.url}>{d.url.length > 70 ? d.url.slice(0, 70) + "…" : d.url}</PdfLink> : null}
                  </View>
                  <View>
                    <Text style={s.rutaPrecio}>
                      {d.precio_clp != null ? fmtCLP(d.precio_clp * cant) : d.precio != null ? fmtPrecio(d.precio * cant, d.moneda) : "—"}
                    </Text>
                    {cant > 1 && d.precio_clp != null && (
                      <Text style={{ fontSize: 6.5, color: "#666666", textAlign: "right" }}>
                        {cant} x {fmtCLP(d.precio_clp)}
                      </Text>
                    )}
                  </View>
                </View>
              );
            })}
            <View style={s.totalFila}>
              <Text style={{ fontFamily: "Helvetica-Bold" }}>TOTAL SELECCIONADOS (CLP aprox.)</Text>
              <Text style={{ fontFamily: "Helvetica-Bold" }}>{fmtCLP(totalCLP)}</Text>
            </View>
            {definitivos.length < datos.items.length && (
              <Text style={{ fontSize: 7.5, color: "#666666", marginTop: 4 }}>
                * {datos.items.length - definitivos.length} ítem(s) aún sin proveedor definitivo, no incluidos en el total.
              </Text>
            )}
          </>
        )}

        <Text style={s.footer} render={({ pageNumber, totalPages }) => `cotizador.ai · Informe de lista · Página ${pageNumber} de ${totalPages}`} fixed />
      </Page>

      {/* Una página (o más) por los comparados de cada ítem */}
      <Page size="A4" style={s.page}>
        <View style={s.rule} />
        <Text style={s.kicker}>
          {esMejorPrecio ? "DETALLE POR ÍTEM, OPCIÓN MÁS ECONÓMICA" : "DETALLE POR ÍTEM, PROVEEDORES COMPARADOS"}
        </Text>

        {datos.items.map((it, idx) => (
          <View key={idx}>
            <Text style={s.seccion}>
              {idx + 1}. {it.nombre}  ·  cantidad: {it.cantidad || 1}  ({it.comparados.length} proveedor{it.comparados.length !== 1 ? "es" : ""})
            </Text>
            {it.comparados.length === 0 && (
              <Text style={{ fontSize: 8, color: "#666666", marginBottom: 8 }}>Sin proveedores comparados.</Text>
            )}
            {it.comparados.map((c, ci) => {
              const precio = c.precio_cotizado ?? c.precio;
              const moneda = c.precio_cotizado != null ? "CLP" : c.moneda;
              const esDef = it.definitivo?.resultado_id === c.resultado_id;
              return (
                <View key={ci} style={s.card} wrap={false}>
                  {esDef && <Text style={s.defBadge}>✓ SELECCIÓN DEFINITIVA</Text>}
                  <View style={s.cardTop}>
                    <View style={{ flex: 1, paddingRight: 10 }}>
                      <Text style={s.provNombre}>{c.proveedor ?? "Proveedor"}</Text>
                      <Text style={s.provFuente}>{FUENTE_LABEL[c.fuente ?? ""] ?? c.fuente ?? "—"}</Text>
                    </View>
                    <Text style={s.precio}>{precio != null ? fmtPrecio(precio, moneda) : "Sin precio"}</Text>
                  </View>
                  {c.descripcion ? <Text style={s.descripcion}>{c.descripcion}</Text> : null}
                  <Text style={s.datos}>
                    {[
                      c.ubicacion ? `Ubicación: ${c.ubicacion}` : null,
                      c.plazo_entrega ? `Entrega: ${c.plazo_entrega}` : null,
                      c.contacto ? `Contacto: ${c.contacto}` : "Contacto: vía web",
                    ].filter(Boolean).join("   ·   ")}
                  </Text>
                  {c.url ? <PdfLink src={c.url} style={s.url}>{c.url.length > 105 ? c.url.slice(0, 105) + "…" : c.url}</PdfLink> : null}
                </View>
              );
            })}
          </View>
        ))}

        <Text style={s.footer} render={({ pageNumber, totalPages }) => `cotizador.ai · Informe de lista · Página ${pageNumber} de ${totalPages}`} fixed />
      </Page>
    </Document>
  );
}

// Transforma la lista al escenario "mejor precio": por cada ítem queda solo la
// opción más barata (en CLP) como selección y como único comparado del informe.
function escenarioMejorPrecio(datos: DetalleLista, tasas: Record<string, number>): DetalleLista {
  const aCLP = (v: number, m: string) =>
    m === "CLP" ? v : (v / (tasas[m] ?? 1)) * (tasas.CLP ?? 950);

  const items = datos.items.map(it => {
    const conPrecio = it.comparados.filter(c => (c.precio_cotizado ?? c.precio) != null);
    if (!conPrecio.length) return { ...it, comparados: [], definitivo: null };

    const clpDe = (c: (typeof conPrecio)[number]) => {
      const p = c.precio_cotizado ?? c.precio!;
      const m = c.precio_cotizado != null ? "CLP" : c.moneda;
      return aCLP(p, m);
    };
    const mejor = conPrecio.reduce((a, b) => (clpDe(a) <= clpDe(b) ? a : b));
    const precio = mejor.precio_cotizado ?? mejor.precio!;
    const moneda = mejor.precio_cotizado != null ? "CLP" : mejor.moneda;

    return {
      ...it,
      comparados: [mejor],
      definitivo: {
        resultado_id: mejor.resultado_id,
        proveedor: mejor.proveedor,
        precio, moneda,
        url: mejor.url,
        fuente: mejor.fuente,
        precio_clp: aCLP(precio, moneda),
      },
    };
  });
  return { ...datos, items };
}

export default function InformeLista({
  listaId,
  userId,
  nombreLista,
  tienePrecios,
}: {
  listaId: string;
  userId: string;
  nombreLista: string;
  tienePrecios: boolean;
}) {
  const [generando, setGenerando] = useState<"normal" | "mejor_precio" | null>(null);
  const [abierto, setAbierto] = useState(false);
  const [error, setError] = useState("");
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const cerrarAlClickFuera = (event: MouseEvent) => {
      if (!menuRef.current?.contains(event.target as Node)) setAbierto(false);
    };
    document.addEventListener("mousedown", cerrarAlClickFuera);
    return () => document.removeEventListener("mousedown", cerrarAlClickFuera);
  }, []);

  const descargar = async (modo: "normal" | "mejor_precio") => {
    if (!userId || !tienePrecios) return;
    setAbierto(false);
    setGenerando(modo);
    setError("");
    try {
      const [res, tasas] = await Promise.all([
        authFetch(`${API_URL}/api/listas/${listaId}/informe`),
        fetch("https://open.er-api.com/v6/latest/USD")
          .then(r => r.json()).then(d => (d.rates ?? {}) as Record<string, number>)
          .catch(() => ({ CLP: 950, EUR: 0.92, CNY: 7.25, GBP: 0.79 } as Record<string, number>)),
      ]);
      if (!res.ok) throw new Error("No se pudieron obtener los datos del informe");
      let datos: DetalleLista = await res.json();
      if (modo === "mejor_precio") datos = escenarioMejorPrecio(datos, tasas);

      const blob = await pdf(<ListaPDF datos={datos} modo={modo} />).toBlob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      const prefijo = modo === "mejor_precio" ? "Informe_mejor_precio" : "Informe_lista";
      a.download = `${prefijo}_${(nombreLista || "lista").replace(/\s+/g, "_")}.pdf`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Error generando el informe");
      setTimeout(() => setError(""), 4000);
    } finally {
      setGenerando(null);
    }
  };

  return (
    <div ref={menuRef} style={{ position: "relative", display: "inline-flex", flexDirection: "column", alignItems: "flex-end", gap: 4 }}>
      <button
        type="button"
        onClick={() => setAbierto(v => !v)}
        disabled={!tienePrecios || generando !== null}
        aria-expanded={abierto}
        aria-haspopup="menu"
        className="btn-swiss-primary"
        style={{
          fontSize: 10, whiteSpace: "nowrap",
          cursor: !tienePrecios ? "not-allowed" : generando ? "wait" : "pointer",
          opacity: tienePrecios ? 1 : .45,
        }}
        title={tienePrecios ? "Descargar informe" : "Disponible cuando el cuadro comparativo tenga precios"}
      >
        {generando ? "GENERANDO..." : "INFORMES"}
        <span aria-hidden="true" style={{
          display: "inline-block", marginLeft: 8,
          transform: abierto ? "rotate(180deg)" : "rotate(0deg)",
          transition: "transform 180ms ease",
        }}>⌄</span>
      </button>

      <div style={{
        position: "absolute", zIndex: 40, top: "calc(100% + 6px)", right: 0,
        display: "grid", gridTemplateRows: abierto ? "1fr" : "0fr",
        opacity: abierto ? 1 : 0,
        transform: abierto ? "translateY(0)" : "translateY(-6px)",
        transition: "grid-template-rows 220ms ease, opacity 160ms ease, transform 220ms ease",
        pointerEvents: abierto ? "auto" : "none",
      }}>
        <div style={{ overflow: "hidden" }}>
          <div role="menu" style={{
            minWidth: 220, padding: 6,
            background: "var(--surface)", border: "1px solid var(--n-200)",
            borderRadius: "var(--r-md)", boxShadow: "var(--shadow-pop)",
          }}>
            {([
              ["normal", "Informe completo"],
              ["mejor_precio", "Informe mejor precio"],
            ] as const).map(([modo, label]) => (
              <button
                key={modo}
                type="button"
                role="menuitem"
                onClick={() => void descargar(modo)}
                style={{
                  display: "block", width: "100%", padding: "10px 12px",
                  border: 0, borderRadius: "var(--r-sm)", background: "transparent",
                  color: "var(--n-800)", textAlign: "left", whiteSpace: "nowrap",
                  font: "inherit", fontSize: 13, fontWeight: 500, cursor: "pointer",
                }}
                onMouseEnter={e => { e.currentTarget.style.background = "var(--n-100)"; }}
                onMouseLeave={e => { e.currentTarget.style.background = "transparent"; }}
              >
                {label} <span aria-hidden="true" style={{ float: "right", color: "var(--n-500)" }}>↓</span>
              </button>
            ))}
          </div>
        </div>
      </div>
      {error && <span className="label" style={{ color: "var(--text-error)" }}>{error}</span>}
    </div>
  );
}
