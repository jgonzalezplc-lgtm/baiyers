"use client";

import Image from "next/image";

/**
 * Cuerpo recortado con las cinco cabezas apiladas en el cuello. Sólo una está
 * opaca a la vez: la elige `zona`, que sale de la posición del puntero. El
 * cross-fade es de opacidad y no de `display` para que la transición exista.
 */
export type Zona = "up" | "left" | "front" | "down" | "right";

/** Offsets por cabeza, calibrados contra el recorte de cada PNG. */
const CABEZAS: { zona: Zona; src: string; left: string; top: string; width: string }[] = [
  { zona: "right", src: "head-right.png", left: "30%", top: "-33%", width: "66%" },
  { zona: "down", src: "head-down.png", left: "28%", top: "-34%", width: "68%" },
  { zona: "front", src: "head-front.png", left: "33%", top: "-36%", width: "60%" },
  { zona: "left", src: "head-left.png", left: "26%", top: "-35%", width: "66%" },
  { zona: "up", src: "head-up.png", left: "29%", top: "-35%", width: "64%" },
];

/** La figura chica que apunta a la tabla usa el mismo set, reencuadrado. */
const CABEZAS_CHICAS: typeof CABEZAS = [
  { zona: "right", src: "head-right.png", left: "36%", top: "-17%", width: "36%" },
  { zona: "down", src: "head-down.png", left: "35%", top: "-18%", width: "37%" },
  { zona: "front", src: "head-front.png", left: "38%", top: "-19%", width: "32%" },
  { zona: "left", src: "head-left.png", left: "34%", top: "-18%", width: "36%" },
  { zona: "up", src: "head-up.png", left: "36%", top: "-18%", width: "34%" },
];

const BASE = "/landing/baiyer/";

export default function Figura({
  cuerpo,
  zona,
  alt,
  proporcion,
  espejada = false,
  chica = false,
  prioridad = false,
}: {
  cuerpo: string;
  zona: Zona;
  alt: string;
  /** alto/ancho del cuerpo, en %, para reservar el espacio antes de cargar. */
  proporcion: number;
  espejada?: boolean;
  chica?: boolean;
  prioridad?: boolean;
}) {
  // Sin `sizes`, Next pide el candidato más grande del srcset (1920px) y sirve
  // un upscale de originales de 900px: peso de más por píxeles inventados.
  const sizes = chica ? "210px" : "(max-width: 900px) 55vw, 560px";
  const cabezas = chica ? CABEZAS_CHICAS : CABEZAS;
  return (
    <div style={{ position: "relative", width: "100%", paddingBottom: `${proporcion}%` }}>
      <Image
        src={BASE + cuerpo}
        alt={alt}
        width={900}
        height={900}
        priority={prioridad}
        sizes={sizes}
        style={{ position: "absolute", left: 0, bottom: 0, width: "100%", height: "auto", display: "block" }}
      />
      {cabezas.map(c => (
        <Image
          key={c.src}
          src={BASE + c.src}
          alt=""
          width={900}
          height={900}
          priority={prioridad}
          sizes={sizes}
          style={{
            position: "absolute",
            left: c.left,
            top: c.top,
            width: c.width,
            height: "auto",
            display: "block",
            opacity: zona === c.zona ? 1 : 0,
            transition: "opacity .3s ease",
            transformOrigin: "50% 100%",
            transform: espejada ? "scaleX(-1)" : undefined,
          }}
        />
      ))}
    </div>
  );
}
