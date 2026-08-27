"use client";
import { Document, Page, View, Text, Image, StyleSheet } from "@react-pdf/renderer";

export interface OCData {
  numero_oc: string;
  fecha: string;
  nombre_item: string;
  proveedor_nombre: string;
  proveedor_email?: string | null;
  cantidad: number;
  unidad?: string | null;
  precio_unitario: number;
  moneda: string;
  subtotal: number;
  iva: number;
  total: number;
  condiciones_pago: string;
  plazo_entrega: string;
  notas?: string | null;
  /** Dónde despachar. Distinta de `emisor_direccion`, que es la administrativa
   * (la scrapea el onboarding y no está verificada). Si falta, el bloque no se
   * dibuja: mejor que el proveedor pregunte a insinuar un destino sin confirmar.
   * Espeja `_despacho()` en `backend/app/services/oc_pdf.py` — cambiar los dos. */
  direccion_despacho?: string | null;
  /** Perfil de marca de la organización emisora — si falta, se usa el
   * fallback genérico "Baiyer" (ej. cuentas legado sin onboarding nuevo). */
  emisor_nombre?: string | null;
  emisor_rut?: string | null;
  emisor_direccion?: string | null;
  emisor_logo_url?: string | null;
}

const s = StyleSheet.create({
  page: { fontFamily: "Helvetica", fontSize: 10, padding: 48, color: "#1e293b", backgroundColor: "#ffffff" },
  header: { flexDirection: "row", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 32, paddingBottom: 16, borderBottomWidth: 2, borderBottomColor: "#6366f1" },
  logoText: { fontSize: 22, fontFamily: "Helvetica-Bold", color: "#6366f1", letterSpacing: 2 },
  logoImg: { width: 100, height: 40, objectFit: "contain" as const, marginBottom: 4 },
  ocTitle: { fontSize: 9, color: "#64748b", textTransform: "uppercase", letterSpacing: 1, marginTop: 2 },
  ocNumero: { fontSize: 20, fontFamily: "Helvetica-Bold", color: "#1e293b", textAlign: "right" },
  ocFecha: { fontSize: 9, color: "#64748b", textAlign: "right", marginTop: 2 },
  partiesRow: { flexDirection: "row", gap: 24, marginBottom: 28 },
  partyBox: { flex: 1, backgroundColor: "#f8fafc", padding: 14, borderRadius: 4 },
  partyLabel: { fontSize: 8, color: "#6366f1", fontFamily: "Helvetica-Bold", textTransform: "uppercase", letterSpacing: 1, marginBottom: 6 },
  partyName: { fontSize: 11, fontFamily: "Helvetica-Bold", color: "#1e293b", marginBottom: 2 },
  partyDetail: { fontSize: 9, color: "#64748b", marginBottom: 1 },
  tableHeader: { flexDirection: "row", backgroundColor: "#6366f1", padding: "8 12", borderRadius: 4, marginBottom: 2 },
  tableHeaderText: { color: "#ffffff", fontFamily: "Helvetica-Bold", fontSize: 9, textTransform: "uppercase" },
  tableRow: { flexDirection: "row", padding: "10 12", borderBottomWidth: 1, borderBottomColor: "#f1f5f9" },
  tableRowAlt: { flexDirection: "row", padding: "10 12", backgroundColor: "#f8fafc", borderBottomWidth: 1, borderBottomColor: "#f1f5f9" },
  col1: { flex: 4 },
  col2: { flex: 1, textAlign: "center" },
  col3: { flex: 2, textAlign: "right" },
  col4: { flex: 2, textAlign: "right" },
  totalsBox: { marginTop: 16, alignItems: "flex-end" },
  totalRow: { flexDirection: "row", gap: 24, marginBottom: 4 },
  totalLabel: { fontSize: 9, color: "#64748b", width: 120, textAlign: "right" },
  totalValue: { fontSize: 9, color: "#1e293b", width: 100, textAlign: "right" },
  totalFinalLabel: { fontSize: 12, fontFamily: "Helvetica-Bold", color: "#1e293b", width: 120, textAlign: "right" },
  totalFinalValue: { fontSize: 12, fontFamily: "Helvetica-Bold", color: "#6366f1", width: 100, textAlign: "right" },
  totalLine: { width: 244, height: 1, backgroundColor: "#e2e8f0", marginBottom: 6, marginTop: 6 },
  condiciones: { flexDirection: "row", gap: 16, marginTop: 28, padding: 14, backgroundColor: "#f8fafc", borderRadius: 4 },
  condicionBox: { flex: 1 },
  condicionLabel: { fontSize: 8, color: "#6366f1", fontFamily: "Helvetica-Bold", textTransform: "uppercase", letterSpacing: 1, marginBottom: 4 },
  condicionVal: { fontSize: 10, color: "#1e293b" },
  despacho: { marginTop: 12, padding: 14, backgroundColor: "#f8fafc", borderRadius: 4 },
  footer: { position: "absolute", bottom: 24, left: 48, right: 48, flexDirection: "row", justifyContent: "space-between", borderTopWidth: 1, borderTopColor: "#e2e8f0", paddingTop: 8 },
  footerText: { fontSize: 8, color: "#94a3b8" },
});

function fmt(n: number, moneda: string) {
  if (moneda === "CLP") return `$${Math.round(n).toLocaleString("es-CL")}`;
  return `${moneda} ${n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function fmtCantidad(cantidad: number, unidad?: string | null) {
  return `${Number(cantidad.toFixed(3)).toString()} ${unidad || "und"}`;
}

export default function OCPDFTemplate({ oc }: { oc: OCData }) {
  const emisorNombre = oc.emisor_nombre || "Baiyer";

  return (
    <Document title={`OC ${oc.numero_oc}`} author={emisorNombre}>
      <Page size="A4" style={s.page}>

        {/* Header */}
        <View style={s.header}>
          <View>
            {oc.emisor_logo_url ? (
              <Image style={s.logoImg} src={oc.emisor_logo_url} />
            ) : (
              <Text style={s.logoText}>{emisorNombre}</Text>
            )}
            <Text style={s.ocTitle}>Orden de Compra</Text>
          </View>
          <View>
            <Text style={s.ocNumero}>{oc.numero_oc}</Text>
            <Text style={s.ocFecha}>Fecha: {oc.fecha}</Text>
          </View>
        </View>

        {/* Emisor / Proveedor */}
        <View style={s.partiesRow}>
          <View style={s.partyBox}>
            <Text style={s.partyLabel}>Emisor</Text>
            <Text style={s.partyName}>{emisorNombre}</Text>
            {oc.emisor_rut && <Text style={s.partyDetail}>RUT: {oc.emisor_rut}</Text>}
            {oc.emisor_direccion && <Text style={s.partyDetail}>{oc.emisor_direccion}</Text>}
          </View>
          <View style={s.partyBox}>
            <Text style={s.partyLabel}>Proveedor</Text>
            <Text style={s.partyName}>{oc.proveedor_nombre}</Text>
            {oc.proveedor_email && <Text style={s.partyDetail}>{oc.proveedor_email}</Text>}
          </View>
        </View>

        {/* Tabla */}
        <View style={s.tableHeader}>
          <Text style={[s.tableHeaderText, s.col1]}>Descripción</Text>
          <Text style={[s.tableHeaderText, s.col2]}>Cant.</Text>
          <Text style={[s.tableHeaderText, s.col3]}>Precio Unit.</Text>
          <Text style={[s.tableHeaderText, s.col4]}>Total</Text>
        </View>
        <View style={s.tableRowAlt}>
          <Text style={[{ fontSize: 10, color: "#1e293b" }, s.col1]}>{oc.nombre_item}</Text>
          <Text style={[{ fontSize: 10, color: "#1e293b", textAlign: "center" }, s.col2]}>{fmtCantidad(oc.cantidad, oc.unidad)}</Text>
          <Text style={[{ fontSize: 10, color: "#1e293b", textAlign: "right" }, s.col3]}>{fmt(oc.precio_unitario, oc.moneda)}</Text>
          <Text style={[{ fontSize: 10, color: "#1e293b", textAlign: "right" }, s.col4]}>{fmt(oc.subtotal, oc.moneda)}</Text>
        </View>

        {/* Totales */}
        <View style={s.totalsBox}>
          <View style={s.totalRow}>
            <Text style={s.totalLabel}>Subtotal</Text>
            <Text style={s.totalValue}>{fmt(oc.subtotal, oc.moneda)}</Text>
          </View>
          <View style={s.totalRow}>
            <Text style={s.totalLabel}>IVA (19%)</Text>
            <Text style={s.totalValue}>{fmt(oc.iva, oc.moneda)}</Text>
          </View>
          <View style={[s.totalLine]} />
          <View style={s.totalRow}>
            <Text style={s.totalFinalLabel}>Total</Text>
            <Text style={s.totalFinalValue}>{fmt(oc.total, oc.moneda)}</Text>
          </View>
        </View>

        {/* Condiciones */}
        <View style={s.condiciones}>
          <View style={s.condicionBox}>
            <Text style={s.condicionLabel}>Condiciones de pago</Text>
            <Text style={s.condicionVal}>{oc.condiciones_pago}</Text>
          </View>
          <View style={s.condicionBox}>
            <Text style={s.condicionLabel}>Plazo de entrega</Text>
            <Text style={s.condicionVal}>{oc.plazo_entrega || "A convenir"}</Text>
          </View>
          {oc.notas && (
            <View style={s.condicionBox}>
              <Text style={s.condicionLabel}>Notas</Text>
              <Text style={s.condicionVal}>{oc.notas}</Text>
            </View>
          )}
        </View>

        {/* Despacho — sólo si está configurado (ver comentario en OCData) */}
        {oc.direccion_despacho && (
          <View style={s.despacho}>
            <Text style={s.condicionLabel}>Despachar a</Text>
            <Text style={s.condicionVal}>{oc.direccion_despacho}</Text>
          </View>
        )}

        {/* Footer */}
        <View style={s.footer} fixed>
          <Text style={s.footerText}>
            {oc.emisor_nombre ? `${oc.emisor_nombre} · generado vía Baiyer` : "Generado por Baiyer"}
          </Text>
          <Text style={s.footerText}>{oc.numero_oc} · {oc.fecha}</Text>
        </View>

      </Page>
    </Document>
  );
}
