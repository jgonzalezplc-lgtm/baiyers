"use client";

import { useCallback, useRef, useState, type CSSProperties, type ReactNode, type RefObject } from "react";
import { Minus, Plus } from "lucide-react";

export interface CanvasViewport { scale: number; translateX: number; translateY: number }

export const VIEWPORT_MIN_SCALE = 0.5;
export const VIEWPORT_MAX_SCALE = 1.75;
export const VIEWPORT_STEP = 0.1;

export const VIEWPORT_DEFAULT: CanvasViewport = { scale: 1, translateX: 0, translateY: 0 };

// Convierte coordenadas de pantalla a coordenadas del "mundo" (las mismas
// que se persisten como posición de cada tarjeta) dado el viewport actual.
// La composición del transform es `translate(tx,ty) scale(s)`, por lo que
// screenX = tx + s*worldX  =>  worldX = (screenX - tx) / s.
export function screenToWorld(clientX: number, clientY: number, rect: DOMRect, viewport: CanvasViewport) {
  return {
    x: (clientX - rect.left - viewport.translateX) / viewport.scale,
    y: (clientY - rect.top - viewport.translateY) / viewport.scale,
  };
}

export function WorkflowCanvasViewport({
  viewport, onViewportChange, lienzoRef, onBackgroundMouseMove, onBackgroundMouseUp, children, topRight, style,
}: {
  viewport: CanvasViewport;
  onViewportChange: (v: CanvasViewport) => void;
  lienzoRef: RefObject<HTMLDivElement>;
  onBackgroundMouseMove?: (e: React.MouseEvent) => void;
  onBackgroundMouseUp?: (e: React.MouseEvent) => void;
  children: ReactNode;
  topRight?: ReactNode;
  style?: CSSProperties;
}) {
  const panRef = useRef<{ x: number; y: number } | null>(null);
  const [panning, setPanning] = useState(false);

  const zoomAt = useCallback((clientX: number, clientY: number, nextScaleRaw: number) => {
    const rect = lienzoRef.current?.getBoundingClientRect();
    if (!rect) return;
    const nextScale = Math.min(VIEWPORT_MAX_SCALE, Math.max(VIEWPORT_MIN_SCALE, Math.round(nextScaleRaw * 100) / 100));
    const world = screenToWorld(clientX, clientY, rect, viewport);
    onViewportChange({
      scale: nextScale,
      translateX: clientX - rect.left - world.x * nextScale,
      translateY: clientY - rect.top - world.y * nextScale,
    });
  }, [viewport, onViewportChange, lienzoRef]);

  const zoomButton = (delta: number) => {
    const rect = lienzoRef.current?.getBoundingClientRect();
    if (!rect) return;
    zoomAt(rect.left + rect.width / 2, rect.top + rect.height / 2, viewport.scale + delta);
  };

  const reset = () => onViewportChange(VIEWPORT_DEFAULT);

  const onWheel = (e: React.WheelEvent) => {
    if (!(e.ctrlKey || e.metaKey)) return;
    e.preventDefault();
    zoomAt(e.clientX, e.clientY, viewport.scale + (e.deltaY > 0 ? -VIEWPORT_STEP : VIEWPORT_STEP));
  };

  // Solo empieza a panear si el mousedown llega hasta este contenedor sin
  // que algo intermedio (una tarjeta, un botón de conexión) haya llamado
  // stopPropagation — así paneo y drag de tarjetas nunca compiten.
  const onMouseDownBg = (e: React.MouseEvent) => {
    if (e.button !== 0) return;
    panRef.current = { x: e.clientX - viewport.translateX, y: e.clientY - viewport.translateY };
    setPanning(true);
  };
  const onMouseMove = (e: React.MouseEvent) => {
    if (panRef.current) {
      onViewportChange({ ...viewport, translateX: e.clientX - panRef.current.x, translateY: e.clientY - panRef.current.y });
      return;
    }
    onBackgroundMouseMove?.(e);
  };
  const stopPan = (e: React.MouseEvent) => {
    panRef.current = null;
    setPanning(false);
    onBackgroundMouseUp?.(e);
  };

  return (
    <div
      ref={lienzoRef}
      onMouseDown={onMouseDownBg}
      onMouseMove={onMouseMove}
      onMouseUp={stopPan}
      onMouseLeave={stopPan}
      onWheel={onWheel}
      style={{
        position: "relative", flex: 1, minHeight: 480, background: "var(--canvas)",
        border: "1px solid var(--n-200)", borderRadius: "var(--r-md)", overflow: "hidden",
        backgroundImage: "radial-gradient(var(--n-200) 1px, transparent 1px)",
        backgroundSize: `${16 * viewport.scale}px ${16 * viewport.scale}px`,
        backgroundPosition: `${viewport.translateX}px ${viewport.translateY}px`,
        cursor: panning ? "grabbing" : "default",
        ...style,
      }}
    >
      <div
        style={{
          position: "absolute", inset: 0, transformOrigin: "0 0",
          transform: `translate(${viewport.translateX}px, ${viewport.translateY}px) scale(${viewport.scale})`,
        }}
      >
        {children}
      </div>

      {topRight && <div style={{ position: "absolute", top: 10, right: 10, zIndex: 5 }}>{topRight}</div>}

      <div
        style={{
          position: "absolute", left: 10, bottom: 10, zIndex: 5, display: "flex", alignItems: "center", gap: 4,
          background: "var(--surface)", border: "1px solid var(--n-200)", borderRadius: "var(--r-md)",
          padding: 4, boxShadow: "var(--shadow-card)",
        }}
      >
        <button aria-label="Alejar" title="Alejar" onClick={() => zoomButton(-VIEWPORT_STEP)} style={zoomBtnStyle}>
          <Minus size={13} />
        </button>
        <button
          aria-label="Restablecer vista al 100%"
          title="Restablecer vista"
          onClick={reset}
          style={{ ...zoomBtnStyle, width: 46, fontSize: 11, fontWeight: 600 }}
        >
          {Math.round(viewport.scale * 100)}%
        </button>
        <button aria-label="Acercar" title="Acercar" onClick={() => zoomButton(VIEWPORT_STEP)} style={zoomBtnStyle}>
          <Plus size={13} />
        </button>
      </div>
    </div>
  );
}

const zoomBtnStyle: CSSProperties = {
  width: 26, height: 26, display: "inline-flex", alignItems: "center", justifyContent: "center",
  border: "1px solid var(--n-200)", background: "var(--surface)", color: "var(--n-700)",
  borderRadius: "var(--r-sm)", cursor: "pointer",
};
