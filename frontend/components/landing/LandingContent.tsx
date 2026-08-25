"use client";
/**
 * Landing pública — rediseño 2026-08-24.
 *
 * Traducción del handoff `design_handoff_baiyer_landing` (prototipo hecho con
 * un runtime propio, `<x-dc>`/`<sc-for>`) a React: se conservan estructura,
 * copy e interacciones.
 *
 * Mezcla deliberada de los dos sistemas: **tipografía Source Serif 4 del
 * handoff** (es lo que le da el aire editorial) sobre la **paleta de la app**
 * (azul petróleo y neutros cálidos) en vez del cian/magenta de Broadsheet, para
 * que landing y producto se reconozcan como lo mismo.
 *
 * **Siempre en claro** (`.tema-claro`): el diseño está pensado sobre papel y en
 * modo oscuro los wordmarks del titular no tenían solución limpia.
 *
 * No se porta el tratamiento CMYK de los titulares: es un efecto de registro de
 * imprenta que sin la paleta de Broadsheet no se lee como tal.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { DEMO_URL, FAQS, FEATURES, INTEGRACIONES } from "./datos";

/** Botón/enlace con el lenguaje de la app, en tamaño landing. */
function CtaPrimary({ href, children, externo }: { href: string; children: React.ReactNode; externo?: boolean }) {
  const estilo: React.CSSProperties = {
    display: "inline-flex", alignItems: "center", justifyContent: "center",
    background: "var(--brand)", color: "#fff", border: "none",
    borderRadius: "var(--r-md)", padding: "12px 22px",
    fontSize: 15, fontWeight: 600, textDecoration: "none", whiteSpace: "nowrap",
  };
  return externo
    ? <a href={href} style={estilo}>{children}</a>
    : <Link href={href} style={estilo}>{children}</Link>;
}

function CtaSecondary({ href, children, externo }: { href: string; children: React.ReactNode; externo?: boolean }) {
  const estilo: React.CSSProperties = {
    display: "inline-flex", alignItems: "center", justifyContent: "center",
    background: "var(--surface)", color: "var(--n-700)",
    border: "1px solid var(--n-300)", borderRadius: "var(--r-md)", padding: "12px 22px",
    fontSize: 15, fontWeight: 600, textDecoration: "none", whiteSpace: "nowrap",
  };
  return externo
    ? <a href={href} style={estilo}>{children}</a>
    : <Link href={href} style={estilo}>{children}</Link>;
}

export default function LandingContent() {
  const [logo, setLogo] = useState(0);
  const [active, setActive] = useState(0);
  const [anim, setAnim] = useState(true);
  const [abierta, setAbierta] = useState<number>(0);

  const seccionRef = useRef<HTMLDivElement | null>(null);
  const videoFeature = useRef<HTMLVideoElement | null>(null);
  const videoHero = useRef<HTMLVideoElement | null>(null);

  // Los logos del titular alternan; sólo uno existe en el DOM a la vez.
  useEffect(() => {
    const t = setInterval(() => setLogo(l => (l === 0 ? 1 : 0)), 6500);
    return () => clearInterval(t);
  }, []);

  // `muted`/`loop` se asignan imperativamente: como atributos planos el
  // navegador puede bloquear el autoplay.
  const prepararVideo = useCallback((el: HTMLVideoElement | null) => {
    if (!el) return;
    el.muted = true;
    el.loop = true;
    void el.play().catch(() => {});
  }, []);

  useEffect(() => { prepararVideo(videoHero.current); }, [prepararVideo]);

  useEffect(() => {
    const el = videoFeature.current;
    if (!el) return;
    el.src = FEATURES[active].video;
    el.load();
    prepararVideo(el);
  }, [active, prepararVideo]);

  // El índice activo se deriva de cuánto se avanzó dentro del bloque alto.
  useEffect(() => {
    let raf = 0;
    const onScroll = () => {
      if (raf) return;
      raf = requestAnimationFrame(() => {
        raf = 0;
        const el = seccionRef.current;
        if (!el) return;
        const recorrido = el.offsetHeight - window.innerHeight;
        if (recorrido <= 0) return;
        const avanzado = Math.min(Math.max(-el.getBoundingClientRect().top, 0), recorrido);
        const idx = Math.min(
          FEATURES.length - 1,
          Math.max(0, Math.floor((avanzado / recorrido) * FEATURES.length)),
        );
        setActive(prev => {
          if (prev === idx) return prev;
          // Reinicia la transición de entrada del texto.
          setAnim(false);
          requestAnimationFrame(() => requestAnimationFrame(() => setAnim(true)));
          return idx;
        });
      });
    };
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll, { passive: true });
    onScroll();
    return () => {
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", onScroll);
      if (raf) cancelAnimationFrame(raf);
    };
  }, []);

  const irAIndice = (i: number) => {
    const el = seccionRef.current;
    if (!el) return;
    const recorrido = el.offsetHeight - window.innerHeight;
    const inicio = window.scrollY + el.getBoundingClientRect().top;
    window.scrollTo({ top: inicio + ((i + 0.5) / FEATURES.length) * recorrido, behavior: "smooth" });
  };

  const f = FEATURES[active];

  return (
    <div
      className="tema-claro"
      style={{
        background: "var(--canvas)", color: "var(--n-900)",
        // Source Serif 4 en toda la landing, como el diseño original. La app
        // por dentro sigue en Inter.
        fontFamily: "var(--font-serif), Georgia, serif",
      }}
    >

      {/* ── Barra de anuncio ── */}
      <div style={{
        background: "var(--n-900)", color: "var(--canvas)", fontSize: 13,
        textAlign: "center", padding: "9px 20px",
      }}>
        Nuevo: agentes de correo que cotizan por ti, de semanas a minutos.{" "}
        <a href={DEMO_URL} style={{ color: "var(--canvas)", textDecoration: "underline", textUnderlineOffset: 3 }}>
          Agenda una demo →
        </a>
      </div>

      {/* ── Nav ── */}
      <nav style={{
        maxWidth: 1180, margin: "0 auto", padding: "16px clamp(20px,5vw,64px)",
        display: "flex", alignItems: "center", gap: 24, flexWrap: "wrap",
      }}>
        <span style={{ fontSize: 20, fontWeight: 600, letterSpacing: "-0.02em", marginRight: "auto" }}>
          Baiyer
        </span>
        <a href="#features" style={{ fontSize: 14, color: "var(--n-600)", textDecoration: "none" }}>Producto</a>
        <a href="#why" style={{ fontSize: 14, color: "var(--n-600)", textDecoration: "none" }}>Por qué</a>
        <a href="#faq" style={{ fontSize: 14, color: "var(--n-600)", textDecoration: "none" }}>Preguntas</a>
        <span style={{ display: "flex", gap: 10 }}>
          <CtaSecondary href="/login">Iniciar sesión</CtaSecondary>
          <CtaPrimary href={DEMO_URL} externo>Probar gratis</CtaPrimary>
        </span>
      </nav>

      <main>
      <div style={{ maxWidth: 1180, margin: "0 auto", padding: "0 clamp(20px,5vw,64px)" }}>

        {/* ── Hero ── */}
        <section style={{
          display: "flex", flexDirection: "column", alignItems: "center",
          gap: "clamp(36px,5vw,60px)", padding: "clamp(48px,7vw,88px) 0 clamp(40px,6vw,72px)",
        }}>
          <div style={{ textAlign: "center", width: "100%" }}>
            <h1 style={{
              fontWeight: 600, fontSize: "clamp(40px,5.4vw,66px)",
              lineHeight: 0.98, letterSpacing: "-0.025em", margin: 0,
            }}>
              <span style={{ display: "block" }}>Tu proceso de compra</span>
              <span style={{ display: "block" }}>completo desde</span>
              <span style={{ position: "relative", display: "block", height: "1.42em", marginTop: "0.1em" }}>
                <span
                  key={logo}
                  style={{
                    position: "absolute", inset: 0, display: "flex",
                    alignItems: "flex-end", justifyContent: "center", paddingBottom: "0.12em",
                    animation: "landingLogoIn .45s ease-out both",
                  }}
                >
                  {/* Los PNG del handoff traían fondo blanco opaco; se les quitó
                      con `scripts/limpiar-logos.mjs`, así que van sueltos sobre el
                      papel, sin chip ni `mix-blend-mode`. */}
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img
                    src={logo === 0 ? "/landing/logo-claude-wordmark.png" : "/landing/logo-chatgpt-wordmark.png"}
                    alt={logo === 0 ? "Claude" : "ChatGPT"}
                    style={{ height: logo === 0 ? "1.2em" : "1.38em", width: "auto", display: "block" }}
                  />
                </span>
              </span>
            </h1>

            <p style={{
              fontSize: 17, lineHeight: 1.6, maxWidth: "54ch", margin: "24px auto 0",
              color: "var(--n-600)",
            }}>
              Baiyer hace el trabajo de cotización y compras por ti: conectas tu cuenta de correo y
              tu IA preferida, y ella se encarga de qué cotizar. Un trabajo de semanas queda en unos
              minutos.
            </p>

            <div style={{
              display: "flex", flexWrap: "wrap", gap: 12, justifyContent: "center",
              alignItems: "center", marginTop: 28,
            }}>
              <CtaPrimary href={DEMO_URL} externo>Agenda una demo</CtaPrimary>
              <CtaSecondary href="#features" externo>Ver la plataforma →</CtaSecondary>
            </div>
          </div>

          <div style={{
            width: "100%", maxWidth: 1120, borderRadius: "var(--r-lg)", overflow: "hidden",
            boxShadow: "var(--shadow-modal)", lineHeight: 0,
          }}>
            <video
              ref={videoHero}
              src="/landing/videos/baiyer-mcp-claude-screen-progressive-chat.mp4"
              autoPlay loop muted playsInline preload="metadata"
              style={{ display: "block", width: "100%", height: "auto" }}
            />
          </div>
        </section>
      </div>

      {/* ── Features: panel pegado + scroll ── */}
      <section
        id="features"
        ref={seccionRef}
        aria-label="Qué hace Baiyer"
        style={{ position: "relative", height: "480vh" }}
      >
        <div style={{
          position: "sticky", top: 0, height: "100vh", display: "flex", flexDirection: "column",
          justifyContent: "center", overflow: "hidden", padding: "clamp(24px,5vh,64px) 0",
        }}>
          <h2 style={{
            fontSize: "clamp(26px,3.2vw,38px)", letterSpacing: "-0.02em", fontWeight: 600,
            margin: "0 auto 12px", maxWidth: "22ch", textAlign: "center", lineHeight: 1.15,
            padding: "0 20px",
          }}>
            Pensado para hacer tu empresa más eficiente
          </h2>

          <div style={{
            display: "flex", flexWrap: "wrap", justifyContent: "center", gap: 8,
            margin: "0 auto clamp(24px,4vh,44px)", padding: "0 20px", maxWidth: 1000,
          }}>
            {FEATURES.map((t, i) => (
              <button
                key={t.name}
                type="button"
                onClick={() => irAIndice(i)}
                style={{
                  cursor: "pointer", fontFamily: "inherit", fontSize: 13.5,
                  fontWeight: i === active ? 600 : 500, whiteSpace: "nowrap",
                  padding: "8px 16px", borderRadius: "var(--r-pill)",
                  border: `1px solid ${i === active ? "var(--brand)" : "var(--n-200)"}`,
                  background: i === active ? "var(--brand)" : "var(--surface)",
                  color: i === active ? "#fff" : "var(--n-500)",
                  transition: "background .2s ease, color .2s ease, border-color .2s ease",
                }}
              >
                {t.name}
              </button>
            ))}
          </div>

          <div style={{ maxWidth: 1120, width: "100%", margin: "0 auto", padding: "0 clamp(16px,4vw,32px)" }}>
            <div style={{
              position: "relative", background: "var(--surface)", border: "1px solid var(--n-200)",
              borderRadius: "var(--r-xl)", boxShadow: "var(--shadow-modal)",
              padding: "clamp(22px,3vw,40px)", display: "flex", flexWrap: "wrap",
              alignItems: "center", gap: "clamp(24px,3vw,40px)",
            }}>
              <div style={{
                flex: "1 1 240px", minWidth: 220,
                opacity: anim ? 1 : 0,
                transform: anim ? "translateY(0)" : "translateY(24px)",
                transition: "opacity .4s ease, transform .4s cubic-bezier(0.22,1,0.36,1)",
              }}>
                <h3 style={{
                  fontSize: "clamp(24px,2.6vw,32px)", lineHeight: 1.1, letterSpacing: "-0.015em",
                  fontWeight: 600, margin: "0 0 16px",
                }}>
                  {f.title}
                </h3>
                <p style={{ fontSize: 16, lineHeight: 1.65, margin: "0 0 28px", maxWidth: "42ch", color: "var(--n-600)" }}>
                  {f.desc}
                </p>
                <div style={{
                  background: "var(--brand-50)", border: "1px solid var(--brand-100)",
                  borderRadius: "var(--r-lg)", padding: "16px 20px",
                }}>
                  <div style={{ fontWeight: 600, fontSize: 15.5, lineHeight: 1.4, color: "var(--brand)" }}>
                    {f.note}
                  </div>
                </div>
              </div>

              <div style={{ flex: "1.6 1 340px", minWidth: 260 }}>
                <div style={{
                  position: "relative", width: "100%", aspectRatio: "16/10", maxHeight: "42vh",
                  borderRadius: "var(--r-lg)", overflow: "hidden", background: "var(--n-100)",
                  border: "1px solid var(--n-200)", boxShadow: "var(--shadow-card)",
                  opacity: anim ? 1 : 0, transition: "opacity .4s ease",
                }}>
                  <video
                    ref={videoFeature}
                    autoPlay loop muted playsInline preload="metadata"
                    style={{ position: "absolute", inset: 0, width: "100%", height: "100%", objectFit: "cover" }}
                  />
                </div>
              </div>
            </div>

            <div style={{
              textAlign: "center", marginTop: "clamp(20px,3vh,34px)", fontSize: 12.5,
              color: "var(--n-500)", display: "flex", alignItems: "center", justifyContent: "center", gap: 8,
            }}>
              <span aria-hidden="true">↕</span>Desplázate para cambiar de tarjeta
            </div>
          </div>
        </div>
      </section>

      <div style={{ maxWidth: 1180, margin: "0 auto", padding: "0 clamp(20px,5vw,64px)" }}>

        {/* ── Bento ── */}
        <section id="why" style={{ padding: "clamp(48px,6vw,80px) 0" }}>
          <h2 style={{
            textAlign: "center", fontSize: "clamp(28px,3.6vw,44px)", letterSpacing: "-0.02em",
            fontWeight: 600, margin: "0 auto clamp(28px,4vw,44px)", maxWidth: "20ch", lineHeight: 1.15,
          }}>
            ¿Por qué Baiyer es la mejor opción?
          </h2>

          <div className="landing-bento">
            {/* Proceso + mock de Gmail */}
            <div style={{
              gridArea: "left", background: "var(--surface)", border: "1px solid var(--n-200)",
              borderRadius: "var(--r-xl)", padding: "clamp(24px,2.4vw,34px)",
              display: "flex", flexDirection: "column",
            }}>
              <h3 style={{ fontSize: "clamp(22px,2.2vw,28px)", lineHeight: 1.15, letterSpacing: "-0.015em", fontWeight: 600, margin: "0 0 14px" }}>
                Nos adaptamos a tu proceso de compra
              </h3>
              <p style={{ fontSize: 15, lineHeight: 1.6, margin: "0 0 24px", color: "var(--n-600)" }}>
                Entendemos tu proceso de compras y autorizaciones, y nuestros agentes de correo hacen
                la comunicación por ti.
              </p>

              {/* Mock de hilo de Gmail — usa Roboto a propósito, para que se lea como Gmail. */}
              <div style={{
                marginTop: "auto", background: "#fff", border: "1px solid var(--n-200)",
                borderRadius: "var(--r-md)", boxShadow: "var(--shadow-card)", overflow: "hidden",
                fontFamily: "var(--font-roboto), Roboto, system-ui, sans-serif", color: "#201e1d",
              }}>
                <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "12px 14px", borderBottom: "1px solid #e6e3dc" }}>
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img src="/landing/logos/gmail.png" alt="" aria-hidden="true" style={{ width: 22, height: 18, objectFit: "contain", flex: "none" }} />
                  <span style={{ fontSize: 13.5, fontWeight: 500, flex: 1, minWidth: 0 }}>Cotización · 20 sacos de cemento</span>
                  <span aria-hidden="true" style={{ color: "#f4b400", fontSize: 15 }}>★</span>
                </div>
                <div style={{ padding: "6px 0" }}>
                  {[
                    { ini: "B", bg: "#1a73e8", nombre: "Agente Baiyer", hora: "10:02", para: "para Proveedor", texto: "Hola, necesitamos cotización por 20 sacos de cemento, entrega en Santiago. ¿Precio y plazo?" },
                    { ini: "P", bg: "#188038", nombre: "Proveedor", hora: "10:41", para: "para mí", texto: "$4.290 c/u, despacho en 48 h. Adjunto cotización formal." },
                  ].map((m, i) => (
                    <div key={m.ini} style={{ display: "flex", gap: 11, padding: "11px 14px", borderTop: i ? "1px solid #f1efea" : "none" }}>
                      <span aria-hidden="true" style={{
                        flex: "none", width: 30, height: 30, borderRadius: "50%", background: m.bg, color: "#fff",
                        display: "inline-flex", alignItems: "center", justifyContent: "center", fontWeight: 500, fontSize: 13,
                      }}>{m.ini}</span>
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div style={{ display: "flex", alignItems: "baseline", gap: 6, marginBottom: 2 }}>
                          <span style={{ fontSize: 12.5, fontWeight: 600 }}>{m.nombre}</span>
                          <span style={{ fontSize: 11, color: "#8a8478", marginLeft: "auto" }}>{m.hora}</span>
                        </div>
                        <div style={{ fontSize: 10.5, color: "#8a8478", marginBottom: 5 }}>{m.para}</div>
                        <p style={{ margin: 0, fontSize: 12.5, lineHeight: 1.5, color: "#45403a" }}>{m.texto}</p>
                      </div>
                    </div>
                  ))}
                </div>
                <div style={{
                  display: "flex", alignItems: "center", gap: 10, margin: "0 14px 14px",
                  background: "var(--brand-50)", border: "1px solid var(--brand-100)",
                  borderRadius: "var(--r-sm)", padding: "9px 12px",
                }}>
                  <span aria-hidden="true" style={{ color: "var(--brand)", fontSize: 14 }}>✓</span>
                  <span style={{ fontSize: 12, lineHeight: 1.4, color: "var(--brand)" }}>
                    Autorización aprobada por <strong>Gerencia</strong> · orden de compra generada
                  </span>
                </div>
              </div>
            </div>

            {/* Integraciones */}
            <div style={{
              gridArea: "black", background: "var(--n-900)", color: "var(--canvas)",
              borderRadius: "var(--r-xl)", padding: "clamp(22px,2.2vw,30px)",
              display: "flex", flexDirection: "column",
            }}>
              <h3 style={{ fontSize: "clamp(20px,1.9vw,25px)", lineHeight: 1.2, letterSpacing: "-0.015em", fontWeight: 600, margin: "0 0 10px" }}>
                Conecta todo en un solo lugar
              </h3>
              <p style={{ fontSize: 13.5, lineHeight: 1.55, margin: "0 0 22px", opacity: 0.72 }}>
                Tus herramientas de IA y correo, integradas de una vez.
              </p>
              <div style={{ marginTop: "auto", display: "flex", flexWrap: "wrap", gap: 12 }}>
                {INTEGRACIONES.map(l => (
                  <span key={l.nombre} title={l.nombre} style={{
                    display: "inline-flex", alignItems: "center", justifyContent: "center",
                    width: 52, height: 52, borderRadius: "var(--r-md)", overflow: "hidden",
                    background: l.bg, boxShadow: "var(--shadow-card)",
                  }}>
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img src={l.src} alt={l.nombre} style={{
                      width: "100%", height: "100%", objectFit: "contain",
                      padding: l.padding, boxSizing: "border-box",
                    }} />
                  </span>
                ))}
              </div>
            </div>

            {/* Homologación */}
            <div style={{
              gridArea: "green", background: "var(--st-cotizando-bg)",
              border: "1px solid rgba(124,92,18,.25)", borderRadius: "var(--r-xl)",
              padding: "clamp(22px,2.2vw,30px)", display: "flex", flexDirection: "column",
            }}>
              <span aria-hidden="true" style={{
                display: "inline-flex", alignItems: "center", justifyContent: "center",
                width: 38, height: 38, borderRadius: "var(--r-sm)", background: "#fff",
                boxShadow: "var(--shadow-card)", color: "var(--st-cotizando-fg)", fontSize: 19, marginBottom: 14,
              }}>⚖</span>
              <h3 style={{ fontSize: "clamp(19px,1.8vw,24px)", lineHeight: 1.2, letterSpacing: "-0.015em", fontWeight: 600, margin: 0, color: "var(--st-cotizando-fg)" }}>
                Homologación y análisis de riesgo inteligente
              </h3>
              <p style={{ fontSize: 13, lineHeight: 1.55, margin: "12px 0 0", color: "var(--st-cotizando-fg)", opacity: 0.85 }}>
                Validamos y calificamos a cada proveedor antes de comprar.
              </p>
            </div>

            {/* Plataforma / inventario */}
            <div style={{
              gridArea: "blue", background: "var(--brand-50)", border: "1px solid var(--brand-100)",
              borderRadius: "var(--r-xl)", padding: "clamp(22px,2.4vw,32px)",
              display: "flex", alignItems: "center", gap: "clamp(20px,3vw,40px)", flexWrap: "wrap",
            }}>
              <div style={{ flex: "1 1 300px", minWidth: 260 }}>
                <h3 style={{ fontSize: "clamp(20px,2vw,27px)", lineHeight: 1.2, letterSpacing: "-0.015em", fontWeight: 600, margin: 0, color: "var(--brand)" }}>
                  Una plataforma automatizada con toda la información de tu inventario y proveedores
                </h3>
                <p style={{ fontSize: 13.5, lineHeight: 1.55, margin: "14px 0 0", color: "var(--n-600)" }}>
                  Inventario, historial y proveedores, todo consultable en un mismo panel.
                </p>
              </div>
              <div style={{
                flex: "1 1 240px", minWidth: 220, background: "var(--surface)",
                border: "1px solid var(--n-200)", borderRadius: "var(--r-md)",
                boxShadow: "var(--shadow-card)", padding: "14px 16px",
              }}>
                <div style={{ fontSize: 12.5, fontWeight: 600, color: "var(--brand)", marginBottom: 8 }}>
                  Panel · Inventario
                </div>
                {[
                  ["Proveedores activos", "128"],
                  ["SKU en catálogo", "3.410"],
                  ["Cotizaciones este mes", "42"],
                ].map(([k, v]) => (
                  <div key={k} style={{
                    display: "flex", justifyContent: "space-between", fontSize: 12.5,
                    padding: "7px 0", borderTop: "1px solid var(--n-100)",
                  }}>
                    <span style={{ color: "var(--n-600)" }}>{k}</span>
                    <span className="mono" style={{ fontWeight: 600 }}>{v}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </section>

        {/* ── CTA final ── */}
        <section style={{ textAlign: "center", padding: "clamp(56px,7vw,96px) 0" }}>
          <h2 style={{
            fontWeight: 600, fontSize: "clamp(32px,4.4vw,52px)", lineHeight: 1.05,
            letterSpacing: "-0.02em", margin: 0,
          }}>
            De semanas a minutos,<br />al mejor precio.
          </h2>
          <p style={{ fontSize: 16, lineHeight: 1.6, maxWidth: "44ch", margin: "22px auto 0", color: "var(--n-600)" }}>
            Deja que los agentes de correo hagan el ida y vuelta con tus proveedores. Tú apruebas.
          </p>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 12, justifyContent: "center", marginTop: 28 }}>
            <CtaPrimary href={DEMO_URL} externo>Comienza a cotizar</CtaPrimary>
            <CtaSecondary href="/register">Probar en el navegador</CtaSecondary>
          </div>
        </section>

        {/* ── FAQ ── */}
        <section id="faq" style={{ padding: "clamp(48px,6vw,80px) 0" }}>
          <div style={{ fontSize: 13, fontWeight: 500, color: "var(--brand)", marginBottom: 10 }}>
            Preguntas frecuentes
          </div>
          <h2 style={{ fontSize: "clamp(28px,3.4vw,40px)", letterSpacing: "-0.02em", fontWeight: 600, margin: "0 0 24px" }}>
            Lo que suelen preguntar
          </h2>
          <div style={{ maxWidth: 820 }}>
            {FAQS.map((item, i) => {
              const open = abierta === i;
              return (
                <div key={item.q} style={{ borderTop: "1px solid var(--n-200)" }}>
                  <button
                    type="button"
                    onClick={() => setAbierta(open ? -1 : i)}
                    aria-expanded={open}
                    style={{
                      width: "100%", display: "flex", justifyContent: "space-between", alignItems: "center",
                      gap: 16, background: "none", border: 0, padding: "18px 0", cursor: "pointer",
                      textAlign: "left", fontFamily: "inherit", fontWeight: 600, fontSize: 18,
                      color: open ? "var(--brand)" : "var(--n-900)",
                    }}
                  >
                    <span>{item.q}</span>
                    <span aria-hidden="true" style={{
                      flex: "none", fontSize: 24, lineHeight: 1, color: "var(--brand)",
                      transition: "transform .3s ease", transform: `rotate(${open ? 45 : 0}deg)`,
                    }}>+</span>
                  </button>
                  <div style={{
                    overflow: "hidden", transition: "max-height .35s ease, opacity .3s ease",
                    maxHeight: open ? 320 : 0, opacity: open ? 1 : 0,
                  }}>
                    <p style={{ margin: "0 0 18px", fontSize: 15, lineHeight: 1.65, maxWidth: "68ch", color: "var(--n-600)" }}>
                      {item.a}
                    </p>
                  </div>
                </div>
              );
            })}
          </div>
        </section>
      </div>
      </main>

      {/* ── Footer ── */}
      <footer style={{ borderTop: "1px solid var(--n-200)" }}>
        <div style={{
          maxWidth: 1180, margin: "0 auto", padding: "40px clamp(20px,5vw,64px)",
          display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(160px,1fr))", gap: 28,
        }}>
          <div>
            <div style={{ fontSize: 20, fontWeight: 600, letterSpacing: "-0.02em", marginBottom: 8 }}>Baiyer</div>
            <p style={{ fontSize: 13, lineHeight: 1.5, margin: 0, color: "var(--n-500)" }}>
              Agentic procurement para Chile. Compras y proveedores, automatizados con IA.
            </p>
          </div>
          {[
            { titulo: "Producto", links: [["Cómo funciona", "#features"], ["Por qué Baiyer", "#why"], ["Preguntas", "#faq"]] },
            { titulo: "Empresa", links: [["Iniciar sesión", "/login"], ["Contacto", "mailto:j.gonzalez.plc@gmail.com"], ["Agenda una demo", DEMO_URL]] },
            // El handoff trae una columna "Legal" con Privacidad y Términos, pero
            // esas páginas no existen: enlazarlas daría 404. Se reponen cuando se
            // escriban — los pilotos empresa las van a pedir.
          ].map(col => (
            <div key={col.titulo}>
              <div style={{ fontSize: 13, fontWeight: 600, color: "var(--n-500)", marginBottom: 12 }}>{col.titulo}</div>
              <div style={{ display: "flex", flexDirection: "column", gap: 8, fontSize: 13.5 }}>
                {col.links.map(([txt, href]) => (
                  <a key={txt} href={href} style={{ color: "var(--n-700)", textDecoration: "none" }}>{txt}</a>
                ))}
              </div>
            </div>
          ))}
        </div>
        <div style={{
          maxWidth: 1180, margin: "0 auto", padding: "16px clamp(20px,5vw,64px) 40px",
          fontSize: 12, color: "var(--n-500)",
        }}>
          © 2026 Baiyer · Santiago de Chile
        </div>
      </footer>
    </div>
  );
}
