"use client";
import { useState } from "react";
import { PDFDownloadLink, Document, Page, Text, View, StyleSheet } from "@react-pdf/renderer";

interface ReporteItem {
  item: string;
  descripcion: string | null;
  cantidad: number;
  unidad: string;
  proveedor_seleccionado: string | null;
  precio_unitario: number | null;
  precio_total: number | null;
  plazo_entrega_dias: number | null;
  cotizaciones: Array<{ proveedor_nombre: string; precio_unitario: number; fuente: string }>;
}

interface ReporteDatos {
  titulo: string;
  fecha: string;
  proyecto: Record<string, unknown> | null;
  items: ReporteItem[];
  proveedores_detalle: Record<string, unknown>;
  resumen: {
    total_items: number;
    items_cotizados: number;
    monto_total: number;
    proveedores_evaluados: number;
    max_plazo_dias: number;
  };
  secciones: string[];
}

// ── PDF Styles ──────────────────────────────────────────────────────────────

const styles = StyleSheet.create({
  page: { backgroundColor: "#FFFFFF", padding: 40, fontFamily: "Helvetica", fontSize: 10, color: "#1e1e3a" },
  header: { marginBottom: 24, borderBottom: "2px solid #6366f1", paddingBottom: 12 },
  headerTitle: { fontSize: 20, fontWeight: "bold", color: "#1e1e3a", marginBottom: 4 },
  headerSub: { fontSize: 9, color: "#64748b" },
  section: { marginBottom: 20 },
  sectionTitle: { fontSize: 12, fontWeight: "bold", color: "#6366f1", marginBottom: 10, textTransform: "uppercase", letterSpacing: 1 },
  kpiRow: { flexDirection: "row", gap: 10, marginBottom: 12 },
  kpiBox: { flex: 1, padding: 10, backgroundColor: "#f8f9ff", borderRadius: 4, border: "1px solid #e2e8f0" },
  kpiValue: { fontSize: 16, fontWeight: "bold", color: "#6366f1", marginBottom: 2 },
  kpiLabel: { fontSize: 8, color: "#64748b", textTransform: "uppercase" },
  table: { marginBottom: 8 },
  tableHeader: { flexDirection: "row", backgroundColor: "#1e1e3a", padding: "6 8" },
  tableHeaderCell: { color: "#ffffff", fontSize: 8, fontWeight: "bold", flex: 1 },
  tableRow: { flexDirection: "row", padding: "5 8", borderBottom: "1px solid #f1f5f9" },
  tableRowAlt: { flexDirection: "row", padding: "5 8", borderBottom: "1px solid #f1f5f9", backgroundColor: "#fafbff" },
  tableCell: { fontSize: 9, color: "#334155", flex: 1 },
  tableCellBold: { fontSize: 9, color: "#1e1e3a", fontWeight: "bold", flex: 1 },
  footer: { position: "absolute", bottom: 30, left: 40, right: 40, textAlign: "center", fontSize: 8, color: "#94a3b8", borderTop: "1px solid #e2e8f0", paddingTop: 8 },
  provCard: { marginBottom: 10, padding: 10, backgroundColor: "#f8f9ff", borderRadius: 4, border: "1px solid #e2e8f0" },
  provName: { fontSize: 11, fontWeight: "bold", color: "#1e1e3a", marginBottom: 4 },
  provDetail: { fontSize: 9, color: "#64748b", marginBottom: 2 },
});

// ── PDF Document ────────────────────────────────────────────────────────────

function ReportePDF({ datos }: { datos: ReporteDatos }) {
  const fmt = (n: number | null | undefined) =>
    n != null ? `$${Math.round(n).toLocaleString("es-CL")}` : "—";

  return (
    <Document title={datos.titulo}>
      <Page size="A4" style={styles.page}>

        {/* Header */}
        <View style={styles.header}>
          <Text style={styles.headerTitle}>{datos.titulo}</Text>
          <Text style={styles.headerSub}>
            Generado el {datos.fecha}
            {datos.proyecto ? ` · Proyecto: ${(datos.proyecto as Record<string, string>).nombre || ""}` : ""}
          </Text>
        </View>

        {/* Resumen */}
        {datos.secciones.includes("resumen") && (
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>Resumen ejecutivo</Text>
            <View style={styles.kpiRow}>
              <View style={styles.kpiBox}>
                <Text style={styles.kpiValue}>{fmt(datos.resumen.monto_total)}</Text>
                <Text style={styles.kpiLabel}>Monto total CLP</Text>
              </View>
              <View style={styles.kpiBox}>
                <Text style={styles.kpiValue}>{datos.resumen.items_cotizados}/{datos.resumen.total_items}</Text>
                <Text style={styles.kpiLabel}>Ítems cotizados</Text>
              </View>
              <View style={styles.kpiBox}>
                <Text style={styles.kpiValue}>{datos.resumen.proveedores_evaluados}</Text>
                <Text style={styles.kpiLabel}>Cotizaciones evaluadas</Text>
              </View>
              <View style={styles.kpiBox}>
                <Text style={styles.kpiValue}>{datos.resumen.max_plazo_dias}d</Text>
                <Text style={styles.kpiLabel}>Plazo máximo</Text>
              </View>
            </View>
          </View>
        )}

        {/* Ítems */}
        {datos.secciones.includes("items") && datos.items.length > 0 && (
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>Detalle de ítems</Text>
            <View style={styles.table}>
              <View style={styles.tableHeader}>
                {["Ítem", "Cant.", "Proveedor", "P. Unit.", "P. Total", "Plazo"].map(h => (
                  <Text key={h} style={styles.tableHeaderCell}>{h}</Text>
                ))}
              </View>
              {datos.items.map((it, i) => (
                <View key={i} style={i % 2 === 0 ? styles.tableRow : styles.tableRowAlt}>
                  <Text style={styles.tableCellBold}>{it.item}</Text>
                  <Text style={styles.tableCell}>{it.cantidad} {it.unidad}</Text>
                  <Text style={styles.tableCell}>{it.proveedor_seleccionado || "—"}</Text>
                  <Text style={styles.tableCell}>{fmt(it.precio_unitario)}</Text>
                  <Text style={styles.tableCellBold}>{fmt(it.precio_total)}</Text>
                  <Text style={styles.tableCell}>{it.plazo_entrega_dias ? `${it.plazo_entrega_dias}d` : "—"}</Text>
                </View>
              ))}
            </View>
          </View>
        )}

        {/* Comparativa */}
        {datos.secciones.includes("comparativa") && datos.items.some(it => it.cotizaciones?.length > 0) && (
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>Comparativa de proveedores</Text>
            <View style={styles.table}>
              <View style={styles.tableHeader}>
                {["Ítem", "Proveedor", "Precio Unit.", "Fuente"].map(h => (
                  <Text key={h} style={styles.tableHeaderCell}>{h}</Text>
                ))}
              </View>
              {datos.items.flatMap((it, ii) =>
                (it.cotizaciones || []).map((c, ci) => (
                  <View key={`${ii}-${ci}`} style={(ii + ci) % 2 === 0 ? styles.tableRow : styles.tableRowAlt}>
                    <Text style={styles.tableCellBold}>{it.item}</Text>
                    <Text style={styles.tableCell}>{c.proveedor_nombre}</Text>
                    <Text style={styles.tableCell}>{fmt(c.precio_unitario)}</Text>
                    <Text style={styles.tableCell}>{c.fuente || "—"}</Text>
                  </View>
                ))
              )}
            </View>
          </View>
        )}

        {/* Footer */}
        <Text style={styles.footer} render={({ pageNumber, totalPages }) => `Claria · Cotizador Inteligente · Página ${pageNumber} de ${totalPages}`} fixed />
      </Page>

      {/* Proveedores page */}
      {datos.secciones.includes("proveedores") && Object.keys(datos.proveedores_detalle).length > 0 && (
        <Page size="A4" style={styles.page}>
          <View style={styles.header}>
            <Text style={styles.headerTitle}>{datos.titulo}</Text>
            <Text style={styles.headerSub}>Ficha de proveedores</Text>
          </View>
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>Proveedores evaluados</Text>
            {Object.values(datos.proveedores_detalle).map((prov: unknown, i) => {
              const p = prov as Record<string, unknown>;
              return (
                <View key={i} style={styles.provCard}>
                  <Text style={styles.provName}>{p.nombre as string || "Proveedor"}</Text>
                  {p.email && <Text style={styles.provDetail}>Email: {p.email as string}</Text>}
                  {p.telefono && <Text style={styles.provDetail}>Tel: {p.telefono as string}</Text>}
                  {p.categoria && <Text style={styles.provDetail}>Categoría: {p.categoria as string}</Text>}
                  {p.rating_promedio != null && (
                    <Text style={styles.provDetail}>
                      Rating: {p.rating_promedio as number}/5 ({p.total_ratings as number} evaluaciones) · OCs: {p.total_ocs_historial as number}
                    </Text>
                  )}
                  {p.es_nuevo && <Text style={{ ...styles.provDetail, color: "#f59e0b" }}>Proveedor nuevo — sin historial previo</Text>}
                </View>
              );
            })}
          </View>
          <Text style={styles.footer} render={({ pageNumber, totalPages }) => `Claria · Cotizador Inteligente · Página ${pageNumber} de ${totalPages}`} fixed />
        </Page>
      )}
    </Document>
  );
}

// ── Screen Preview + Download ───────────────────────────────────────────────

export default function ReporteTemplate({ datos }: { datos: ReporteDatos }) {
  const [ready, setReady] = useState(false);

  const fmt = (n: number | null | undefined) =>
    n != null ? `$${Math.round(n).toLocaleString("es-CL")}` : "—";

  return (
    <div>
      {/* Download button */}
      <div style={{ marginBottom: 20, display: "flex", gap: 8, alignItems: "center" }}>
        <PDFDownloadLink
          document={<ReportePDF datos={datos} />}
          fileName={`${datos.titulo.replace(/\s+/g, "_")}.pdf`}
          onLoad={() => setReady(true)}
        >
          {({ loading }) => (
            <button style={{ padding: "10px 24px", fontWeight: 700, fontSize: 12, background: loading ? "#1a1a2e" : "#6366f1", color: loading ? "#475569" : "#fff", border: "none", borderRadius: 8, cursor: loading ? "wait" : "pointer", fontFamily: "inherit" }}>
              {loading ? "Preparando PDF..." : "Descargar PDF"}
            </button>
          )}
        </PDFDownloadLink>
        {ready && <span style={{ fontSize: 10, color: "#34d399" }}>PDF listo</span>}
      </div>

      {/* Screen preview */}
      <div style={{ background: "#fff", borderRadius: 12, padding: "40px 48px", color: "#1e1e3a", fontFamily: "Georgia, serif" }}>

        {/* Header */}
        <div style={{ borderBottom: "3px solid #6366f1", paddingBottom: 16, marginBottom: 24 }}>
          <div style={{ fontSize: 24, fontWeight: 800, color: "#1e1e3a", marginBottom: 4 }}>{datos.titulo}</div>
          <div style={{ fontSize: 12, color: "#64748b" }}>
            Generado el {datos.fecha}
            {datos.proyecto ? ` · Proyecto: ${(datos.proyecto as Record<string, string>).nombre || ""}` : ""}
          </div>
        </div>

        {/* Resumen */}
        {datos.secciones.includes("resumen") && (
          <div style={{ marginBottom: 28 }}>
            <div style={{ fontSize: 11, fontWeight: 700, color: "#6366f1", textTransform: "uppercase", letterSpacing: "0.12em", marginBottom: 12 }}>Resumen ejecutivo</div>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12 }}>
              {[
                { label: "Monto total", value: fmt(datos.resumen.monto_total) },
                { label: "Ítems cotizados", value: `${datos.resumen.items_cotizados}/${datos.resumen.total_items}` },
                { label: "Cotizaciones evaluadas", value: `${datos.resumen.proveedores_evaluados}` },
                { label: "Plazo máximo", value: `${datos.resumen.max_plazo_dias} días` },
              ].map(k => (
                <div key={k.label} style={{ padding: "12px 14px", background: "#f8f9ff", borderRadius: 6, border: "1px solid #e2e8f0" }}>
                  <div style={{ fontSize: 16, fontWeight: 800, color: "#6366f1", marginBottom: 3 }}>{k.value}</div>
                  <div style={{ fontSize: 10, color: "#64748b", textTransform: "uppercase" }}>{k.label}</div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Items table */}
        {datos.secciones.includes("items") && datos.items.length > 0 && (
          <div style={{ marginBottom: 28 }}>
            <div style={{ fontSize: 11, fontWeight: 700, color: "#6366f1", textTransform: "uppercase", letterSpacing: "0.12em", marginBottom: 12 }}>Detalle de ítems</div>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 11 }}>
              <thead>
                <tr style={{ background: "#1e1e3a" }}>
                  {["Ítem", "Cant.", "Proveedor", "P. Unit.", "P. Total", "Plazo"].map(h => (
                    <th key={h} style={{ padding: "8px 10px", color: "#fff", textAlign: "left", fontSize: 9, textTransform: "uppercase" }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {datos.items.map((it, i) => (
                  <tr key={i} style={{ background: i % 2 === 0 ? "#fff" : "#f8f9ff" }}>
                    <td style={{ padding: "7px 10px", fontWeight: 600, color: "#1e1e3a", borderBottom: "1px solid #f1f5f9" }}>{it.item}</td>
                    <td style={{ padding: "7px 10px", color: "#64748b", borderBottom: "1px solid #f1f5f9" }}>{it.cantidad} {it.unidad}</td>
                    <td style={{ padding: "7px 10px", color: "#64748b", borderBottom: "1px solid #f1f5f9" }}>{it.proveedor_seleccionado || "—"}</td>
                    <td style={{ padding: "7px 10px", color: "#334155", borderBottom: "1px solid #f1f5f9" }}>{fmt(it.precio_unitario)}</td>
                    <td style={{ padding: "7px 10px", fontWeight: 700, color: "#6366f1", borderBottom: "1px solid #f1f5f9" }}>{fmt(it.precio_total)}</td>
                    <td style={{ padding: "7px 10px", color: "#64748b", borderBottom: "1px solid #f1f5f9" }}>{it.plazo_entrega_dias ? `${it.plazo_entrega_dias}d` : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* Comparativa */}
        {datos.secciones.includes("comparativa") && datos.items.some(it => it.cotizaciones?.length > 0) && (
          <div style={{ marginBottom: 28 }}>
            <div style={{ fontSize: 11, fontWeight: 700, color: "#6366f1", textTransform: "uppercase", letterSpacing: "0.12em", marginBottom: 12 }}>Comparativa de proveedores</div>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 11 }}>
              <thead>
                <tr style={{ background: "#1e1e3a" }}>
                  {["Ítem", "Proveedor", "Precio Unit.", "Fuente"].map(h => (
                    <th key={h} style={{ padding: "8px 10px", color: "#fff", textAlign: "left", fontSize: 9, textTransform: "uppercase" }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {datos.items.flatMap((it, ii) =>
                  (it.cotizaciones || []).map((c, ci) => (
                    <tr key={`${ii}-${ci}`} style={{ background: (ii + ci) % 2 === 0 ? "#fff" : "#f8f9ff" }}>
                      <td style={{ padding: "7px 10px", fontWeight: 600, borderBottom: "1px solid #f1f5f9" }}>{it.item}</td>
                      <td style={{ padding: "7px 10px", color: "#64748b", borderBottom: "1px solid #f1f5f9" }}>{c.proveedor_nombre}</td>
                      <td style={{ padding: "7px 10px", color: "#334155", borderBottom: "1px solid #f1f5f9" }}>{fmt(c.precio_unitario)}</td>
                      <td style={{ padding: "7px 10px", color: "#64748b", borderBottom: "1px solid #f1f5f9" }}>{c.fuente || "—"}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        )}

        {/* Proveedores */}
        {datos.secciones.includes("proveedores") && Object.keys(datos.proveedores_detalle).length > 0 && (
          <div style={{ marginBottom: 28 }}>
            <div style={{ fontSize: 11, fontWeight: 700, color: "#6366f1", textTransform: "uppercase", letterSpacing: "0.12em", marginBottom: 12 }}>Ficha de proveedores</div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
              {Object.values(datos.proveedores_detalle).map((prov: unknown, i) => {
                const p = prov as Record<string, unknown>;
                return (
                  <div key={i} style={{ padding: "12px 14px", background: "#f8f9ff", borderRadius: 6, border: "1px solid #e2e8f0" }}>
                    <div style={{ fontSize: 13, fontWeight: 700, color: "#1e1e3a", marginBottom: 6 }}>{p.nombre as string}</div>
                    {p.email && <div style={{ fontSize: 10, color: "#64748b" }}>✉ {p.email as string}</div>}
                    {p.telefono && <div style={{ fontSize: 10, color: "#64748b" }}>☎ {p.telefono as string}</div>}
                    {p.rating_promedio != null && (
                      <div style={{ fontSize: 10, color: "#64748b", marginTop: 4 }}>
                        Rating: {p.rating_promedio as number}/5 · OCs: {p.total_ocs_historial as number}
                        {p.es_nuevo && <span style={{ color: "#f59e0b", marginLeft: 8 }}>Nuevo</span>}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* Footer */}
        <div style={{ borderTop: "1px solid #e2e8f0", paddingTop: 12, fontSize: 10, color: "#94a3b8", textAlign: "center" }}>
          Claria · Cotizador Inteligente · {datos.fecha}
        </div>
      </div>
    </div>
  );
}
