"use client";
import { useState, useEffect } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Sparkles } from "lucide-react";
import { createClient } from "@/lib/supabase/client";
import FormularioCotizar from "./components/FormularioCotizar";
import ResultadoIdentificacion from "./components/ResultadoIdentificacion";
import ResultadoIdentificacionMulti, { type ItemIdentificado } from "./components/ResultadoIdentificacionMulti";

type Etapa = "formulario" | "procesando" | "aclaracion" | "revision_bloqueada" | "resultado" | "guardado";

interface ResultadoIA {
  nombre_tecnico: string;
  marca: string | null;
  numero_parte: string | null;
  categoria: string;
  terminos_busqueda_es: string[];
  terminos_busqueda_en: string[];
  confianza: "alto" | "medio" | "bajo";
  estado_flujo?: "requiere_datos" | "listo" | "requiere_revision";
  mensaje?: string | null;
  preguntas?: PreguntaCubicacion[];
  datos_confirmados?: Record<string, string | number | boolean>;
  revision_cubicacion?: RevisionCubicacion;
  bloquea_publicacion?: boolean;
  // true si el usuario describió un proyecto y la IA generó la lista de materiales
  es_proyecto?: boolean;
  nombre_lista_sugerido?: string | null;
  // El LLM separa la intención de compra en ítems (con cantidad detectada)
  lista_items?: {
    nombre_tecnico: string;
    marca: string | null;
    numero_parte: string | null;
    categoria: string;
    cantidad?: number;
    unidad?: string;
    cantidad_neta?: number;
    unidad_compra?: string;
    cantidad_comercial?: number;
    calculo?: string;
    supuestos?: string[];
    advertencias?: string[];
    terminos_busqueda_es: string[];
    terminos_busqueda_en: string[];
  }[];
}

interface PreguntaCubicacion { id: string; texto: string; tipo: "numero" | "texto" | "booleano"; unidad?: string; permite_no_se?: boolean; es_supuesto?: boolean }
interface RevisionCubicacion { receta: string; items: Array<{ nombre_tecnico: string; cantidad_neta: number; unidad: string; cantidad_compra: number; unidad_compra: string; cantidad_comercial: number; calculo: string }>; supuestos: string[]; advertencias: string[]; resumen?: Record<string, unknown> }

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// Saludo según la hora: "este día" (mañana) · "esta tarde" · "esta noche"
const momentoDelDia = (): string => {
  const h = new Date().getHours();
  if (h < 12) return "este día";
  if (h < 20) return "esta tarde";
  return "esta noche";
};

export default function CotizarPage() {
  const [etapa, setEtapa] = useState<Etapa>("formulario");
  const [resultado, setResultado] = useState<ResultadoIA | null>(null);
  // Multi-ítem: el LLM separó la compra en varios ítems → lista de cotización
  const [resultadosMulti, setResultadosMulti] = useState<ItemIdentificado[] | null>(null);
  const [nombreListaSugerido, setNombreListaSugerido] = useState("");
  const [esProyecto, setEsProyecto] = useState(false);
  const [error, setError] = useState("");
  const [guardando, setGuardando] = useState(false);
  const [userId, setUserId] = useState<string | null>(null);
  const [industriaEmpresa, setIndustriaEmpresa] = useState<string | null>(null);
  const [nombreUsuario, setNombreUsuario] = useState<string | null>(null);
  const [lastDescripcion, setLastDescripcion] = useState("");
  const [respuestasCubicacion, setRespuestasCubicacion] = useState<Record<string, string | number | boolean>>({});
  const [preguntasCubicacion, setPreguntasCubicacion] = useState<PreguntaCubicacion[]>([]);
  const [mensajeCubicacion, setMensajeCubicacion] = useState("");
  const [revisionCubicacion, setRevisionCubicacion] = useState<RevisionCubicacion | null>(null);
  const router = useRouter();

  useEffect(() => {
    const supabase = createClient();
    supabase.auth.getUser().then(({ data }) => {
      setUserId(data.user?.id ?? null);
      setIndustriaEmpresa((data.user?.user_metadata?.industria as string) ?? null);
      const nombre = (data.user?.user_metadata?.nombre_usuario as string) ?? "";
      setNombreUsuario(nombre ? nombre.split(/\s+/)[0] : null);
    });
  }, []);

  const identificarUno = async (descripcion: string, imagenBase64: string | null = null, imagenMime = "image/jpeg", respuestas: Record<string, string | number | boolean> = {}): Promise<ResultadoIA> => {
    const body: Record<string, unknown> = { modo_cubicacion_conversacional: true, respuestas_cubicacion: respuestas };
    if (descripcion) body.descripcion = descripcion;
    if (industriaEmpresa) body.industria_empresa = industriaEmpresa;
    if (imagenBase64) { body.imagen_base64 = imagenBase64; body.imagen_mime = imagenMime; }
    const res = await fetch(`${API_URL}/api/identificar`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!res.ok) { const d = await res.json(); throw new Error(d.detail ?? "Error al identificar"); }
    return res.json();
  };

  const handleIdentificar = async (descripcion: string, imagenBase64: string | null, imagenMime: string) => {
    setError("");
    setEtapa("procesando");
    setLastDescripcion(descripcion);
    setRespuestasCubicacion({});
    setRevisionCubicacion(null);
    setResultadosMulti(null);
    try {
      // Una sola llamada al LLM: entiende la intención de compra completa y
      // separa los ítems solo ("3 martillos y un taladro" → 2 ítems, cantidades 3 y 1)
      const data = await identificarUno(descripcion, imagenBase64, imagenMime);
      if (data.estado_flujo === "requiere_datos") {
        setMensajeCubicacion(data.mensaje ?? "Necesito algunos datos para calcular las cantidades.");
        setPreguntasCubicacion(data.preguntas ?? []);
        setRespuestasCubicacion(data.datos_confirmados ?? {});
        setEtapa("aclaracion");
        return;
      }
      aplicarResultado(data);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Error desconocido");
      setEtapa("formulario");
    }
  };

  const aplicarResultado = (data: ResultadoIA) => {
      setRevisionCubicacion(data.revision_cubicacion ?? null);
      if (data.estado_flujo === "requiere_revision" || data.bloquea_publicacion) {
        setMensajeCubicacion(data.mensaje ?? "Este cálculo necesita revisión especializada.");
        setEtapa("revision_bloqueada");
        return;
      }
      const items = data.lista_items ?? [];
      if (items.length > 1 || (items.length === 1 && data.revision_cubicacion)) {
        setNombreListaSugerido(data.nombre_lista_sugerido ?? "");
        setEsProyecto(data.es_proyecto ?? false);
        setResultadosMulti(items.map(li => ({
          nombre_tecnico: li.nombre_tecnico,
          marca: li.marca ?? null,
          numero_parte: li.numero_parte ?? null,
          categoria: li.categoria,
          cantidad: li.cantidad ?? 1,
          terminos_busqueda_es: li.terminos_busqueda_es ?? [],
          terminos_busqueda_en: li.terminos_busqueda_en ?? [],
          confianza: data.confianza,
          cubicacion: (() => {
            const detalle = data.revision_cubicacion?.items.find(ri => ri.nombre_tecnico === li.nombre_tecnico);
            return detalle ? { ...detalle, supuestos: data.revision_cubicacion?.supuestos ?? [], advertencias: data.revision_cubicacion?.advertencias ?? [] } : undefined;
          })(),
        })));
        setEtapa("resultado");
        return;
      }
      setResultado(data);
      setEtapa("resultado");
  };

  const handleResponderCubicacion = async () => {
    if (preguntasCubicacion.some(p => respuestasCubicacion[p.id] === undefined || respuestasCubicacion[p.id] === "")) return;
    setError("");
    setEtapa("procesando");
    try {
      const data = await identificarUno(
        lastDescripcion,
        null,
        "image/jpeg",
        respuestasCubicacion,
      );
      if (data.estado_flujo === "requiere_datos") {
        const preguntas = data.preguntas ?? [];
        setMensajeCubicacion(data.mensaje ?? "Me falta confirmar algunos datos.");
        setPreguntasCubicacion(preguntas);
        setRespuestasCubicacion(data.datos_confirmados ?? respuestasCubicacion);
        setEtapa("aclaracion");
        return;
      }
      aplicarResultado(data);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Error desconocido");
      setEtapa("aclaracion");
    }
  };

  // Confirmación multi-ítem: crea N cotizaciones + la lista, y parte por el 1er ítem
  const handleConfirmarMulti = async (categoriasPorItem: string[][], nombreLista: string, cantidades: number[], itemsFinales: ItemIdentificado[]) => {
    if (!userId) {
      setError("Debes iniciar sesión para crear una lista de cotización.");
      return;
    }
    setGuardando(true);
    try {
      const supabase = createClient();
      const itemsSel = itemsFinales;

      const inserts = await Promise.all(itemsSel.map((it, i) =>
        supabase.from("cotizaciones").insert({
          user_id: userId,
          descripcion: lastDescripcion || null,
          nombre_identificado: it.nombre_tecnico,
          marca: it.marca,
          numero_parte: it.numero_parte,
          categoria: categoriasPorItem[i]?.[0] ?? it.categoria,
          terminos_busqueda_es: it.terminos_busqueda_es,
          terminos_busqueda_en: it.terminos_busqueda_en,
          estado: "identificado",
          confianza_ia: it.confianza,
        }).select("id").single()
      ));
      const ids = inserts.map(r => r.data?.id).filter(Boolean) as string[];
      if (ids.length !== itemsSel.length) throw new Error("No se pudieron guardar todos los ítems");

      const res = await fetch(`${API_URL}/api/listas`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          user_id: userId,
          nombre: nombreLista || `Lista ${new Date().toLocaleDateString("es-CL")}`,
          items: itemsSel.map((it, i) => ({
            cotizacion_id: ids[i],
            nombre: it.nombre_tecnico,
            // cantidad: la editada en la confirmación (parte de la detectada por la IA)
            cantidad: cantidades[i] ?? it.cantidad ?? 1,
          })),
        }),
      });
      if (!res.ok) throw new Error("No se pudo crear la lista");
      const lista = await res.json();

      // La lista creada es el punto de control antes de elegir la estrategia
      // de proveedores. Desde ahí el usuario abre la matriz explícitamente.
      router.push(`/listas/${lista.id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Error creando la lista");
      setGuardando(false);
    }
  };

  const handleConfirmar = async (categorias: string[], nombreLista: string) => {
    if (!resultado) return;
    const extra = new URLSearchParams();
    if (categorias.length) extra.set("cats", categorias.join(","));
    if (nombreLista) extra.set("lista", nombreLista);

    if (!userId) {
      const p = new URLSearchParams({
        nombre: resultado.nombre_tecnico,
        es: resultado.terminos_busqueda_es.join(","),
        en: resultado.terminos_busqueda_en.join(","),
      });
      if (categorias.length) p.set("cats", categorias.join(","));
      if (nombreLista) p.set("lista", nombreLista);
      router.push(`/cotizar/demo/resultados?${p.toString()}`);
      return;
    }
    setGuardando(true);
    const supabase = createClient();
    const { data: cotizacion, error: dbError } = await supabase
      .from("cotizaciones")
      .insert({
        user_id: userId,
        descripcion: lastDescripcion || null,
        nombre_identificado: resultado.nombre_tecnico,
        marca: resultado.marca,
        numero_parte: resultado.numero_parte,
        categoria: categorias[0] ?? resultado.categoria,
        terminos_busqueda_es: resultado.terminos_busqueda_es,
        terminos_busqueda_en: resultado.terminos_busqueda_en,
        estado: "identificado",
        confianza_ia: resultado.confianza,
      })
      .select("id")
      .single();
    if (dbError || !cotizacion) {
      setGuardando(false);
      setError("Error guardando en base de datos: " + (dbError?.message ?? "sin datos"));
      return;
    }

    // Un solo ítem es, igual que varios, una "lista de cotización" (de 1 ítem):
    // así todo el flujo — comparador, definitivo, aprobación — es el mismo sin
    // importar cuántos ítems tenga la compra.
    try {
      const resLista = await fetch(`${API_URL}/api/listas`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          user_id: userId,
          nombre: nombreLista || resultado.nombre_tecnico,
          items: [{ cotizacion_id: cotizacion.id, nombre: resultado.nombre_tecnico, cantidad: 1 }],
        }),
      });
      if (resLista.ok) {
        const lista = await resLista.json();
        router.push(`/listas/${lista.id}`);
        return;
      }
    } catch { /* si falla, sigue como cotización suelta (se envuelve al abrirla) */ }

    setGuardando(false);
    const qs = extra.toString();
    router.push(`/cotizar/${cotizacion.id}/resultados${qs ? `?${qs}` : ""}`);
  };

  const handleCorregir = () => { setEtapa("formulario"); setError(""); };

  // ── Procesando ──────────────────────────────────────────────────────────────
  if (etapa === "procesando") {
    return <PantallaProcesando />;
  }

  if (etapa === "aclaracion") {
    return (
      <div style={{ maxWidth: 720, margin: "48px auto", padding: "0 20px" }}>
        <div style={{ marginBottom: 24 }}>
          <span className="label">CUBICACIÓN DEL PROYECTO</span>
          <h1 style={{ fontSize: 28, color: "var(--n-900)", margin: "12px 0 8px" }}>Completemos las medidas</h1>
          <p style={{ color: "var(--n-600)", fontSize: 14, lineHeight: 1.6, margin: 0 }}>{mensajeCubicacion}</p>
        </div>

        <div style={{ background: "var(--surface)", border: "1px solid var(--n-200)", borderRadius: "var(--r-lg)", padding: 20, marginBottom: 16 }}>
          <div style={{ display: "grid", gap: 16 }}>
            {preguntasCubicacion.map((pregunta) => (
              <label key={pregunta.id} style={{ display: "grid", gap: 7, fontSize: 14, color: "var(--n-900)" }}>
                <span>{pregunta.texto}</span>
                <div style={{ display: "flex", gap: 8 }}>
                  <input type="text" inputMode={pregunta.tipo === "numero" ? "decimal" : "text"} value={respuestasCubicacion[pregunta.id] === "no_se" ? "" : String(respuestasCubicacion[pregunta.id] ?? "")} placeholder={respuestasCubicacion[pregunta.id] === "no_se" ? "Marcado: No lo sé" : pregunta.tipo === "booleano" ? "Escribe sí o no" : "Escribe tu respuesta"} onChange={e => setRespuestasCubicacion(r => ({ ...r, [pregunta.id]: e.target.value }))} style={{ flex: 1, padding: 10, border: "1px solid var(--n-300)", background: "var(--surface)", color: "var(--n-900)", font: "inherit" }} />
                  {pregunta.unidad && <span style={{ alignSelf: "center", color: "var(--n-600)" }}>{pregunta.unidad}</span>}
                  {pregunta.permite_no_se && <button type="button" className="btn-swiss-secondary" onClick={() => setRespuestasCubicacion(r => ({ ...r, [pregunta.id]: "no_se" }))}>No lo sé</button>}
                </div>
              </label>
            ))}
          </div>
        </div>

        {error && <div style={{ color: "var(--danger)", fontSize: 13, marginBottom: 12 }}>{error}</div>}
        <div style={{ display: "flex", gap: 10, justifyContent: "flex-end" }}>
          <button
            onClick={handleResponderCubicacion}
            disabled={preguntasCubicacion.some(p => respuestasCubicacion[p.id] === undefined || respuestasCubicacion[p.id] === "")}
            className="btn-swiss-primary"
            style={{ height: 44, display: "inline-flex", alignItems: "center", gap: 7 }}
          >
            Continuar
          </button>
        </div>

        {Object.keys(respuestasCubicacion).length > 0 && (
          <div style={{ marginTop: 20, borderTop: "1px solid var(--n-200)", paddingTop: 14 }}>
            <div className="label" style={{ marginBottom: 8 }}>DATOS CONFIRMADOS · PUEDES EDITARLOS</div>
            <div style={{ display: "flex", gap: 7, flexWrap: "wrap" }}>
              {Object.entries(respuestasCubicacion).map(([id, valor]) => (
                <button key={id} type="button" onClick={() => setRespuestasCubicacion(r => { const n = { ...r }; delete n[id]; return n; })} className="btn-swiss-secondary" title="Quitar para volver a responder">
                  {id.replaceAll("_", " ")}: {String(valor)} ×
                </button>
              ))}
            </div>
          </div>
        )}
        <button onClick={handleCorregir} style={{ border: 0, background: "transparent", color: "var(--n-500)", marginTop: 16, cursor: "pointer" }}>
          ← Cambiar descripción inicial
        </button>
      </div>
    );
  }

  if (etapa === "revision_bloqueada") {
    return (
      <div style={{ maxWidth: 720, margin: "48px auto", padding: "0 20px" }}>
        <span className="label">REQUIERE REVISIÓN TÉCNICA</span>
        <h1 style={{ fontSize: 27, margin: "12px 0 8px" }}>No publicaremos esta lista todavía</h1>
        <p style={{ color: "var(--n-600)", lineHeight: 1.6 }}>{mensajeCubicacion}</p>
        {revisionCubicacion?.resumen && <pre style={{ whiteSpace: "pre-wrap", background: "var(--surface)", border: "1px solid var(--n-200)", padding: 16, fontSize: 12 }}>{JSON.stringify(revisionCubicacion.resumen, null, 2)}</pre>}
        {revisionCubicacion?.advertencias.map(a => <div key={a} style={{ borderLeft: "3px solid var(--danger)", padding: "8px 12px", marginTop: 10, fontSize: 13 }}>{a}</div>)}
        <button className="btn-swiss-secondary" onClick={handleCorregir} style={{ marginTop: 20 }}>Editar datos iniciales</button>
      </div>
    );
  }

  // ── Guardado ────────────────────────────────────────────────────────────────
  if (etapa === "guardado") {
    return (
      <div style={{ display: "flex", alignItems: "center", justifyContent: "center", padding: "60px 20px" }}>
        <div style={{ maxWidth: 440, textAlign: "center" }}>
          <div className="section-rule" style={{ margin: "0 auto 24px" }} />
          <h2 style={{ fontSize: 18, fontWeight: 700, color: "var(--text-primary)", marginBottom: 8 }}>
            {userId ? "Cotizacion guardada" : "Item identificado"}
          </h2>
          <p style={{ fontSize: 12, color: "var(--text-secondary)", marginBottom: 28, lineHeight: 1.6 }}>
            {userId
              ? "La cotizacion fue guardada en tu cuenta."
              : "Item identificado correctamente. Crea una cuenta para guardar tus cotizaciones."}
          </p>
          <div style={{ display: "flex", gap: 10, justifyContent: "center", flexWrap: "wrap" }}>
            <button
              onClick={() => { setEtapa("formulario"); setResultado(null); setError(""); }}
              className="btn-swiss-secondary"
            >
              Nueva cotizacion
            </button>
            {userId
              ? <Link href="/dashboard" className="btn-swiss-primary" style={{ textDecoration: "none" }}>Ir al dashboard</Link>
              : <Link href="/register" className="btn-swiss-primary" style={{ textDecoration: "none" }}>Crear cuenta gratis</Link>
            }
          </div>
        </div>
      </div>
    );
  }

  // ── Formulario (composer centrado estilo Claude) ─────────────────────────────
  if (etapa === "formulario") {
    return (
      <div style={{
        minHeight: "calc(100vh - 120px)",
        display: "flex", flexDirection: "column",
        alignItems: "center", justifyContent: "center",
        padding: "40px 20px",
      }}>
        <div style={{ width: "100%", maxWidth: 720 }}>
          {/* Hero centrado */}
          <div style={{ textAlign: "center", marginBottom: 28 }}>
            <h1 style={{
              display: "flex", alignItems: "center", justifyContent: "center", gap: 12,
              fontSize: 34, lineHeight: 1.15, fontWeight: 600, color: "var(--n-900)",
              margin: "0 0 10px", letterSpacing: "-0.02em",
            }}>
              <Sparkles size={28} strokeWidth={1.5} style={{ color: "var(--brand)", flexShrink: 0 }} />
              {`¿Qué quieres cotizar ${momentoDelDia()}${nombreUsuario ? `, ${nombreUsuario}` : ""}?`}
            </h1>
            <p style={{ fontSize: 15, color: "var(--n-600)", margin: 0, lineHeight: 1.6 }}>
              Busca un ítem o material específico, o describe un proyecto completo, la IA arma la lista y cotiza todo.
            </p>
          </div>

          {/* Error */}
          {error && (
            <div style={{
              background: "var(--fill-error)", border: "1px solid var(--danger)",
              padding: "10px 14px", borderRadius: "var(--r-md)",
              fontSize: 13, color: "var(--danger)", marginBottom: 16, textAlign: "center",
            }}>
              {error}
            </div>
          )}

          <FormularioCotizar
            onSubmit={handleIdentificar}
            loading={false}
            initialDescripcion={lastDescripcion}
          />
        </div>
      </div>
    );
  }

  // ── Resultado ────────────────────────────────────────────────────────────────
  return (
    <div style={{ maxWidth: 720, margin: "0 auto" }}>

      {/* Page header (solo ítem único; la lista multi trae su propio título editable) */}
      {!resultadosMulti && (
        <div style={{ marginBottom: 28, textAlign: "center" }}>
          <h1 style={{ fontSize: 26, fontWeight: 600, color: "var(--n-900)", margin: "0 0 6px", letterSpacing: "-0.015em" }}>
            Ítem identificado
          </h1>
          <p style={{ fontSize: 14, color: "var(--n-600)", margin: 0 }}>
            Revisa la identificación. Puedes confirmar o corregir.
          </p>
        </div>
      )}

      {/* Error */}
      {error && (
        <div style={{
          background: "var(--fill-error)",
          border: "1px solid var(--danger)",
          padding: "10px 14px",
          borderRadius: "var(--r-md)",
          fontSize: 13,
          color: "var(--danger)",
          marginBottom: 20,
        }}>
          {error}
        </div>
      )}

      {etapa === "resultado" && resultadosMulti && (
        <ResultadoIdentificacionMulti
          items={resultadosMulti}
          onConfirmar={handleConfirmarMulti}
          onCorregir={handleCorregir}
          guardando={guardando}
          nombreListaInicial={nombreListaSugerido}
          esProyecto={esProyecto}
        />
      )}

      {etapa === "resultado" && !resultadosMulti && resultado && (
        <ResultadoIdentificacion
          resultado={resultado}
          onConfirmar={handleConfirmar}
          onCorregir={handleCorregir}
          guardando={guardando}
          isLoggedIn={!!userId}
        />
      )}
    </div>
  );
}

// ── Pantalla de carga animada mientras la IA identifica ─────────────────────
const PASOS_IA = [
  "Analizando tu descripción",
  "Identificando los ítems",
  "Detectando cantidades",
  "Generando términos de búsqueda",
];

function PantallaProcesando() {
  const [paso, setPaso] = useState(0);
  useEffect(() => {
    const t = setInterval(() => setPaso(p => (p + 1) % PASOS_IA.length), 1600);
    return () => clearInterval(t);
  }, []);

  return (
    <div style={{
      minHeight: "calc(100vh - 120px)",
      display: "flex", alignItems: "center", justifyContent: "center", padding: "40px 20px",
    }}>
      <div style={{ textAlign: "center", maxWidth: 360 }}>
        {/* Ícono con halo pulsante */}
        <div style={{ position: "relative", width: 64, height: 64, margin: "0 auto 24px" }}>
          <span style={{
            position: "absolute", inset: 0, borderRadius: "50%",
            background: "var(--brand-100)", animation: "haloPulse 1.8s ease-out infinite",
          }} />
          <span style={{
            position: "relative", width: 64, height: 64, borderRadius: "50%",
            background: "var(--brand-50)", color: "var(--brand)",
            display: "inline-flex", alignItems: "center", justifyContent: "center",
            animation: "breathe 2.4s ease-in-out infinite",
          }}>
            <Sparkles size={30} strokeWidth={1.5} />
          </span>
        </div>

        <div style={{ fontSize: 20, fontWeight: 600, color: "var(--n-900)", marginBottom: 8, letterSpacing: "-0.015em" }}>
          Identificando con IA
        </div>

        {/* Mensaje rotativo */}
        <div key={paso} style={{
          fontSize: 14, color: "var(--n-600)", marginBottom: 24, minHeight: 22,
          animation: "fadeUp .35s ease",
        }}>
          {PASOS_IA[paso]}…
        </div>

        {/* Puntos en onda */}
        <div style={{ display: "flex", gap: 7, justifyContent: "center" }}>
          {[0, 1, 2].map(i => (
            <span key={i} style={{
              width: 8, height: 8, borderRadius: "50%", background: "var(--brand)",
              animation: `dotWave 1.3s ease-in-out ${i * 0.16}s infinite`,
            }} />
          ))}
        </div>
      </div>
    </div>
  );
}
