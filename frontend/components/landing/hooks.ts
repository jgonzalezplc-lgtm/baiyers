"use client";

import { useEffect, useRef, useState } from "react";
import { FRASES, TITULOS } from "./datos";
import type { Zona } from "./Figura";

/** `true` si el visitante pidió menos movimiento; apaga todos los relojes. */
function prefiereQuietud() {
  return typeof window !== "undefined"
    && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

/**
 * Reloj único de la maqueta del hilo + RFQ: un contador de frames que da la
 * vuelta. Las tarjetas tienen alto fijo desde el primer frame; la animación
 * sólo las va llenando, así que el layout nunca salta.
 */
export function useFrames(total: number, ms: number) {
  const [f, setF] = useState(0);
  useEffect(() => {
    if (prefiereQuietud()) { setF(total - 1); return; }

    // El reloj re-renderiza toda la landing 25 veces por segundo. Si la pestaña
    // queda abierta de fondo eso es CPU quemada para nadie, así que se corta
    // mientras el documento está oculto y se retoma al volver.
    let id: ReturnType<typeof setInterval> | null = null;
    const arrancar = () => {
      if (id === null) id = setInterval(() => setF(x => (x + 1) % total), ms);
    };
    const parar = () => {
      if (id !== null) { clearInterval(id); id = null; }
    };
    const alCambiarVisibilidad = () => (document.hidden ? parar() : arrancar());

    if (!document.hidden) arrancar();
    document.addEventListener("visibilitychange", alCambiarVisibilidad);
    return () => {
      parar();
      document.removeEventListener("visibilitychange", alCambiarVisibilidad);
    };
  }, [total, ms]);
  return f;
}

/**
 * Titular del hero: escribe una frase, la deja 4s y pasa a la siguiente.
 *
 * Un timer por render en vez de un bucle que se auto-agenda: encadenar
 * `setTimeout` desde dentro de un updater de `setState` rompe con StrictMode,
 * que invoca los updaters dos veces y deja timers huérfanos.
 */
export function useFraseHero() {
  const [i, setI] = useState(0);
  const [n, setN] = useState(0);

  useEffect(() => {
    if (prefiereQuietud()) { setN(FRASES[0].length); return; }
    if (n < FRASES[i].length) {
      const t = setTimeout(() => setN(n + 1), 52);
      return () => clearTimeout(t);
    }
    const t = setTimeout(() => { setI(x => (x + 1) % FRASES.length); setN(0); }, 4000);
    return () => clearTimeout(t);
  }, [i, n]);

  return FRASES[i].slice(0, n);
}

/**
 * Tipeo de los títulos de sección al entrar en pantalla. Devuelve cuántos
 * caracteres mostrar de cada uno y el `ref` que hay que colgar del `<h2>`.
 *
 * Un título que ya quedó por encima del viewport (recarga a media página) se
 * completa de golpe: tipearlo fuera de cuadro no lo vería nadie.
 */
export function useTitulosTipeados() {
  const [n, setN] = useState<number[]>(() => TITULOS.map(() => 0));
  /** Índices que ya entraron en pantalla y por lo tanto están escribiéndose. */
  const activos = useRef(new Set<number>());

  useEffect(() => {
    const total = (i: number) => TITULOS[i].join("").length;
    if (prefiereQuietud()) { setN(TITULOS.map((_, i) => total(i))); return; }

    const io = new IntersectionObserver(entradas => {
      entradas.forEach(e => {
        const i = Number((e.target as HTMLElement).dataset.ttl);
        // Ojo con el `unobserve`: sólo se deja de mirar el título cuando ya se
        // decidió algo sobre él. El observer dispara una llamada inicial por
        // CADA elemento apenas arranca —incluidos los que están más abajo, con
        // `isIntersecting: false`—, así que un `unobserve` incondicional acá
        // los desengancha antes de que el usuario llegue y no se escriben nunca.
        if (e.isIntersecting) {
          io.unobserve(e.target);
          activos.current.add(i);
        } else if (e.boundingClientRect.bottom < 0) {
          // Quedó por encima del viewport (recarga a media página): se completa
          // de golpe, tipearlo fuera de cuadro no lo vería nadie.
          io.unobserve(e.target);
          setN(prev => { const s = prev.slice(); s[i] = total(i); return s; });
        }
      });
    }, { threshold: 0.2 });
    // Los títulos se buscan por `data-ttl` en vez de por `ref`: el reloj de la
    // maqueta re-renderiza 25 veces por segundo y cada render reengancha los
    // refs, así que un array de refs es una fuente de sustos innecesaria.
    document.querySelectorAll<HTMLElement>("[data-ttl]").forEach(el => io.observe(el));

    // Un solo reloj avanza todos los títulos activos: encadenar timers desde
    // dentro de un updater de `setState` no sobrevive al doble render de
    // StrictMode y deja títulos a medio escribir.
    const reloj = setInterval(() => {
      if (!activos.current.size) return;
      setN(prev => {
        const s = prev.slice();
        activos.current.forEach(i => {
          if (s[i] < total(i)) s[i] += 1;
          else activos.current.delete(i);
        });
        return s;
      });
    }, 26);

    return () => { io.disconnect(); clearInterval(reloj); };
  }, []);

  return n;
}

/**
 * Zona a la que mira el empleado digital, derivada de la posición del puntero
 * en la ventana. Con puntero grueso (táctil) no hay `mousemove`: se queda
 * mirando al frente y no se registra el listener.
 */
export function useMirada(): Zona {
  const [zona, setZona] = useState<Zona>("right");
  useEffect(() => {
    if (window.matchMedia("(pointer: coarse)").matches) { setZona("front"); return; }
    const mover = (e: MouseEvent) => {
      const fx = e.clientX / window.innerWidth;
      const fy = e.clientY / window.innerHeight;
      let z: Zona;
      if (fy < 0.5) z = fx <= 0.3 ? "up" : "right";
      else if (fx <= 0.11) z = "left";
      else if (fx <= 0.3) z = "front";
      else z = "down";
      setZona(prev => (prev === z ? prev : z));
    };
    window.addEventListener("mousemove", mover, { passive: true });
    return () => window.removeEventListener("mousemove", mover);
  }, []);
  return zona;
}
