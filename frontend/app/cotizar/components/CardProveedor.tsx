"use client";
import { useState } from "react";

export interface Resultado {
  titulo: string;
  precio: number | null;
  moneda: string;
  url: string;
  fuente: string;
  fuente_label?: string;
  pais: string;
  tipo_proveedor?: string;
  relevante?: boolean;
  proveedor?: string;
  thumbnail?: string | null;
  // Producto
  marca?: string | null;
  numero_parte?: string | null;
  descripcion?: string | null;
  condicion?: string | null;
  categoria?: string | null;
  lifecycle?: string | null;
  // Disponibilidad
  stock?: number | null;
  stock_disponible?: boolean | null;
  cantidad_minima?: number | null;
  // Precios
  precio_original?: number | null;
  moneda_original?: string | null;
  precio_volumen?: Array<{ qty: number; precio_usd?: number; precio_eur?: number; precio_clp?: number }> | null;
  // Logística
  envio_gratis?: boolean | null;
  plazo_entrega_estimado?: string | null;
  ubicacion_vendedor?: string | null;
  // Calidad
  rating?: number | null;
  num_reviews?: number | null;
  reputacion_vendedor?: string | null;
  ventas_realizadas?: number | null;
  // Certificaciones
  rohs?: boolean | null;
  datasheet_url?: string | null;
  garantia?: string | null;
  especificaciones?: Record<string, string> | null;
}

interface Props {
  resultado: Resultado;
  seleccionado: boolean;
  onSeleccionar: () => void;
  tasas?: Record<string, number>;
  /** Mismo producto visto en otras fuentes (incluye la oferta actual), ordenado por precio asc. */
  ofertas?: Resultado[];
  /** Para armar el mensaje de cotización (WhatsApp/email) */
  nombreItem?: string;
  cantidad?: number;
  /** Permite elegir una oferta específica del grupo (no solo la más barata) */
  onToggleOferta?: (url: string) => void;
  seleccionadosUrls?: Set<string>;
}

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface Contacto {
  email: string | null;
  telefono: string | null;
  whatsapp: { numero: string; link: string } | null;
  mensaje: string;
}

const PAIS_LABEL: Record<string, string> = {
  CL: "Chile", CN: "China", US: "USA", DE: "Alemania", ES: "España",
  MX: "México", BR: "Brasil", EU: "Europa", PL: "Polonia",
};
const FUENTE_LABEL: Record<string, string> = {
  google: "Google Shopping", mercadolibre: "MercadoLibre", alibaba: "Alibaba",
  mouser: "Mouser", digikey: "DigiKey", tme: "TME", farnell: "Farnell", manual: "Manual",
  sodimac: "Sodimac", easy: "Easy", lasierra: "La Sierra", construmart: "Construmart",
  vitel: "Vitel", dartel: "Dartel", ferrelectrica: "Ferrelectrica", gobantes: "Gobantes", rhona: "Rhona",
  clcsa: "CLC Maderas", wmaderas: "W Maderas", ferramenta: "Ferramenta", maderas_dir: "Aserraderos CL",
};

function formatPrecio(precio: number, moneda: string): string {
  if (moneda === "CLP") return `$${Math.round(precio).toLocaleString("es-CL")}`;
  if (moneda === "EUR") return `€${precio.toLocaleString("de-DE", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  return `$${precio.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function StarRating({ rating }: { rating: number }) {
  return (
    <span style={{ color: "#f59e0b", fontSize: 10, letterSpacing: -0.5 }}>
      {"★".repeat(Math.round(rating))}{"☆".repeat(5 - Math.round(rating))}
      <span style={{ color: "var(--text-muted)", marginLeft: 3 }}>{rating.toFixed(1)}</span>
    </span>
  );
}

export default function CardProveedor({ resultado, seleccionado, onSeleccionar, ofertas, nombreItem, cantidad, onToggleOferta, seleccionadosUrls }: Props) {
  const [imgError, setImgError] = useState(false);
  const [showSpecs, setShowSpecs] = useState(false);

  // Contacto para cotizar (scrape de email + WhatsApp con mensaje pre-hecho)
  const [contacto, setContacto] = useState<Contacto | null>(null);
  const [cargandoContacto, setCargandoContacto] = useState(false);
  const [copiado, setCopiado] = useState<"" | "email" | "mensaje">("");

  const cargarContacto = async () => {
    if (contacto || cargandoContacto || !resultado.url) return;
    setCargandoContacto(true);
    try {
      const res = await fetch(`${API_URL}/api/contacto`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          url: resultado.url,
          proveedor: resultado.proveedor,
          nombre_item: nombreItem || resultado.titulo,
          cantidad: cantidad || 1,
          email_existente: (resultado as unknown as { contacto?: string }).contacto,
        }),
      });
      if (res.ok) setContacto(await res.json());
    } catch { /* silencioso */ } finally {
      setCargandoContacto(false);
    }
  };

  const copiar = async (texto: string, cual: "email" | "mensaje") => {
    try {
      await navigator.clipboard.writeText(texto);
      setCopiado(cual);
      setTimeout(() => setCopiado(""), 1800);
    } catch { /* clipboard no disponible */ }
  };

  const paisLabel = PAIS_LABEL[resultado.pais] ?? resultado.pais ?? "Internacional";
  const fuenteLabel = resultado.fuente_label || FUENTE_LABEL[resultado.fuente] || resultado.fuente;
  // El título suele ser la descripción real del producto (sobre todo en Mouser/DigiKey/TME/Farnell,
  // donde "proveedor" es solo el nombre del distribuidor genérico, ej. "Mouser").
  const nombre = resultado.titulo || resultado.proveedor;
  const subtitulo = resultado.titulo && resultado.proveedor && resultado.proveedor !== resultado.titulo ? resultado.proveedor : null;
  const showThumb = resultado.thumbnail && !imgError;

  const stockNum = typeof resultado.stock === "number" ? resultado.stock : null;
  const stockLabel = stockNum !== null
    ? stockNum > 0 ? `${stockNum.toLocaleString("es-CL")} uds.` : "Sin stock"
    : resultado.stock_disponible === true ? "En stock"
    : resultado.stock_disponible === false ? "Sin stock"
    : null;
  const stockOk = stockNum === null ? resultado.stock_disponible !== false : stockNum > 0;

  const specsEntries = resultado.especificaciones ? Object.entries(resultado.especificaciones).slice(0, 8) : [];

  return (
    <div style={{
      background: seleccionado ? "var(--fill-success)" : "var(--bg-surface)",
      border: `1px solid ${seleccionado ? "var(--palette-green-500, #16a34a)" : "var(--border-default)"}`,
      borderTop: "none",
      padding: "14px 16px",
      display: "flex",
      gap: 14,
      alignItems: "flex-start",
    }}>

      {/* Thumbnail */}
      <div style={{
        width: 52, height: 52, flexShrink: 0,
        background: "var(--bg-base)", border: "1px solid var(--border-default)",
        overflow: "hidden", display: "flex", alignItems: "center", justifyContent: "center",
      }}>
        {showThumb ? (
          <img src={resultado.thumbnail!} alt={resultado.titulo} onError={() => setImgError(true)}
            style={{ width: "100%", height: "100%", objectFit: "cover" }} />
        ) : (
          <span className="label" style={{ color: "var(--text-muted)" }}>IMG</span>
        )}
      </div>

      {/* Info */}
      <div style={{ flex: 1, minWidth: 0 }}>
        {seleccionado && (
          <div className="label" style={{ color: "var(--text-success)", marginBottom: 2 }}>✓ Seleccionado</div>
        )}

        <div style={{ fontSize: 12, fontWeight: 700, color: "var(--text-primary)", marginBottom: 3, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          {nombre}
        </div>

        {subtitulo && (
          <div className="label" style={{ color: "var(--text-muted)", marginBottom: 3 }}>
            {subtitulo}
          </div>
        )}

        {(resultado.numero_parte || resultado.marca) && (
          <div className="label" style={{ color: "var(--text-muted)", marginBottom: 4, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
            {resultado.marca && <span style={{ fontWeight: 700 }}>{resultado.marca}</span>}
            {resultado.marca && resultado.numero_parte && " · "}
            {resultado.numero_parte && <span style={{ fontFamily: "var(--font-mono)" }}>{resultado.numero_parte}</span>}
          </div>
        )}

        {/* Badges */}
        <div style={{ display: "flex", gap: 4, flexWrap: "wrap", alignItems: "center", marginBottom: 6 }}>
          <span className="label" style={{ background: "var(--bg-base)", border: "1px solid var(--border-default)", padding: "1px 5px" }}>
            {fuenteLabel}
          </span>
          <span className="label" style={{ color: "var(--text-muted)" }}>{paisLabel}</span>
          {resultado.condicion && resultado.condicion !== "nuevo" && (
            <span className="label" style={{ color: "#d97706", border: "1px solid #d97706", padding: "1px 5px" }}>
              {resultado.condicion}
            </span>
          )}
          {resultado.rohs === true && (
            <span className="label" style={{ color: "#16a34a", border: "1px solid #16a34a", padding: "1px 5px" }}>
              RoHS
            </span>
          )}
          {resultado.lifecycle && resultado.lifecycle.toLowerCase() !== "active" && (
            <span className="label" style={{ color: "#dc2626", border: "1px solid #dc2626", padding: "1px 5px" }}>
              {resultado.lifecycle}
            </span>
          )}
        </div>

        {/* Métricas */}
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
          {stockLabel && (
            <span className="label" style={{ color: stockOk ? "#16a34a" : "#dc2626" }}>
              ● {stockLabel}
            </span>
          )}
          {resultado.cantidad_minima != null && resultado.cantidad_minima > 1 && (
            <span className="label" style={{ color: "var(--text-muted)" }}>MOQ {resultado.cantidad_minima}</span>
          )}
          {resultado.envio_gratis === true && (
            <span className="label" style={{ color: "#16a34a" }}>Envío gratis</span>
          )}
          {resultado.plazo_entrega_estimado && (
            <span className="label" style={{ color: "var(--text-muted)" }}>{resultado.plazo_entrega_estimado}</span>
          )}
          {resultado.ubicacion_vendedor && (
            <span className="label" style={{ color: "var(--text-muted)" }}>📍 {resultado.ubicacion_vendedor}</span>
          )}
          {resultado.rating != null && resultado.rating > 0 && <StarRating rating={resultado.rating} />}
          {resultado.num_reviews != null && resultado.num_reviews > 0 && (
            <span className="label" style={{ color: "var(--text-muted)" }}>({resultado.num_reviews.toLocaleString("es-CL")} reseñas)</span>
          )}
          {resultado.reputacion_vendedor && (
            <span className="label" style={{ color: "var(--text-muted)" }}>Rep: {resultado.reputacion_vendedor}</span>
          )}
          {resultado.ventas_realizadas != null && resultado.ventas_realizadas > 0 && (
            <span className="label" style={{ color: "var(--text-muted)" }}>{resultado.ventas_realizadas.toLocaleString("es-CL")} ventas</span>
          )}
          {resultado.garantia && (
            <span className="label" style={{ color: "var(--text-muted)" }}>Garantía: {resultado.garantia}</span>
          )}
        </div>

        {/* Precios por volumen */}
        {resultado.precio_volumen && resultado.precio_volumen.length > 1 && (
          <div style={{ marginTop: 5, display: "flex", gap: 3, flexWrap: "wrap" }}>
            <span className="label" style={{ color: "var(--text-muted)", marginRight: 2 }}>Volumen:</span>
            {resultado.precio_volumen.slice(0, 4).map((pv, i) => (
              <span key={i} className="label" style={{
                background: "var(--bg-base)", border: "1px solid var(--border-default)",
                padding: "1px 5px", fontFamily: "var(--font-mono)",
              }}>
                {pv.qty}+ → {pv.precio_clp
                  ? `$${Math.round(pv.precio_clp).toLocaleString("es-CL")}`
                  : pv.precio_usd ? `$${pv.precio_usd} USD` : `€${pv.precio_eur} EUR`}
              </span>
            ))}
          </div>
        )}

        {/* Especificaciones */}
        {specsEntries.length > 0 && (
          <div style={{ marginTop: 5 }}>
            <button onClick={() => setShowSpecs(v => !v)} className="label"
              style={{ background: "none", border: "none", cursor: "pointer", color: "var(--text-muted)", padding: 0, textDecoration: "underline" }}>
              {showSpecs ? "Ocultar specs" : `${specsEntries.length} especificaciones`}
            </button>
            {showSpecs && (
              <div style={{ marginTop: 4, display: "grid", gridTemplateColumns: "1fr 1fr", gap: "2px 12px" }}>
                {specsEntries.map(([k, v]) => (
                  <div key={k} className="label" style={{ color: "var(--text-muted)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    <span style={{ fontWeight: 600 }}>{k}:</span> {v}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Descripción breve (solo si aporta info distinta del título ya mostrado) */}
        {resultado.descripcion && resultado.descripcion !== resultado.titulo && (
          <div className="label" style={{ color: "var(--text-muted)", marginTop: 4, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
            {resultado.descripcion}
          </div>
        )}

        {/* Mismo producto visto en otras fuentes — comparativa de precios */}
        {ofertas && ofertas.length > 1 && (
          <div style={{ marginTop: 8, paddingTop: 8, borderTop: "1px dashed var(--border-default)" }}>
            <div className="label" style={{ color: "var(--text-muted)", marginBottom: 4 }}>
              Mismo producto en {ofertas.length} fuentes:
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              {ofertas.map((o, i) => {
                const esEsta = o.url === resultado.url;
                const labelFuente = o.fuente_label || FUENTE_LABEL[o.fuente] || o.fuente;
                const desc = o.titulo || o.descripcion || "";
                const elegible = !!onToggleOferta && !!o.url;
                const elegida = seleccionadosUrls?.has(o.url) ?? false;
                return (
                  <div
                    key={o.url || i}
                    style={{
                      display: "flex",
                      alignItems: "stretch",
                      gap: 8,
                      padding: "4px 6px",
                      borderLeft: `2px solid ${elegida ? "var(--accent)" : "var(--border-default)"}`,
                      background: elegida ? "var(--fill-error)" : "transparent",
                    }}
                  >
                    {/* Checkbox para elegir esta oferta específica */}
                    {elegible && (
                      <button
                        onClick={() => onToggleOferta!(o.url)}
                        title={elegida ? "Quitar de la selección" : "Elegir esta oferta"}
                        style={{
                          flexShrink: 0, width: 16, height: 16, alignSelf: "center", cursor: "pointer",
                          border: `1px solid ${elegida ? "var(--accent)" : "var(--border-strong)"}`,
                          background: elegida ? "var(--accent)" : "var(--bg-base)",
                          color: "#fff", fontSize: 11, lineHeight: 1, padding: 0,
                          display: "flex", alignItems: "center", justifyContent: "center",
                        }}
                      >
                        {elegida ? "✓" : ""}
                      </button>
                    )}
                    {/* Descripción + fuente + precio (link a la oferta) */}
                    <a
                      href={o.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      style={{ flex: 1, display: "flex", flexDirection: "column", gap: 1, textDecoration: "none", minWidth: 0 }}
                    >
                      <span
                        title={desc}
                        style={{
                          fontSize: 11,
                          color: elegida ? "var(--text-primary)" : "var(--text-secondary)",
                          fontWeight: elegida ? 700 : 400,
                          overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", lineHeight: 1.3,
                        }}
                      >
                        {desc || labelFuente}
                      </span>
                      <span className="label" style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
                        <span style={{ color: "var(--accent)" }}>
                          {labelFuente}{o.proveedor && o.proveedor !== labelFuente ? ` · ${o.proveedor}` : ""}
                          {esEsta ? " — más barata" : ""}
                        </span>
                        <span style={{ flexShrink: 0, fontFamily: "var(--font-mono)", color: "var(--text-primary)", fontWeight: 700 }}>
                          {o.precio != null ? formatPrecio(o.precio, o.moneda) : "A cotizar"}
                        </span>
                      </span>
                    </a>
                  </div>
                );
              })}
            </div>
            {onToggleOferta && (
              <div className="label" style={{ color: "var(--text-muted)", marginTop: 4 }}>
                Marca ✓ la oferta que quieras cotizar (no tiene que ser la más barata).
              </div>
            )}
          </div>
        )}
      </div>

      {/* Precio + acciones */}
      <div style={{ textAlign: "right", flexShrink: 0, minWidth: 110 }}>
        {resultado.precio != null ? (
          <div style={{ marginBottom: 6 }}>
            <div style={{ fontSize: 16, fontWeight: 800, color: seleccionado ? "var(--text-success)" : "var(--text-primary)", lineHeight: 1.1, letterSpacing: "-0.01em" }}>
              {formatPrecio(resultado.precio, resultado.moneda)}
            </div>
            <div className="label" style={{ color: "var(--text-muted)", marginTop: 2 }}>
              {resultado.moneda}
              {resultado.precio_original != null && resultado.moneda_original && resultado.moneda_original !== resultado.moneda && (
                <span style={{ marginLeft: 4, opacity: 0.7 }}>
                  ({resultado.moneda_original === "EUR" ? "€" : "$"}{resultado.precio_original.toLocaleString("en-US", { maximumFractionDigits: 2 })} {resultado.moneda_original})
                </span>
              )}
            </div>
          </div>
        ) : (
          <div className="label" style={{ color: "var(--text-muted)", background: "var(--bg-base)", border: "1px solid var(--border-default)", padding: "3px 8px", marginBottom: 8, display: "inline-block" }}>
            A cotizar
          </div>
        )}

        <div style={{ display: "flex", gap: 5, justifyContent: "flex-end", flexWrap: "wrap" }}>
          {resultado.datasheet_url && (
            <a href={resultado.datasheet_url} target="_blank" rel="noopener noreferrer"
              className="btn-swiss-secondary" style={{ fontSize: 10, padding: "4px 8px", textDecoration: "none" }}>
              DS
            </a>
          )}
          {resultado.url && (
            <a href={resultado.url} target="_blank" rel="noopener noreferrer"
              className="btn-swiss-secondary" style={{ fontSize: 10, padding: "4px 8px", textDecoration: "none" }}>
              Ver
            </a>
          )}
          {resultado.url && (
            <button onClick={cargarContacto} disabled={cargandoContacto}
              className="btn-swiss-secondary" style={{ fontSize: 10, padding: "4px 8px" }}>
              {cargandoContacto ? "Buscando…" : contacto ? "Contacto ▾" : "Cotizar"}
            </button>
          )}
          <button onClick={onSeleccionar}
            className={seleccionado ? "btn-swiss-secondary" : "btn-swiss-primary"}
            style={{ fontSize: 10, padding: "4px 8px" }}>
            {seleccionado ? "Quitar" : "Seleccionar"}
          </button>
        </div>
      </div>

      {/* Panel de contacto: email + WhatsApp con mensaje pre-hecho */}
      {contacto && (
        <div style={{
          marginTop: 10, paddingTop: 10, borderTop: "1px solid var(--border-subtle)",
          display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center",
        }}>
          {contacto.whatsapp ? (
            <>
              <a href={contacto.whatsapp.link} target="_blank" rel="noopener noreferrer"
                style={{
                  fontSize: 11, fontWeight: 700, textDecoration: "none",
                  color: "#fff", background: "#25D366", padding: "6px 12px",
                  display: "inline-flex", alignItems: "center", gap: 6,
                }}>
                WhatsApp con mensaje listo ↗
              </a>
              <button onClick={() => copiar(contacto.mensaje, "mensaje")}
                className="btn-swiss-secondary" style={{ fontSize: 10, padding: "5px 10px" }}>
                {copiado === "mensaje" ? "¡Copiado!" : "Copiar mensaje"}
              </button>
            </>
          ) : (
            <span className="label" style={{ color: "var(--text-muted)" }}>Sin WhatsApp en la página</span>
          )}

          {contacto.email ? (
            <button onClick={() => copiar(contacto.email!, "email")}
              className="btn-swiss-secondary" style={{ fontSize: 10, padding: "5px 10px" }}>
              {copiado === "email" ? "¡Copiado!" : `✉ ${contacto.email}`}
            </button>
          ) : (
            <span className="label" style={{ color: "var(--text-muted)" }}>Email no encontrado</span>
          )}
        </div>
      )}
    </div>
  );
}
