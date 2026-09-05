"use client";

import { useState } from "react";
import Image from "next/image";
import Figura from "./Figura";
import { useFrames, useFraseHero, useMirada, useTitulosTipeados } from "./hooks";
import {
  ACTORES, C, DEMO_URL, DISPLAY, ETAPAS, FAQS, FRASES, MONO, ORDENES, TITULOS,
} from "./datos";

const BASE = "/landing/baiyer/";
const CONTENEDOR: React.CSSProperties = { maxWidth: 1180, margin: "0 auto", padding: "0 24px" };
const GLOW = "0 0 22px rgba(16,0,255,.55),0 0 7px rgba(16,0,255,.45)";

/* ── Hilo del chat ──────────────────────────────────────────────────────────
   Los tiempos son frames del reloj único (40ms). `SENT` es el instante en que
   Camila manda el mensaje que menciona a Baiyer: todo lo del panel RFQ cuelga
   de ahí, así que las dos tarjetas quedan sincronizadas sin coordinarse.      */
const BORRADOR_PRE = "No sé, ";
const BORRADOR_CHIP = "@Baiyer";
const BORRADOR_POST = ", ¿cuál es la mejor opción considerando precio vs calidad?";
const LARGO_BORRADOR = BORRADOR_PRE.length + BORRADOR_CHIP.length + BORRADOR_POST.length;
const INICIO_TIPEO = 56;
const SENT = INICIO_TIPEO + LARGO_BORRADOR + 14;
const PANEL = SENT + 8;
const SI_PORFA = SENT + 210;
const TOTAL_FRAMES = 560;

type Msg = { quien: "camila" | "diego" | "baiyer"; at: number; time: string; pre: string; mention?: string; post?: string };

const MENSAJES: Msg[] = [
  { quien: "camila", at: 8, time: "9:38", pre: "Chicos, los nuevos ingenieros llegan el lunes! Necesitamos 5 computadores para ellos." },
  { quien: "diego", at: 30, time: "9:38", pre: "¿Cuáles tienes pensados? ¿ThinkPad o MacBook?" },
  { quien: "camila", at: SENT, time: "9:39", pre: BORRADOR_PRE, mention: BORRADOR_CHIP, post: BORRADOR_POST },
  { quien: "baiyer", at: SENT + 172, time: "9:40", pre: "Ya tengo las cotizaciones: ThinkPad E14 a $450.000 y MacBook Air a $600.000. Mejor precio/calidad son los ThinkPad. ¿Les pido despacho para el viernes?" },
  { quien: "camila", at: SI_PORFA, time: "9:41", pre: "Sí porfa!" },
  { quien: "baiyer", at: SENT + 238, time: "9:41", pre: "Correos enviados! ", mention: "@Cami", post: " te dejé en copia para hacer seguimiento :)" },
  { quien: "camila", at: SENT + 268, time: "9:42", pre: "Gracias Baiyer, eres un amor! <3" },
];

const PERSONAS = {
  camila: { name: "Camila Rojas", emoji: "🌸", bg: C.panel },
  diego: { name: "Diego Fuentes", emoji: "🐶", bg: C.panel },
  baiyer: { name: "Baiyer", emoji: "", bg: "#1f8b3a" },
} as const;

/** `[nombre, inicial, modelo, apareceEn, cotizaEn, precio, esThinkPadElegido]` */
const PROVEEDORES: [string, string, string, number, number, string, boolean][] = [
  ["MacOnline", "M", "MacBook Air M3", PANEL + 4, PANEL + 66, "$600.000", false],
  ["Lenovo Chile", "L", "ThinkPad E14 Gen 5", PANEL + 12, PANEL + 86, "$450.000", true],
  ["PC Factory", "P", "ThinkPad E14 Gen 5", PANEL + 20, PANEL + 106, "$468.900", true],
  ["Tecnoglobal", "T", "MacBook Air M3", PANEL + 28, PANEL + 126, "$629.000", false],
  ["Reifschneider", "R", "ThinkPad T14 Gen 4", PANEL + 36, PANEL + 148, "$512.400", true],
];

/* ── Piezas chicas ───────────────────────────────────────────────────────── */

function Titulo({ i, n, tamano = "clamp(34px,4.6vw,62px)" }: {
  i: number; n: number; tamano?: string;
}) {
  const [ini, medio, fin] = TITULOS[i];
  let resto = n;
  const a = ini.slice(0, Math.min(resto, ini.length));
  resto -= ini.length;
  const b = resto > 0 ? medio.slice(0, resto) : "";
  resto -= medio.length;
  const c = resto > 0 ? fin.slice(0, resto) : "";
  // El cursor se pega a la última palabra para que no quede huérfano al saltar
  // de línea; por eso el tramo final se parte en "todo menos la última palabra".
  const corte = c ? c.trimEnd().lastIndexOf(" ") : -1;
  const cabeza = c && corte > 0 ? c.slice(0, corte + 1) : "";
  const cola = c && corte > 0 ? c.slice(corte + 1) : c;

  return (
    <h2
      data-ttl={i}
      style={{ fontFamily: DISPLAY, fontWeight: 500, fontSize: tamano, lineHeight: 1.06, letterSpacing: ".01em", margin: "0 0 18px" }}
    >
      {/* El título se escribe recién en el cliente, así que sin esta copia el
          encabezado viaja VACÍO en el HTML del servidor: un buscador que no
          ejecuta JS ve una portada sin ningún <h2>, y un lector de pantalla
          leería el texto a medio tipear. La copia animada queda como
          decorativa para que no se anuncie dos veces. */}
      <span className="bl-solo-lectores">{TITULOS[i].join("")}</span>
      <span aria-hidden="true">
        {a}
        <span style={{ color: C.azul, textShadow: GLOW }}>{b}</span>
        {cabeza}
        <span style={{ whiteSpace: "nowrap" }}>
          {cola}
          <span className="bl-cursor" style={{ display: "inline-block", width: ".5em", height: ".72em", background: "currentColor", verticalAlign: "-.04em" }} />
        </span>
      </span>
    </h2>
  );
}

function Lead({ children, ancho = 620 }: { children: React.ReactNode; ancho?: number }) {
  return (
    <p style={{ fontSize: 17, lineHeight: 1.55, maxWidth: ancho, margin: "0 0 40px", color: C.cuerpo, textWrap: "pretty" }}>
      {children}
    </p>
  );
}

/** Botón-píldora blanco sobre azul, con la explosión de recortes al pasar. */
function CtaExplosiva({ etiqueta, poses, transformaciones }: {
  etiqueta: string;
  poses: { src: string; w: number; h: number; delay: string; dur: string }[];
  transformaciones: { activo: string; reposo: string }[];
}) {
  const [on, setOn] = useState(false);
  return (
    <div style={{ position: "relative", zIndex: 5 }}>
      <div style={{ position: "absolute", inset: 0, pointerEvents: "none", zIndex: 6 }}>
        {poses.map((p, i) => (
          <div
            key={i}
            style={{
              position: "absolute", left: "50%", top: "50%", width: p.w, height: p.h,
              transition: `transform ${p.dur} cubic-bezier(.22,1.25,.36,1),opacity .35s`,
              transitionDelay: p.delay,
              transform: on ? transformaciones[i].activo : transformaciones[i].reposo,
              opacity: on ? 1 : 0,
            }}
          >
            <Image src={BASE + p.src} alt="" width={700} height={900} sizes="110px"
              style={{ width: "100%", height: "100%", objectFit: "contain", objectPosition: "bottom center", display: "block" }} />
          </div>
        ))}
      </div>
      <a
        href={DEMO_URL} target="_blank" rel="noopener"
        onMouseEnter={() => setOn(true)} onMouseLeave={() => setOn(false)}
        className="bl-cta"
        style={{
          position: "relative", zIndex: 1, display: "inline-block", fontFamily: MONO,
          fontSize: 13, letterSpacing: ".14em", color: C.azul, background: "#fff",
          border: "1px solid #fff", padding: "16px 32px", borderRadius: 999,
        }}
      >
        {etiqueta}
      </a>
    </div>
  );
}

/** Encabezado de las tarjetas-panel (título display + subtítulo mono + badge). */
function CabezaPanel({ titulo, sub, badge, badgeEstilo }: {
  titulo: string; sub?: string; badge: string; badgeEstilo?: React.CSSProperties;
}) {
  return (
    <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 14, padding: "18px 18px 0" }}>
      <div>
        <div style={{ fontFamily: DISPLAY, fontSize: 21, lineHeight: 1.1 }}>{titulo}</div>
        {sub !== undefined && (
          <div style={{ fontFamily: MONO, fontSize: 11, letterSpacing: ".08em", color: C.mudo, marginTop: 6, minHeight: "1.2em" }}>{sub}</div>
        )}
      </div>
      <span style={{
        flex: "none", fontFamily: MONO, fontSize: 10, letterSpacing: ".12em",
        border: `1px solid ${C.tinta}`, borderRadius: 999, padding: "7px 13px",
        background: "#fff", whiteSpace: "nowrap", ...badgeEstilo,
      }}>{badge}</span>
    </div>
  );
}

/** "$468.900" → 468900. Los precios de la maqueta son texto ya formateado. */
function aPesos(precio: string) {
  return Number(precio.replace(/\D/g, ""));
}

/** Cuadrito con la inicial del proveedor. */
function Inicial({ children }: { children: React.ReactNode }) {
  return (
    <span style={{
      width: 23, height: 23, flex: "none", border: `1px solid ${C.tinta}`, borderRadius: 8,
      background: "#fff", display: "flex", alignItems: "center", justifyContent: "center",
      fontFamily: MONO, fontSize: 11, fontWeight: 700,
    }}>{children}</span>
  );
}

/* ── Página ──────────────────────────────────────────────────────────────── */

export default function LandingContent() {
  const zona = useMirada();
  const f = useFrames(TOTAL_FRAMES, 40);
  const wf = useFrames(ETAPAS.length + 1, 1050);
  const frase = useFraseHero();
  const tipeado = useTitulosTipeados();
  const [abierta, setAbierta] = useState<number | null>(null);

  /* Composer: cuánto lleva escrito el mensaje 3 y si ya está listo para enviar. */
  const escrito = f < INICIO_TIPEO || f >= SENT ? 0 : Math.min(LARGO_BORRADOR, f - INICIO_TIPEO);
  const armado = escrito >= LARGO_BORRADOR;
  const bPre = BORRADOR_PRE.slice(0, escrito);
  const bChip = escrito > BORRADOR_PRE.length ? BORRADOR_CHIP.slice(0, escrito - BORRADOR_PRE.length) : "";
  const bPost = escrito > BORRADOR_PRE.length + BORRADOR_CHIP.length
    ? BORRADOR_POST.slice(0, escrito - BORRADOR_PRE.length - BORRADOR_CHIP.length) : "";

  /* Filas de la RFQ: aparecen, cotizan y —tras el "Sí porfa!"— reciben correo. */
  const filas = PROVEEDORES.map(([name, initial, model, apareceEn, cotizaEn, precio, elegido]) => {
    const visible = f >= apareceEn;
    const cotizado = f >= cotizaEn;
    const conCorreo = elegido && cotizado && f >= SI_PORFA + 10;
    return {
      name, initial, model,
      precio: cotizado ? precio : "—",
      estado: conCorreo ? "Correo consulta despacho enviado" : cotizado ? "Precio obtenido" : "Buscando en web",
      fg: cotizado ? C.tinta : C.mudo,
      precioFg: cotizado ? C.tinta : C.apagado,
      punto: conCorreo ? C.azul : cotizado ? C.verde : C.apagado,
      visible, cotizado,
    };
  });
  // Se compara el valor numérico, no el texto: ordenar "$450.000" como string
  // sólo funciona mientras todos los precios tengan el mismo largo, y agregar
  // uno de otra magnitud daría una "mejor oferta" equivocada sin avisar.
  const cotizadas = filas.filter(v => v.cotizado);
  const mejor = cotizadas.length
    ? cotizadas.reduce((a, b) => (aPesos(a.precio) <= aPesos(b.precio) ? a : b)).precio
    : "—";
  const rfqEnCurso = f >= SENT;

  /* Órdenes de compra: el foco rota y arrastra el borrador de correo. */
  const foco = Math.floor(f / 70) % ORDENES.length;
  const oc = ORDENES[foco];

  return (
    <div className="bl">
      {/* ── Nav fija ── */}
      {/* El layout de la barra vive en `.bl-nav` (globals.css) y no inline: en
          móvil se acuesta, y un estilo inline no lo puede pisar una media query. */}
      <div className="bl-nav">
        <div className="bl-nav-marca">BAiYER</div>
        <nav className="bl-nav-links">
          {[["#producto", "EMPLEADO DIGITAL"], ["#proceso", "CÓMO FUNCIONA"], ["#nosotros", "FAQ"]].map(([href, txt]) => (
            <a key={href} href={href} className="bl-navlink">{txt}</a>
          ))}
        </nav>
      </div>

      {/* ── 1. Hero ── */}
      {/* Igual que la nav, el layout del hero vive en CSS: en móvil cambia de
          "figura al costado, texto centrado a la altura de los ojos" a "texto
          centrado arriba, figura abajo", y eso una media query no lo puede
          hacer contra estilos inline. */}
      <header className="bl-hero">
        <div className="bl-hero-figura">
          <Figura cuerpo="body-headless.png" zona={zona} alt="Baiyer, el empleado digital de compras" proporcion={119.3} prioridad />
        </div>
        <div className="bl-hero-grid">
          <div className="bl-hero-hueco" />
          <div className="bl-hero-copy">
            <h1 className="bl-hero-titulo">
              {/* El h1 cicla tres frases y se escribe en el cliente: sin esta
                  copia la portada no tiene encabezado principal en el HTML.
                  Se fija la primera frase —la que ve todo el mundo al cargar—
                  para que el h1 sea uno solo y estable, no tres rotando. */}
              <span className="bl-solo-lectores">{FRASES[0]}</span>
              <span aria-hidden="true">
                {frase}
                <span className="bl-cursor" style={{ display: "inline-block", width: ".62em", height: ".78em", background: "#fff", marginLeft: ".12em", verticalAlign: "-.06em" }} />
              </span>
            </h1>
            <div className="bl-hero-acciones">
              <CtaExplosiva
                etiqueta="CONVERSEMOS! →"
                poses={[
                  { src: "crt-full.png", w: 96, h: 128, delay: "0s", dur: ".7s" },
                  { src: "crt-full.png", w: 88, h: 118, delay: ".04s", dur: ".75s" },
                  { src: "crt-full.png", w: 104, h: 136, delay: ".08s", dur: ".8s" },
                  { src: "crt-full.png", w: 80, h: 110, delay: ".12s", dur: ".85s" },
                ]}
                transformaciones={[
                  { activo: "translate(-190px,-180px) rotate(-14deg)", reposo: "translate(-48px,-64px) scale(.2)" },
                  { activo: "translate(70px,-200px) rotate(-11deg) scaleX(-1)", reposo: "translate(-44px,-59px) scale(.2) scaleX(-1)" },
                  { activo: "translate(-250px,-30px) rotate(7deg)", reposo: "translate(-52px,-68px) scale(.2)" },
                  { activo: "translate(150px,-40px) rotate(9deg) scaleX(-1)", reposo: "translate(-40px,-55px) scale(.2) scaleX(-1)" },
                ]}
              />
            </div>
          </div>
        </div>
      </header>

      <main id="producto" style={{ ...CONTENEDOR, paddingTop: 110 }}>

        {/* ── 2. Hilo + RFQ en vivo ── */}
        <section style={{ marginBottom: 110 }}>
          <Titulo i={0} n={tipeado[0]} />
          <Lead>Solo un mensaje por Teams, correo o WhatsApp basta para que empiece a trabajar. Mientras conversamos, ya estoy buscando el mejor precio con los mejores proveedores.</Lead>

          <div style={{ display: "flex", flexWrap: "wrap", alignItems: "flex-start", gap: 26 }}>
            {/* Hilo estilo Slack */}
            <div style={{ position: "relative", zIndex: 2, flex: "1 1 460px", minWidth: 300, maxWidth: 500, border: `1px solid ${C.tinta}`, borderRadius: 20, background: "#fff", boxShadow: "0 26px 60px rgba(17,17,17,.10)" }}>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, borderBottom: `1px solid ${C.tinta}`, padding: "14px 18px" }}>
                <div style={{ display: "flex", alignItems: "center", gap: 10, fontFamily: MONO, fontSize: 11, letterSpacing: ".14em" }}>
                  <span style={{ width: 9, height: 9, borderRadius: "50%", background: C.verde, display: "inline-block" }} />
                  <span>HILO EN # abastecimiento-ti</span>
                </div>
                <span style={{ fontFamily: MONO, fontSize: 13, color: C.mudo, letterSpacing: ".1em" }}>···</span>
              </div>

              <div style={{ padding: "14px 16px", display: "flex", flexDirection: "column", gap: 13 }}>
                {MENSAJES.map((m, i) => {
                  const p = PERSONAS[m.quien];
                  const visible = f >= m.at;
                  return (
                    <div key={i} style={{ display: "flex", gap: 12, opacity: visible ? 1 : 0, transform: visible ? "translateY(0)" : "translateY(8px)", transition: "opacity .5s ease,transform .5s cubic-bezier(.22,1,.36,1)" }}>
                      <div style={{ width: 30, height: 30, flex: "none", border: `1px solid ${C.tinta}`, borderRadius: 10, background: p.bg, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 14, overflow: "hidden" }}>
                        {m.quien === "baiyer"
                          ? <Image src={BASE + "av-baiyer.jpeg"} alt="" width={60} height={60} style={{ width: "100%", height: "100%", objectFit: "cover", display: "block" }} />
                          : p.emoji}
                      </div>
                      <div style={{ minWidth: 0 }}>
                        <div style={{ display: "flex", alignItems: "baseline", gap: 8, flexWrap: "wrap" }}>
                          <span style={{ fontSize: 13, fontWeight: 600 }}>{p.name}</span>
                          <span style={{ fontFamily: MONO, fontSize: 10, color: C.mudo }}>{m.time}</span>
                        </div>
                        <div style={{ fontSize: 13.5, lineHeight: 1.45, marginTop: 3, color: C.tinta, textWrap: "pretty" }}>
                          {m.pre}
                          {m.mention && <span style={{ color: C.azul, fontWeight: 600, background: C.azulTinte, borderRadius: 4, padding: "0 3px" }}>{m.mention}</span>}
                          {m.post}
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>

              {/* Composer: el mensaje 3 se escribe acá antes de saltar al hilo */}
              <div style={{ padding: "0 16px 14px" }}>
                <div style={{ border: `1px solid ${C.tinta}`, borderRadius: 16, overflow: "hidden", background: "#FBFAF8" }}>
                  <div style={{ padding: "11px 13px", minHeight: 46, fontSize: 13.5, lineHeight: 1.45, color: C.tinta }}>
                    {bPre}
                    {bChip && <span style={{ color: C.azul, fontWeight: 600, background: C.azulTinte, borderRadius: 5, padding: "1px 5px" }}>{bChip}</span>}
                    {bPost}
                    <span className="bl-cursor" style={{ display: "inline-block", width: 2, height: "1em", background: C.tinta, verticalAlign: "-.14em", marginLeft: 2, opacity: escrito > 0 ? 1 : 0 }} />
                  </div>
                  <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, borderTop: `1px solid ${C.reglaSuave}`, padding: "9px 12px" }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 16, fontFamily: MONO, fontSize: 13, color: C.mudo }}>
                      <span>+</span><span>Aa</span><span>@</span>
                    </div>
                    <span style={{ fontFamily: MONO, fontSize: 11, letterSpacing: ".1em", background: armado ? C.azul : "#fff", color: armado ? "#fff" : C.mudo, border: `1px solid ${C.tinta}`, borderRadius: 999, padding: "8px 16px", transition: "background .3s,color .3s" }}>ENVIAR ↵</span>
                  </div>
                </div>
              </div>
            </div>

            {/* Panel RFQ */}
            <div style={{ position: "relative", flex: "1 1 440px", minWidth: 300, maxWidth: 520, marginTop: 44, paddingRight: "clamp(0px,6vw,74px)" }}>
              <div className="bl-figura-rfq">
                <Figura cuerpo="body-point-left.png" zona={zona} alt="Baiyer señalando la tabla de cotizaciones" proporcion={100} espejada chica />
              </div>
              <div style={{ position: "relative", zIndex: 1, border: `1px solid ${C.tinta}`, borderRadius: 20, background: C.panel }}>
                <CabezaPanel
                  titulo={rfqEnCurso ? "RFQ: MacBook vs ThinkPad (5)" : "Nueva cotización"}
                  sub={rfqEnCurso ? "EVENTO DE ABASTECIMIENTO · EQUIPAMIENTO TI" : ""}
                  badge={rfqEnCurso ? "RFQ EN CURSO" : "EN ESPERA"}
                />
                <div style={{ padding: "18px 18px 16px" }}>
                  <div className="bl-tabla-cab" style={{ display: "grid", gridTemplateColumns: "1fr auto auto", gap: 14, fontFamily: MONO, fontSize: 10, letterSpacing: ".14em", color: C.mudo, paddingBottom: 12, borderBottom: `1px solid ${C.regla}` }}>
                    <span>PROVEEDOR</span><span>ESTADO</span><span style={{ textAlign: "right" }}>COTIZACIÓN</span>
                  </div>
                  {filas.map(v => (
                    <div key={v.name} className="bl-tabla-fila" style={{ display: "grid", gridTemplateColumns: "1fr auto auto", gap: 12, alignItems: "center", padding: "11px 0", borderBottom: `1px solid ${C.regla}`, opacity: v.visible ? 1 : 0, transform: v.visible ? "translateY(0)" : "translateY(6px)", transition: "opacity .5s ease,transform .5s cubic-bezier(.22,1,.36,1)" }}>
                      <div style={{ display: "flex", alignItems: "center", gap: 11, minWidth: 0 }}>
                        <Inicial>{v.initial}</Inicial>
                        <span style={{ minWidth: 0 }}>
                          <span style={{ display: "block", fontSize: 14, fontWeight: 600, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{v.name}</span>
                          <span style={{ display: "block", fontFamily: MONO, fontSize: 10, color: C.mudo, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{v.model}</span>
                        </span>
                      </div>
                      <span style={{ display: "flex", alignItems: "center", gap: 7, fontFamily: MONO, fontSize: 10, letterSpacing: ".04em", lineHeight: 1.3, maxWidth: 170, color: v.fg }}>
                        <span style={{ width: 7, height: 7, borderRadius: "50%", background: v.punto, display: "inline-block", flex: "none" }} />
                        {v.estado}
                      </span>
                      <span style={{ fontFamily: MONO, fontSize: 14, textAlign: "right", minWidth: 84, color: v.precioFg }}>{v.precio}</span>
                    </div>
                  ))}
                  <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 12, paddingTop: 14 }}>
                    <span style={{ fontFamily: MONO, fontSize: 10, letterSpacing: ".14em", color: C.mudo }}>MEJOR OFERTA</span>
                    <span style={{ fontFamily: MONO, fontSize: 19, fontWeight: 700, color: cotizadas.length ? C.azul : C.apagado }}>{mejor}</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* ── 3. Órdenes de compra + borrador de correo ── */}
        <section style={{ marginBottom: 110 }}>
          <Titulo i={1} n={tipeado[1]} />
          <Lead ancho={760}>
            Me contacto con proveedores, cotizo con ellos por correo, busco por internet, selecciono la mejor oferta, solicito autorización interna configurable por ti, hago revisión documental para homologación (creando un perfil de riesgo por proveedor), genero órdenes de compra, hago seguimiento hasta el despacho, reviso las facturas con las OC, y además puedo ejecutar pagos desde tarjetas de débito virtuales.
          </Lead>

          <div style={{ display: "flex", flexWrap: "wrap", alignItems: "stretch", gap: 26 }}>
            <div style={{ flex: "1 1 440px", minWidth: 300, maxWidth: 520, border: `1px solid ${C.tinta}`, borderRadius: 20, background: C.panel, display: "flex", flexDirection: "column" }}>
              <CabezaPanel
                titulo="Órdenes de compra abiertas" sub="DESPACHOS · PLANTA QUILICURA" badge="1 ATRASADA"
                badgeEstilo={{ border: `1px solid ${C.ambar}`, color: C.ambarOscuro, background: C.ambarTinte }}
              />
              <div style={{ padding: 18, display: "flex", flexDirection: "column" }}>
                <div className="bl-tabla-cab" style={{ display: "grid", gridTemplateColumns: "1fr 150px 74px", gap: 12, fontFamily: MONO, fontSize: 10, letterSpacing: ".14em", color: C.mudo, padding: "0 10px 12px", borderBottom: `1px solid ${C.regla}` }}>
                  <span>PROVEEDOR</span><span style={{ textAlign: "right" }}>ESTADO</span><span style={{ textAlign: "right" }}>PROMETIDO</span>
                </div>
                {ORDENES.map((o, i) => (
                  <div key={o.name} className="bl-tabla-fila" style={{ display: "grid", gridTemplateColumns: "1fr 150px 74px", gap: 12, alignItems: "center", padding: "11px 10px", borderBottom: `1px solid ${C.regla}`, borderRadius: 10, background: i === foco ? "#fff" : "transparent", boxShadow: i === foco ? "0 6px 18px rgba(17,17,17,.10)" : "none", transition: "background .45s ease,box-shadow .45s ease" }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 11, minWidth: 0 }}>
                      <Inicial>{o.initial}</Inicial>
                      <span style={{ minWidth: 0 }}>
                        <span style={{ display: "block", fontSize: 14, fontWeight: 600, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{o.name}</span>
                        <span style={{ display: "block", fontFamily: MONO, fontSize: 10, color: C.mudo, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{o.meta}</span>
                      </span>
                    </div>
                    <span style={{ display: "flex", alignItems: "center", justifyContent: "flex-end", gap: 7, fontFamily: MONO, fontSize: 10, letterSpacing: ".04em", textAlign: "right", color: o.fg }}>
                      <span style={{ width: 7, height: 7, borderRadius: "50%", flex: "none", background: o.fg, display: "inline-block" }} />
                      {o.status}
                    </span>
                    <span style={{ fontFamily: MONO, fontSize: 13, textAlign: "right", color: o.late ? C.ambar : C.tinta }}>{o.date}</span>
                  </div>
                ))}
              </div>
            </div>

            <div style={{ position: "relative", zIndex: 2, flex: "1 1 440px", minWidth: 300, maxWidth: 520, border: `1px solid ${C.tinta}`, borderRadius: 20, background: "#fff", boxShadow: "0 26px 60px rgba(17,17,17,.10)", padding: 16, display: "flex", flexDirection: "column" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <span style={{ width: 30, height: 30, flex: "none", border: `1px solid ${C.tinta}`, borderRadius: 10, overflow: "hidden", background: "#1f8b3a" }}>
                  <Image src={BASE + "av-baiyer.jpeg"} alt="" width={60} height={60} style={{ width: "100%", height: "100%", objectFit: "cover", display: "block" }} />
                </span>
                <span style={{ fontSize: 13, fontWeight: 600 }}>Baiyer</span>
                <span style={{ fontFamily: MONO, fontSize: 10, color: C.mudo }}>ahora</span>
                <span style={{ marginLeft: "auto", fontFamily: MONO, fontSize: 9, letterSpacing: ".12em", border: `1px solid ${C.tinta}`, borderRadius: 999, padding: "4px 9px" }}>{oc.stage}</span>
              </div>
              <div style={{ fontSize: 13.5, lineHeight: 1.45, marginTop: 10, minHeight: 60, textWrap: "pretty" }}>{oc.note}</div>
              <div style={{ marginTop: 12, border: `1px solid ${C.tinta}`, borderRadius: 14, overflow: "hidden", background: "#FBFAF8" }}>
                {[["PARA", oc.to, false], ["ASUNTO", oc.subject, true]].map(([k, v, fuerte]) => (
                  <div key={k as string} style={{ display: "flex", gap: 14, padding: "10px 13px", borderBottom: `1px solid ${C.reglaSuave}` }}>
                    <span style={{ fontFamily: MONO, fontSize: 10, letterSpacing: ".12em", color: C.mudo, width: 64, flex: "none" }}>{k as string}</span>
                    <span style={{ fontSize: 13, fontWeight: fuerte ? 600 : 400 }}>{v as string}</span>
                  </div>
                ))}
                <div style={{ padding: "12px 13px", fontSize: 13, lineHeight: 1.5, minHeight: 76, color: C.cuerpo, textWrap: "pretty" }}>{oc.body}</div>
              </div>
              <div style={{ display: "flex", gap: 10, marginTop: 14 }}>
                <div className="bl-pill-azul" style={{ fontFamily: MONO, fontSize: 11, letterSpacing: ".1em", background: C.azul, color: "#fff", border: `1px solid ${C.azul}`, padding: "11px 20px", borderRadius: 999, cursor: "pointer" }}>{oc.cta}</div>
                <div className="bl-pill-linea" style={{ fontFamily: MONO, fontSize: 11, letterSpacing: ".1em", border: `1px solid ${C.tinta}`, padding: "11px 20px", borderRadius: 999, cursor: "pointer" }}>EDITAR BORRADOR</div>
              </div>
            </div>
          </div>
        </section>

        {/* ── 4. Se adapta al proceso + grafo del ciclo de compra ── */}
        <section id="proceso" style={{ marginBottom: 110, scrollMarginTop: 24 }}>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(320px,1fr))", gap: 44, alignItems: "center" }}>
            <div>
              <Titulo i={3} n={tipeado[3]} />
              <p style={{ fontSize: 17, lineHeight: 1.55, maxWidth: 520, margin: 0, color: C.cuerpo, textWrap: "pretty" }}>
                Solo necesitas contarme con tus palabras cómo es el proceso interno de cotizaciones, autorizaciones y compras, y yo me encargo de la comunicación interna con colegas y jefaturas, y externa con proveedores.
              </p>
              <div style={{ position: "relative", width: "min(100%,340px)", margin: "72px auto 0", pointerEvents: "none" }}>
                <Image src={BASE + "body-sitting.png"} alt="Baiyer sentado" width={900} height={601} sizes="340px" style={{ width: "100%", height: "auto", display: "block" }} />
                <Image src={BASE + "head-smile.png"} alt="" width={900} height={753} sizes="125px" style={{ position: "absolute", left: "32%", top: "-22%", width: "36%", height: "auto", display: "block" }} />
              </div>
              <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", justifyContent: "center", gap: "clamp(28px,5vw,56px)", marginTop: 56 }}>
                {[
                  ["logo-gmail.png", "Gmail", 38, 0],
                  ["logo-outlook.webp", "Outlook", 38, 0],
                  ["logo-slack.png", "Slack", 36, 0],
                  ["logo-claude.webp", "Claude", 36, 8],
                  ["logo-openai-dark.webp", "OpenAI", 36, 8],
                ].map(([src, alt, h, r]) => (
                  <Image key={src as string} src={BASE + (src as string)} alt={alt as string} width={200} height={200} sizes="80px"
                    style={{ height: h as number, width: "auto", display: "block", borderRadius: r as number }} />
                ))}
              </div>
              <p style={{ textAlign: "center", fontFamily: MONO, fontSize: 12, letterSpacing: ".1em", color: C.mudo, margin: "18px 0 0" }}>
                ME INTEGRO A LAS PLATAFORMAS QUE TÚ YA USAS
              </p>
            </div>

            {/* Grafo serpenteante: 3 columnas, con las flechas entre celdas */}
            <div>
              <div style={{ border: `1px solid ${C.tinta}`, borderRadius: 22, overflow: "hidden", background: "#fff" }}>
                <div className="bl-grafo" style={{ padding: 18, display: "grid", gridTemplateColumns: "repeat(3,minmax(0,1fr))", gap: 12, background: C.panel }}>
                  {ETAPAS.map((e, i) => {
                    const activo = wf === i, hecho = wf > i;
                    const a = ACTORES[e.actor];
                    const fila = Math.floor(i / 3);
                    const izqDer = fila % 2 === 0;
                    return (
                      <div key={e.label} className="bl-grafo-nodo" style={{
                        gridColumn: izqDer ? (i % 3) + 1 : 3 - (i % 3),
                        gridRow: fila + 1,
                        position: "relative", border: `1px solid ${C.tinta}`, borderRadius: 12,
                        background: activo ? C.azul : "#fff", color: activo ? "#fff" : C.tinta,
                        boxShadow: activo ? "0 12px 26px rgba(16,0,255,.3)" : hecho ? "0 3px 10px rgba(17,17,17,.06)" : "none",
                        padding: "10px 11px",
                        transition: "background .45s cubic-bezier(.22,1,.36,1),color .45s,box-shadow .45s",
                      }}>
                        <div style={{ display: "flex", alignItems: "center", gap: 7 }}>
                          <span style={{ width: 7, height: 7, borderRadius: "50%", flex: "none", background: activo ? "#fff" : hecho ? C.verde : C.apagado }} />
                          <span style={{
                            marginLeft: "auto", minWidth: 0, overflowWrap: "anywhere", fontFamily: MONO,
                            fontSize: 8, letterSpacing: ".1em", borderRadius: 999, padding: "2px 7px",
                            border: `1px solid ${activo ? "rgba(255,255,255,.5)" : a.bd}`,
                            color: activo ? "#fff" : a.fg,
                            background: activo ? "rgba(255,255,255,.16)" : a.bg,
                          }}>{a.t}</span>
                        </div>
                        <div style={{ fontSize: 13, fontWeight: 600, lineHeight: 1.2, marginTop: 6, textWrap: "pretty" }}>{e.label}</div>
                        <div style={{ fontFamily: MONO, fontSize: 9.5, letterSpacing: ".02em", opacity: .62, marginTop: 5, lineHeight: 1.35 }}>{e.role}</div>
                        {e.person && (
                          <div style={{ display: "flex", alignItems: "center", gap: 6, marginTop: 7, fontFamily: MONO, fontSize: 9, letterSpacing: ".04em", opacity: .85 }}>
                            <span style={{ width: 14, height: 14, flex: "none", border: "1px solid currentColor", borderRadius: "50%", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 7 }}>◍</span>
                            {e.person}
                          </div>
                        )}
                        {e.edgeLabel && (
                          <div style={{ marginTop: 7, display: "inline-block", fontFamily: MONO, fontSize: 8, letterSpacing: ".1em", border: `1px solid ${e.edgeColor || C.tinta}`, color: e.edgeColor || C.tinta, background: "#fff", borderRadius: 999, padding: "2px 7px" }}>{e.edgeLabel}</div>
                        )}
                        {i < ETAPAS.length - 1 && (i % 3 === 2
                          ? <span style={{ position: "absolute", bottom: -10, left: "50%", transform: "translateX(-50%)", fontFamily: MONO, fontSize: 12, color: C.mudo, background: C.panel, lineHeight: 1, padding: "0 1px" }}>↓</span>
                          : izqDer
                            ? <span className="bl-flecha-h" style={{ position: "absolute", top: "50%", right: -11, transform: "translateY(-50%)", fontFamily: MONO, fontSize: 12, color: C.mudo, background: C.panel, lineHeight: 1, padding: "0 1px" }}>→</span>
                            : <span className="bl-flecha-h" style={{ position: "absolute", top: "50%", left: -11, transform: "translateY(-50%)", fontFamily: MONO, fontSize: 12, color: C.mudo, background: C.panel, lineHeight: 1, padding: "0 1px" }}>←</span>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* ── 5. Conciliación a tres bandas ── */}
        <section style={{ marginBottom: 110 }}>
          <Titulo i={2} n={tipeado[2]} />
          <Lead>Reviso las facturas, órdenes de compra y recepción, chequeo que todo esté en orden y te aviso si algo no cuadra.</Lead>
          <div style={{ border: `1px solid ${C.tinta}`, borderRadius: 22, overflow: "hidden", background: "#fff" }}>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(240px,1fr))" }}>
              <div style={{ padding: 20, borderRight: `1px solid ${C.reglaSuave}` }}>
                <div style={{ fontFamily: MONO, fontSize: 10, letterSpacing: ".14em", color: C.mudo }}>FACTURA</div>
                <div style={{ fontSize: 26, fontWeight: 700, fontFamily: MONO, marginTop: 10 }}>$389.500</div>
                <div style={{ fontSize: 14, color: C.cuerpo, marginTop: 12, lineHeight: 1.7 }}>40 servidores<br />40 kits de rieles<br />1 instalación</div>
              </div>
              <div style={{ padding: 20, borderRight: `1px solid ${C.reglaSuave}` }}>
                <div style={{ fontFamily: MONO, fontSize: 10, letterSpacing: ".14em", color: C.mudo }}>ORDEN DE COMPRA</div>
                <div style={{ fontSize: 26, fontWeight: 700, fontFamily: MONO, marginTop: 10 }}>$389.500</div>
                <div style={{ fontSize: 14, color: C.cuerpo, marginTop: 12, lineHeight: 1.7 }}>40 servidores<br />40 kits de rieles<br />1 instalación</div>
              </div>
              <div style={{ padding: 20, background: "#FFFBEB" }}>
                <div style={{ fontFamily: MONO, fontSize: 10, letterSpacing: ".14em", color: C.ambarOscuro }}>RECEPCIÓN DE BIENES</div>
                <div style={{ fontSize: 26, fontWeight: 700, fontFamily: MONO, marginTop: 10, color: C.ambarOscuro }}>$363.280</div>
                <div style={{ fontSize: 14, color: C.cuerpo, marginTop: 12, lineHeight: 1.7 }}>
                  <strong style={{ color: C.ambarOscuro }}>37 servidores</strong><br />40 kits de rieles<br />1 instalación
                </div>
              </div>
            </div>
            <div style={{ borderTop: `1px solid ${C.tinta}`, padding: "18px 16px", display: "flex", alignItems: "center", justifyContent: "space-between", gap: 16, flexWrap: "wrap", background: C.ambarTinte }}>
              <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                <span className="bl-alerta" style={{ fontFamily: MONO, fontSize: 10, letterSpacing: ".1em", padding: "6px 12px", borderRadius: 999, border: `1px solid ${C.ambar}`, background: "#fff", color: C.ambarOscuro }}>ALERTA</span>
                <span style={{ fontSize: 15, color: C.cuerpo }}>Faltan 3 unidades respecto a la OC, diferencia de <strong>$26.220</strong>.</span>
              </div>
              <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
                <div className="bl-pill-azul" style={{ fontFamily: MONO, fontSize: 11, letterSpacing: ".1em", background: C.azul, color: "#fff", padding: "12px 22px", borderRadius: 999, cursor: "pointer" }}>PAGAR $363.280</div>
                <div className="bl-pill-linea" style={{ fontFamily: MONO, fontSize: 11, letterSpacing: ".1em", border: `1px solid ${C.tinta}`, background: "#fff", padding: "12px 22px", borderRadius: 999, cursor: "pointer" }}>CONSULTAR A PROVEEDOR</div>
              </div>
            </div>
          </div>
        </section>
      </main>

      {/* ── 6. FAQ ── */}
      <section id="nosotros" style={{ ...CONTENEDOR, paddingTop: 90, scrollMarginTop: 24 }}>
        <Titulo i={4} n={tipeado[4]} tamano="clamp(32px,4.2vw,56px)" />
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(330px,1fr))", gap: "0 48px", borderTop: `1px solid ${C.tinta}`, marginTop: 34 }}>
          {FAQS.map((faq, i) => (
            <div key={faq.q} style={{ borderBottom: `1px solid ${C.tinta}`, padding: "22px 0" }}>
              <button
                onClick={() => setAbierta(abierta === i ? null : i)}
                aria-expanded={abierta === i}
                style={{ all: "unset", cursor: "pointer", display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 16, width: "100%" }}
              >
                <span style={{ fontSize: 17, fontWeight: 600, textWrap: "pretty" }}>{faq.q}</span>
                <span style={{ fontFamily: MONO, fontSize: 18, color: C.azul }}>{abierta === i ? "−" : "+"}</span>
              </button>
              {abierta === i && (
                <p className="bl-faq-abierta" style={{ fontSize: 15, lineHeight: 1.6, color: C.cuerpo, margin: "12px 0 0", maxWidth: "52ch" }}>{faq.a}</p>
              )}
            </div>
          ))}
        </div>
      </section>

      {/* ── 7. Cierre ── */}
      <footer style={{ background: C.azul, color: "#fff", marginTop: 100, padding: "150px 0 28px", minHeight: "100vh", display: "flex", flexDirection: "column" }}>
        <div style={{ maxWidth: 1180, width: "100%", margin: "0 auto", padding: "15vh 24px 0", flex: 1, display: "flex", flexDirection: "column", justifyContent: "center" }}>
          <div style={{ width: "fit-content", maxWidth: "100%", margin: "0 auto" }}>
            <div style={{ position: "relative" }}>
              {/* `bottom` va por clase y no inline: en el teléfono hay que
                  bajar la figura para que se apoye en las letras, y un estilo
                  inline le gana a cualquier media query. */}
              <div className="bl-cierre-figura" style={{ position: "absolute", left: "50%", transform: "translateX(-12%) rotate(-9deg)", pointerEvents: "none", zIndex: 2 }}>
                <Image src={BASE + "body-lying.png"} alt="Baiyer recostado sobre el logotipo" width={900} height={900} sizes="(max-width: 900px) 60vw, 420px" style={{ width: "100%", height: "auto", display: "block" }} />
                <Image src={BASE + "head-tired.png"} alt="" width={900} height={753} sizes="(max-width: 900px) 20vw, 140px" style={{ position: "absolute", left: "2%", top: "16%", width: "33%", height: "auto", display: "block", transform: "rotate(-6deg)" }} />
              </div>
              {/* `font-size` va por clase: el mínimo de 110px del clamp no cabe
                  en un teléfono y desbordaba por la derecha. */}
              <div className="bl-cierre-marca" style={{ fontFamily: DISPLAY, fontWeight: 700, lineHeight: .86, letterSpacing: "-.01em", position: "relative", zIndex: 1, WebkitTextStroke: "2px currentColor", textAlign: "center" }}>BAiYER</div>
            </div>
            {/* `justify-content` va por clase: inline le gana a la media query
                que lo centra en el teléfono. */}
            <div className="bl-cierre-pie" style={{ display: "flex", alignItems: "flex-end", gap: 30, flexWrap: "wrap", marginTop: 40, width: "100%" }}>
              <p style={{ fontSize: 19, lineHeight: 1.5, maxWidth: 520, margin: 0, color: C.lavanda, textWrap: "pretty" }}>Comencemos a trabajar juntos hoy!</p>
              <CtaExplosiva
                etiqueta="AGENDAR DEMO →"
                poses={[
                  { src: "pose-1.png", w: 104, h: 150, delay: "0s", dur: ".7s" },
                  { src: "pose-2.png", w: 96, h: 140, delay: ".05s", dur: ".78s" },
                  { src: "pose-3.png", w: 100, h: 146, delay: ".1s", dur: ".84s" },
                ]}
                transformaciones={[
                  { activo: "translate(-330px,-120px) rotate(-11deg)", reposo: "translate(-52px,-75px) scale(.2)" },
                  { activo: "translate(-190px,-215px) rotate(8deg)", reposo: "translate(-48px,-70px) scale(.2)" },
                  { activo: "translate(-40px,-235px) rotate(-6deg) scaleX(-1)", reposo: "translate(-50px,-73px) scale(.2) scaleX(-1)" },
                ]}
              />
            </div>
          </div>
          <div style={{ display: "flex", justifyContent: "space-between", gap: 16, flexWrap: "wrap", marginTop: "auto", padding: "18px 0 0", borderTop: "1px solid rgba(255,255,255,.28)", fontFamily: MONO, fontSize: 11, letterSpacing: ".14em", color: C.lavandaMuda }}>
            <span>© 2026 BAIYER SPA</span><span>HECHO CON CARIÑO :)</span>
          </div>
        </div>
      </footer>
    </div>
  );
}
