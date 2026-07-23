"use client";
import { useState, useEffect } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { createClient } from "@/lib/supabase/client";
import FormularioCotizar from "./components/FormularioCotizar";
import ResultadoIdentificacion from "./components/ResultadoIdentificacion";
import ResultadoIdentificacionMulti, { type ItemIdentificado } from "./components/ResultadoIdentificacionMulti";

type Etapa = "formulario" | "procesando" | "resultado" | "guardado";

interface ResultadoIA {
  nombre_tecnico: string;
  marca: string | null;
  numero_parte: string | null;
  categoria: string;
  terminos_busqueda_es: string[];
  terminos_busqueda_en: string[];
  confianza: "alto" | "medio" | "bajo";
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
    terminos_busqueda_es: string[];
    terminos_busqueda_en: string[];
  }[];
}

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

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
  const [lastDescripcion, setLastDescripcion] = useState("");
  const router = useRouter();

  useEffect(() => {
    const supabase = createClient();
    supabase.auth.getUser().then(({ data }) => {
      setUserId(data.user?.id ?? null);
      setIndustriaEmpresa((data.user?.user_metadata?.industria as string) ?? null);
    });
  }, []);

  const identificarUno = async (descripcion: string, imagenBase64: string | null = null, imagenMime = "image/jpeg"): Promise<ResultadoIA> => {
    const body: Record<string, string> = {};
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
    setResultadosMulti(null);
    try {
      // Una sola llamada al LLM: entiende la intención de compra completa y
      // separa los ítems solo ("3 martillos y un taladro" → 2 ítems, cantidades 3 y 1)
      const data = await identificarUno(descripcion, imagenBase64, imagenMime);
      const items = data.lista_items ?? [];
      if (items.length > 1) {
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
        })));
        setEtapa("resultado");
        return;
      }
      setResultado(data);
      setEtapa("resultado");
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Error desconocido");
      setEtapa("formulario");
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

      // Lanza las búsquedas de los ítems 2..N en background AHORA: cuando el
      // usuario llegue a cada uno, sus resultados ya estarán precargados en la BD.
      if (ids.length > 1) {
        fetch(`${API_URL}/api/buscar/prefetch`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ cotizacion_ids: ids.slice(1), user_id: userId }),
          keepalive: true,
        }).catch(() => {});
      }

      const p = new URLSearchParams();
      if (categoriasPorItem[0]?.length) p.set("cats", categoriasPorItem[0].join(","));
      p.set("lista", lista.id);
      router.push(`/cotizar/${ids[0]}/resultados?${p.toString()}`);
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
    setGuardando(false);
    if (dbError || !cotizacion) {
      setError("Error guardando en base de datos: " + (dbError?.message ?? "sin datos"));
      return;
    }
    const qs = extra.toString();
    router.push(`/cotizar/${cotizacion.id}/resultados${qs ? `?${qs}` : ""}`);
  };

  const handleCorregir = () => { setEtapa("formulario"); setError(""); };

  // ── Procesando ──────────────────────────────────────────────────────────────
  if (etapa === "procesando") {
    return (
      <div style={{ display: "flex", alignItems: "center", justifyContent: "center", padding: "60px 20px" }}>
        <div style={{ textAlign: "center", maxWidth: 320 }}>
          <div className="section-rule" style={{ margin: "0 auto 24px" }} />
          <div style={{ fontSize: 13, fontWeight: 700, color: "var(--text-primary)", marginBottom: 8, letterSpacing: "-0.01em" }}>
            Identificando con IA
          </div>
          <div style={{ fontSize: 11, color: "var(--text-muted)", marginBottom: 28, lineHeight: 1.6 }}>
            Analizando imagen y descripcion · Generando terminos de busqueda
          </div>
          <div style={{ display: "flex", gap: 6, justifyContent: "center" }}>
            {[0, 1, 2].map(i => (
              <div key={i} style={{
                width: 6, height: 6,
                background: "var(--accent)",
                opacity: 0.3 + i * 0.35,
              }} />
            ))}
          </div>
        </div>
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

  // ── Formulario / Resultado ───────────────────────────────────────────────────
  return (
    <div style={{ maxWidth: 640 }}>

      {/* Page header */}
      <div style={{ marginBottom: 28 }}>
        <div className="section-rule" style={{ marginBottom: 16 }} />
        <span style={{ fontSize: 10, fontWeight: 700, color: "var(--text-muted)", letterSpacing: "0.06em", display: "block", marginBottom: 6 }}>
          COTIZADOR INTELIGENTE
        </span>
        <h1 style={{ fontSize: 26, fontWeight: 700, color: "var(--text-primary)", margin: "0 0 6px", letterSpacing: "-0.02em" }}>
          {etapa === "resultado"
            ? (resultadosMulti ? `${resultadosMulti.length} ítems identificados` : "Item identificado")
            : "¿Qué quieres comprar hoy?"}
        </h1>
        <p style={{ fontSize: 12, color: "var(--text-secondary)", margin: 0 }}>
          {etapa === "resultado"
            ? "Revisa la identificacion. Puedes confirmar o corregir."
            : "Cuéntalo con tus palabras — la IA entiende qué ítems necesitas, cuántos, y lanza la cotización de todos."}
        </p>
      </div>

      {/* Error */}
      {error && (
        <div style={{
          background: "var(--fill-error)",
          border: "1px solid var(--border-accent)",
          padding: "10px 14px",
          fontSize: 11,
          color: "var(--text-error)",
          marginBottom: 20,
        }}>
          {error}
        </div>
      )}

      {etapa === "formulario" && (
        <FormularioCotizar
          onSubmit={handleIdentificar}
          loading={false}
          initialDescripcion={lastDescripcion}
        />
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
