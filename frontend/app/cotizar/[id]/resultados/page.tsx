"use client";
import { useState, useEffect } from "react";
import { useParams, useSearchParams, useRouter } from "next/navigation";
import Link from "next/link";
import dynamic from "next/dynamic";
import { createClient } from "@/lib/supabase/client";
import FiltrosProveedores from "../../components/FiltrosProveedores";
import CardProveedor, { type Resultado } from "../../components/CardProveedor";
import SkeletonResultados from "../../components/SkeletonResultados";
import EmailPreviewModal from "@/components/EmailPreviewModal";
import HistorialPrecioModal from "@/components/HistorialPrecioModal";

const OCModal = dynamic(() => import("@/components/OCModal"), { ssr: false });

type FiltroPrecio = "todos" | "con_precio" | "sin_precio";
type FiltroPais = "todos" | "chile" | "internacional";
type Orden = "relevancia" | "precio_asc" | "precio_desc";

interface Destinatario {
  _uid?: string;
  nombre: string;
  url: string;
  email: string;
  resultado_id?: string;
}

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// Etiquetas de fuente para los chips cuando se cargan resultados precargados
const FUENTE_CHIP: Record<string, string> = {
  google: "Google", mercadolibre: "MercadoLibre", alibaba: "Alibaba",
  mouser: "Mouser", digikey: "DigiKey", tme: "TME", manual: "Manual",
  sodimac: "Sodimac", easy: "Easy", lasierra: "La Sierra", construmart: "Construmart",
  vitel: "Vitel", dartel: "Dartel", ferrelectrica: "Ferrelectrica", gobantes: "Gobantes", rhona: "Rhona",
  clcsa: "CLC Maderas", wmaderas: "W Maderas", ferramenta: "Ferramenta", maderas_dir: "Aserraderos CL",
};

interface GrupoResultado {
  principal: Resultado;       // oferta con menor precio del grupo
  ofertas: Resultado[];       // todas las ofertas del grupo (incluye principal), ordenadas por precio
}

function normalizarTexto(s: string): string {
  return s
    .toLowerCase()
    .normalize("NFD").replace(/[̀-ͯ]/g, "")
    .replace(/[^a-z0-9\s]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function claveProducto(r: Resultado): string {
  if (r.numero_parte) {
    return "pn:" + r.numero_parte.toUpperCase().replace(/[^A-Z0-9]/g, "");
  }
  const palabras = normalizarTexto(r.titulo)
    .split(" ")
    .filter(w => w.length > 2)
    .sort();
  return "t:" + palabras.slice(0, 6).join("-");
}

// ── Filtro de relevancia ──────────────────────────────────────────────────────
// Descarta accesorios ("broca para taladro" cuando busco taladro) y resultados
// que no mencionan ninguna palabra clave del ítem. Usa TODAS las palabras
// significativas (no solo la primera) para tolerar sinónimos cortos como "TV".
const STOPWORDS = new Set(["para", "con", "del", "los", "las", "por", "una", "uno", "the", "and", "for", "kit", "set", "de", "en", "al", "el", "la"]);

function stemPalabra(w: string): string {
  if (w.length > 4 && w.endsWith("es")) return w.slice(0, -2);
  if (w.length > 3 && w.endsWith("s")) return w.slice(0, -1);
  return w;
}

function matchStem(a: string, b: string): boolean {
  return a === b || (a.length > 3 && b.startsWith(a)) || (b.length > 3 && a.startsWith(b));
}

function esRelevanteParaItem(titulo: string, nombreItem: string): boolean {
  if (!nombreItem || !titulo) return true;
  const toks = normalizarTexto(nombreItem).split(" ").filter(w => w.length > 1 && !STOPWORDS.has(w));
  if (!toks.length) return true;
  const palabras = normalizarTexto(titulo).split(" ");
  const stems = palabras.map(stemPalabra);
  const matches = toks.filter(tok => {
    const st = stemPalabra(tok);
    return stems.some(s => matchStem(s, st));
  });
  // Exigir al menos 2 palabras cuando el nombre tiene 3+, sino al menos 1
  const minimo = toks.length >= 3 ? 2 : 1;
  if (matches.length < minimo) return false;
  // Accesorio: "X para <ítem>"
  for (let j = 0; j < palabras.length; j++) {
    if (palabras[j] !== "para") continue;
    const despues = stems.slice(j + 1);
    if (toks.some(tok => despues.some(s => matchStem(s, stemPalabra(tok))))) return false;
  }
  return true;
}

// ── Marcas locales de progreso de lista ──────────────────────────────────────
// Los POST de "comparado" corren en background; el estado del servidor puede ir
// atrasado al navegar rápido entre ítems. sessionStorage guarda la verdad local
// de la sesión para que el "siguiente pendiente" nunca se calcule con datos viejos.
function comparadosLocales(listaId: string): Set<string> {
  try {
    return new Set<string>(JSON.parse(sessionStorage.getItem(`lista_comparados_${listaId}`) ?? "[]"));
  } catch {
    return new Set<string>();
  }
}

function marcarComparadoLocal(listaId: string, cotizacionId: string) {
  try {
    const s = comparadosLocales(listaId);
    s.add(cotizacionId);
    sessionStorage.setItem(`lista_comparados_${listaId}`, JSON.stringify(Array.from(s)));
  } catch { /* storage no disponible */ }
}

function agruparPorProducto(lista: Resultado[]): GrupoResultado[] {
  const map = new Map<string, Resultado[]>();
  for (const r of lista) {
    const key = claveProducto(r);
    const arr = map.get(key);
    if (arr) arr.push(r); else map.set(key, [r]);
  }
  const grupos: GrupoResultado[] = [];
  for (const items of Array.from(map.values())) {
    const ordenado = [...items].sort((a, b) => {
      if (a.precio == null) return 1;
      if (b.precio == null) return -1;
      return a.precio - b.precio;
    });
    grupos.push({ principal: ordenado[0], ofertas: ordenado });
  }
  return grupos;
}

export default function ResultadosPage() {
  const params = useParams();
  const searchParams = useSearchParams();
  const router = useRouter();
  const id = params.id as string;
  const [creandoLista, setCreandoLista] = useState(false);

  const [resultados, setResultados] = useState<Resultado[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [nombreItem, setNombreItem] = useState("");
  const [descripcionItem, setDescripcionItem] = useState("");
  const [seleccionados, setSeleccionados] = useState<Set<string>>(new Set());
  const [toast, setToast] = useState("");
  const [userId, setUserId] = useState<string | null>(null);
  const [userEmail, setUserEmail] = useState("");
  const [plan, setPlan] = useState("free");
  const [tasas, setTasas] = useState<Record<string, number>>({});

  const [filtroPrecio, setFiltroPrecio] = useState<FiltroPrecio>("todos");
  const [filtroPais, setFiltroPais] = useState<FiltroPais>("todos");
  const [orden, setOrden] = useState<Orden>("relevancia");
  const [soloRelevantes, setSoloRelevantes] = useState(true);
  const [comparando, setComparando] = useState(false);

  // Resultados cargados desde la BD (prefetch de lista) en vez de búsqueda en vivo
  const [precargado, setPrecargado] = useState(false);

  // Agregar proveedor del directorio propio (/proveedores) sin pasar por el buscador
  const [modalDirectorioAbierto, setModalDirectorioAbierto] = useState(false);
  const [proveedoresDirectorio, setProveedoresDirectorio] = useState<{ id: string; nombre: string; email: string | null; bloqueado?: boolean }[]>([]);
  const [cargandoDirectorio, setCargandoDirectorio] = useState(false);
  const [agregandoDirectorioId, setAgregandoDirectorioId] = useState<string | null>(null);
  const [busquedaDirectorio, setBusquedaDirectorio] = useState("");

  // Rebuscador con contexto ("¿No encontraste lo que buscabas?")
  const [refinarAbierto, setRefinarAbierto] = useState(false);
  const [contextoRefinar, setContextoRefinar] = useState("");
  const [refinando, setRefinando] = useState(false);
  const [refineFiltros, setRefineFiltros] = useState<{ requeridas: string[]; excluidas: string[] } | null>(null);

  const [modalEmailAbierto, setModalEmailAbierto] = useState(false);
  const [generandoEmail, setGenerandoEmail] = useState(false);
  const [emailSubject, setEmailSubject] = useState("");
  const [emailBody, setEmailBody] = useState("");
  const [destinatarios, setDestinatarios] = useState<Destinatario[]>([]);
  const [enviados, setEnviados] = useState<Set<string>>(new Set());
  const [enviando, setEnviando] = useState(false);

  const [ocProveedor, setOcProveedor] = useState<Resultado | null>(null);
  const [ocEmitidas, setOcEmitidas] = useState<Set<string>>(new Set());

  // Contexto de lista de cotización (varios ítems en paralelo)
  const listaId = searchParams.get("lista");
  const [lista, setLista] = useState<{
    id: string; nombre: string;
    items: { cotizacion_id: string; nombre: string; cantidad?: number; comparado: boolean }[];
  } | null>(null);
  // Cantidad a comprar del ítem actual
  const [cantidad, setCantidad] = useState<number>(1);

  const [historialItem, setHistorialItem] = useState<{ nombre: string; precio?: number } | null>(null);
  const [modalRespuesta, setModalRespuesta] = useState<{ resultado_id: string; proveedor: string } | null>(null);
  const [formResp, setFormResp] = useState({ precio: "", moneda: "CLP", plazo: "", condiciones: "", notas: "" });
  const [guardandoResp, setGuardandoResp] = useState(false);
  const [fuentesActivas, setFuentesActivas] = useState<string[]>([]);
  const [evaluaciones, setEvaluaciones] = useState<Record<string, {
    evaluacion: string; emoji: string; color: string; mensaje: string;
    precio_promedio_historico?: number; total_compras?: number; ultima_compra?: string;
  }>>({});

  useEffect(() => {
    // Precarga la vista comparador para que "Comparar (X)" navegue al instante
    if (id !== "demo") router.prefetch(`/listas/${id}`);
    if (listaId) router.prefetch(`/listas/${listaId}`);
    createClient().auth.getUser().then(({ data }) => {
      setUserId(data.user?.id ?? null);
      setPlan(data.user?.user_metadata?.plan ?? "free");
      setUserEmail(data.user?.email ?? "");
    });
    fetch("https://open.er-api.com/v6/latest/USD")
      .then(r => r.json())
      .then(d => { if (d.rates) setTasas(d.rates); })
      .catch(() => { setTasas({ CLP: 950, EUR: 0.92, CNY: 7.25, GBP: 0.79, BRL: 5.0, MXN: 17.0 }); });
    buscar();
  }, []);

  // Reconstruye Resultados desde filas de la BD (precargadas por el prefetch de
  // la lista), carga instantánea sin repetir la búsqueda en vivo.
  const cargarPrecargados = (filas: Record<string, unknown>[]): boolean => {
    const items: Resultado[] = [];
    const fuentes = new Set<string>();
    for (const f of filas) {
      let meta: Record<string, unknown> = {};
      try { meta = f.metadata ? JSON.parse(f.metadata as string) : {}; } catch { /* sin metadata */ }
      const fuente = (meta.fuente_label as string) ?? (f.fuente as string) ?? "manual";
      fuentes.add(fuente);
      items.push({
        ...meta,
        _uid: (f.id as string) ?? crypto.randomUUID(),
        titulo: (meta.titulo as string) ?? (f.proveedor_nombre as string) ?? "",
        precio: f.precio as number | null,
        moneda: (f.moneda as string) ?? "CLP",
        url: (f.url as string) ?? "",
        fuente,
        pais: (f.pais as string) ?? "CL",
        proveedor: (f.proveedor_nombre as string) ?? "",
        tipo_proveedor: f.tipo_proveedor as string,
        relevante: f.relevante as boolean,
        thumbnail: (meta.thumbnail as string) ?? null,
      } as Resultado);
    }
    if (!items.length) return false;
    items.sort((a, b) => (a.precio == null ? 1 : 0) - (b.precio == null ? 1 : 0));
    setResultados(items);
    setFuentesActivas(Array.from(fuentes).map(f => FUENTE_CHIP[f] ?? f));
    setPrecargado(true);
    setLoading(false);
    return true;
  };

  const buscar = async (override?: {
    terminos_es: string[]; terminos_en: string[]; nombre_item: string; categoria: string | null;
  }, forzarStream = false) => {
    setLoading(true);
    setError("");
    setResultados([]);
    setFuentesActivas([]);
    setPrecargado(false);

    let terminos_es: string[] = [];
    let terminos_en: string[] = [];
    let nombre_item = "";
    let categoria: string | null = null;
    // Categorías marcadas por el usuario en la identificación (una o más)
    let categorias = searchParams.get("cats")?.split(",").filter(Boolean) ?? [];

    if (override) {
      // Rebusca refinada con contexto del usuario
      terminos_es = override.terminos_es;
      terminos_en = override.terminos_en;
      nombre_item = override.nombre_item;
      categoria = override.categoria;
      if (override.categoria) categorias = [override.categoria];
    } else if (id === "demo") {
      terminos_es = searchParams.get("es")?.split(",").filter(Boolean) ?? [];
      terminos_en = searchParams.get("en")?.split(",").filter(Boolean) ?? [];
      nombre_item = searchParams.get("nombre") ?? "";
      categoria = searchParams.get("cat");
    } else {
      const supabase = createClient();
      // Cotización y resultados precargados en paralelo (una sola espera)
      const [cot, previos] = await Promise.all([
        supabase
          .from("cotizaciones")
          .select("nombre_identificado, descripcion, terminos_busqueda_es, terminos_busqueda_en, categoria")
          .eq("id", id)
          .single(),
        !forzarStream && listaId
          ? supabase.from("resultados").select("*").eq("cotizacion_id", id).eq("estado", "encontrado")
          : Promise.resolve({ data: null }),
      ]);
      if (cot.data) {
        terminos_es = cot.data.terminos_busqueda_es ?? [];
        terminos_en = cot.data.terminos_busqueda_en ?? [];
        nombre_item = cot.data.nombre_identificado ?? cot.data.descripcion ?? "";
        categoria = cot.data.categoria ?? null;
        // Descripción original de la IA, sirve como especificaciones para el correo
        setDescripcionItem(cot.data.nombre_identificado && cot.data.descripcion ? cot.data.descripcion : "");
      }
      setNombreItem(nombre_item);
      // Si el prefetch de la lista ya buscó este ítem → carga instantánea
      if (previos.data && previos.data.length >= 5 && cargarPrecargados(previos.data)) return;
    }
    setNombreItem(nombre_item);

    try {
      const uid = (await createClient().auth.getUser()).data.user?.id ?? null;
      const res = await fetch(`${API_URL}/api/buscar/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          cotizacion_id: id, terminos_es, terminos_en, nombre_item,
          categoria: categorias[0] ?? categoria,
          categorias: categorias.length ? categorias : (categoria ? [categoria] : null),
          user_id: uid,
        }),
      });
      if (!res.ok || !res.body) throw new Error("Error en la busqueda");

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      const seenUrls = new Set<string>();

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";

        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          try {
            const msg = JSON.parse(line.slice(6));
            if (msg.done) {
              setLoading(false);
            } else if (msg.result) {
              // Un resultado individual, efecto cascada
              const r: Resultado = { ...msg.result, _uid: crypto.randomUUID() };
              if (r.url && seenUrls.has(r.url)) continue;
              if (r.url) seenUrls.add(r.url);
              setResultados(prev => [...prev, r]);
              setFuentesActivas(prev =>
                prev.includes(msg.source) ? prev : [...prev, msg.source]
              );
              // Evaluar precio histórico
              if (r.precio != null) {
                if (uid && nombre_item) {
                  fetch(`${API_URL}/api/historico/evaluar`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ precio: r.precio, item_nombre: nombre_item, user_id: uid }),
                  }).then(res => res.json()).then(ev => {
                    setEvaluaciones(prev => ({ ...prev, [r._uid!]: ev }));
                  }).catch(() => {});
                }
              }
            }
          } catch { /* ignore malformed line */ }
        }
      }
    } catch {
      setError("No se pudieron cargar los resultados. Verifica que el backend este corriendo.");
    } finally {
      setLoading(false);
    }
  };

  // Rebusca con contexto del usuario: la IA depura términos, categoría y filtros
  const handleRefinar = async () => {
    if (!contextoRefinar.trim()) return;
    setRefinando(true);
    try {
      const res = await fetch(`${API_URL}/api/refinar-busqueda`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          nombre_item: nombreItem,
          contexto: contextoRefinar.trim(),
          categoria_actual: searchParams.get("cats")?.split(",")[0] ?? null,
        }),
      });
      if (!res.ok) throw new Error();
      const r = await res.json();

      // Persistir los términos depurados en la cotización (rebuscas futuras)
      if (id !== "demo" && userId) {
        await createClient().from("cotizaciones").update({
          terminos_busqueda_es: r.terminos_busqueda_es,
          terminos_busqueda_en: r.terminos_busqueda_en,
          ...(r.categoria ? { categoria: r.categoria } : {}),
        }).eq("id", id);
      }

      setRefineFiltros({
        requeridas: (r.palabras_requeridas ?? []).map((w: string) => w.toLowerCase()),
        excluidas: (r.palabras_excluidas ?? []).map((w: string) => w.toLowerCase()),
      });
      setRefinarAbierto(false);
      setContextoRefinar("");
      setSoloRelevantes(true);
      setSeleccionados(new Set<string>());
      setToast("Rebuscando con los términos depurados...");
      setTimeout(() => setToast(""), 3000);
      buscar({
        terminos_es: r.terminos_busqueda_es ?? [],
        terminos_en: r.terminos_busqueda_en ?? [],
        nombre_item: r.nombre_tecnico || nombreItem,
        categoria: r.categoria ?? null,
      });
    } catch {
      setToast("No se pudo refinar la búsqueda. Intenta de nuevo.");
      setTimeout(() => setToast(""), 3000);
    } finally {
      setRefinando(false);
    }
  };

  const toggleSeleccionado = (uid: string) => {
    setSeleccionados(prev => {
      const next = new Set(prev);
      if (next.has(uid)) next.delete(uid); else next.add(uid);
      return next;
    });
  };

  // Carga el estado de la lista (progreso x/y) cuando hay contexto de lista.
  // Fusiona las marcas locales de la sesión (el servidor puede ir atrasado).
  useEffect(() => {
    if (!listaId || !userId) return;
    fetch(`${API_URL}/api/listas/${listaId}?user_id=${userId}`)
      .then(r => (r.ok ? r.json() : null))
      .then(d => {
        if (!d) return;
        const loc = comparadosLocales(listaId);
        setLista({
          ...d,
          items: d.items.map((it: { cotizacion_id: string; nombre: string; comparado: boolean }) =>
            loc.has(it.cotizacion_id) ? { ...it, comparado: true } : it),
        });
        const itemActual = d.items.find((it: { cotizacion_id: string }) => it.cotizacion_id === id);
        if (itemActual?.cantidad) setCantidad(itemActual.cantidad);
      })
      .catch(() => {});
  }, [listaId, userId, id]);

  // Sin lista: recuperar cantidad guardada en la sesión
  useEffect(() => {
    if (listaId) return;
    try {
      const guardada = parseFloat(sessionStorage.getItem(`cantidad_cot_${id}`) ?? "");
      if (guardada > 0) setCantidad(guardada);
    } catch { /* sin storage */ }
  }, [id, listaId]);

  const guardarCantidad = (n: number) => {
    const val = n > 0 ? n : 1;
    setCantidad(val);
    if (listaId && userId) {
      fetch(`${API_URL}/api/listas/${listaId}/cantidad`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user_id: userId, cotizacion_id: id, cantidad: val }),
        keepalive: true,
      }).catch(() => {});
      setLista(prev => prev ? {
        ...prev,
        items: prev.items.map(it => it.cotizacion_id === id ? { ...it, cantidad: val } : it),
      } : prev);
    } else {
      try { sessionStorage.setItem(`cantidad_cot_${id}`, String(val)); } catch { /* sin storage */ }
    }
  };

  // Persiste la selección y navega: sin lista → comparador; con lista → siguiente ítem
  const handleComparar = async () => {
    if (!userId || id === "demo") {
      setToast("Debes iniciar sesion para comparar proveedores");
      setTimeout(() => setToast(""), 3000);
      return;
    }
    const urls = resultados.filter(r => seleccionados.has(r._uid!)).map(r => r.url).filter(Boolean);
    if (!urls.length) return;
    setComparando(true);
    try {
      // keepalive: los POST sobreviven a la navegación inmediata
      const pComparador = fetch(`${API_URL}/api/cotizaciones/${id}/comparador`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ urls }),
        keepalive: true,
      });

      if (listaId) {
        const pComparado = fetch(`${API_URL}/api/listas/${listaId}/comparado`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ user_id: userId, cotizacion_id: id }),
          keepalive: true,
        });

        // Si la lista aún no cargó (race condition en navegación rápida), buscarla ahora
        let listaData = lista;
        if (!listaData) {
          try {
            const r = await fetch(`${API_URL}/api/listas/${listaId}?user_id=${userId}`);
            if (r.ok) {
              const d = await r.json();
              const loc0 = comparadosLocales(listaId);
              listaData = {
                ...d,
                items: d.items.map((it: { cotizacion_id: string; nombre: string; comparado: boolean }) =>
                  loc0.has(it.cotizacion_id) ? { ...it, comparado: true } : it),
              };
              setLista(listaData);
            }
          } catch { /* continuar sin lista */ }
        }

        // Registrar el ítem actual como comparado en la sesión ANTES de calcular
        // el siguiente: inmune a que el POST de background aún no haya escrito.
        marcarComparadoLocal(listaId, id);
        const loc = comparadosLocales(listaId);
        const siguiente = listaData?.items.find(
          (it: { cotizacion_id: string; comparado: boolean }) => !it.comparado && !loc.has(it.cotizacion_id)
        );
        if (siguiente) {
          router.push(`/cotizar/${siguiente.cotizacion_id}/resultados?lista=${listaId}`);
          return;
        }
        // Último ítem: la vista de lista lee los flags recién escritos, esperar aquí
        await Promise.all([pComparador, pComparado]);
        router.push(`/listas/${listaId}`);
        return;
      }

      // Sin lista (cotización suelta, ej. enlaces antiguos): el comparador lee
      // los flags, esperar antes de navegar. /listas/{id} envuelve la
      // cotización en una lista de 1 ítem si todavía no tenía una.
      await pComparador;
      router.push(`/listas/${id}`);
    } catch {
      setToast("No se pudo guardar la selección");
      setTimeout(() => setToast(""), 3000);
      setComparando(false);
    }
  };

  const handleAgregarLista = async () => {
    if (!userId) {
      setToast("Debes iniciar sesion para crear una lista de cotizacion");
      setTimeout(() => setToast(""), 3000);
      return;
    }
    const selArray = resultados.filter(r => seleccionados.has(r._uid!));
    if (!selArray.length) return;
    setCreandoLista(true);

    // Badges automáticos (el usuario los puede reasignar en la lista)
    const conPrecio = selArray.filter(r => r.precio != null);
    const masEconomico = conPrecio.length
      ? conPrecio.reduce((a, b) => (a.precio! <= b.precio! ? a : b))._uid : null;
    const disponibles = selArray.filter(r =>
      r.stock_disponible === true || (typeof r.stock === "number" && r.stock > 0));
    const conveniente = (disponibles.filter(r => r.precio != null).sort((a, b) => a.precio! - b.precio!)[0]
      ?? conPrecio.sort((a, b) => a.precio! - b.precio!)[0])?._uid ?? null;

    const proveedores = selArray.map(r => {
      let badge: string | null = null;
      if (r._uid === conveniente) badge = "mas_conveniente";
      else if (r._uid === masEconomico) badge = "mas_economico";
      else if (r.stock_disponible === true || (typeof r.stock === "number" && r.stock > 0)) badge = "disponibilidad_inmediata";
      return {
        proveedor_nombre: r.proveedor || r.titulo,
        proveedor_email: null,
        fuente: r.fuente,
        url_referencia: r.url,
        precio_referencial: r.precio,
        moneda_referencial: r.moneda || "CLP",
        plazo_entrega_estimado: r.plazo_entrega_estimado ?? null,
        badge,
      };
    });

    try {
      const res = await fetch(`${API_URL}/api/procurement/eventos`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          user_id: userId,
          nombre: searchParams.get("lista") || nombreItem || "Nueva lista de cotización",
          cotizacion_id: id,
          items: [{
            nombre: nombreItem || selArray[0].titulo,
            numero_parte: selArray[0].numero_parte ?? null,
            marca: selArray[0].marca ?? null,
            cantidad: 1,
            proveedores,
          }],
        }),
      });
      const data = await res.json();
      if (data?.evento?.id) router.push(`/procurement/${data.evento.id}`);
    } catch {
      setToast("No se pudo crear la lista de cotización");
      setTimeout(() => setToast(""), 3000);
    } finally {
      setCreandoLista(false);
    }
  };

  const abrirDirectorio = async () => {
    setModalDirectorioAbierto(true);
    if (proveedoresDirectorio.length > 0 || !userId) return;
    setCargandoDirectorio(true);
    try {
      const res = await fetch(`${API_URL}/api/suppliers?user_id=${userId}`);
      if (res.ok) setProveedoresDirectorio(await res.json());
    } catch { /* silent */ } finally {
      setCargandoDirectorio(false);
    }
  };

  const agregarDeDirectorio = async (proveedorId: string) => {
    if (!userId) return;
    setAgregandoDirectorioId(proveedorId);
    try {
      const res = await fetch(`${API_URL}/api/cotizaciones/${id}/proveedor-directorio`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user_id: userId, proveedor_id: proveedorId }),
      });
      const fila = await res.json().catch(() => ({}));
      if (!res.ok) {
        setToast(fila.detail || "No se pudo agregar el proveedor");
        setTimeout(() => setToast(""), 3000);
        return;
      }
      const nuevo: Resultado & { contacto?: string; resultado_id?: string } = {
        _uid: fila.id,
        titulo: fila.proveedor_nombre,
        precio: null,
        moneda: fila.moneda ?? "CLP",
        url: `manual://${fila.id}`,
        fuente: "manual",
        pais: fila.pais ?? "CL",
        proveedor: fila.proveedor_nombre,
        tipo_proveedor: "desconocido",
        relevante: true,
        contacto: fila.proveedor_email,
        resultado_id: fila.id,
      };
      setResultados(prev => [...prev, nuevo]);
      setSeleccionados(prev => new Set(prev).add(nuevo._uid!));
      setToast(`${fila.proveedor_nombre} agregado — ya puedes enviarle la cotización`);
      setTimeout(() => setToast(""), 3500);
    } catch {
      setToast("Error de red agregando el proveedor");
      setTimeout(() => setToast(""), 3000);
    } finally {
      setAgregandoDirectorioId(null);
    }
  };

  const handleSolicitar = async () => {
    if (!userId) {
      setToast("Debes iniciar sesion para enviar cotizaciones por email");
      setTimeout(() => setToast(""), 3000);
      return;
    }
    const selArray = resultados.filter(r => seleccionados.has(r._uid!));
    if (!selArray.length) return;
    setGenerandoEmail(true);
    try {
      // Especificaciones reales para que Gemini no caiga en la frase genérica
      // "se adjuntan por separado": la descripción de la IA al identificar el
      // ítem, más marca/modelo/descripción del resultado elegido si los tiene.
      const r0 = selArray[0];
      const specsPartes = [
        descripcionItem,
        r0.marca ? `Marca: ${r0.marca}` : null,
        r0.numero_parte ? `Modelo/N° de parte: ${r0.numero_parte}` : null,
        r0.descripcion,
      ].filter(Boolean);
      const specs = specsPartes.length ? specsPartes.join(". ") : undefined;

      const res = await fetch(`${API_URL}/api/gmail/generar-correo`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ nombre_item: nombreItem, specs, proveedor_nombre: r0.proveedor || r0.titulo, cantidad: "1" }),
      });
      if (!res.ok) throw new Error();
      const { subject, body } = await res.json();
      setEmailSubject(subject);
      setEmailBody(body);
      // Email inicial: el que ya venga en el resultado (si lo hay)
      setDestinatarios(selArray.map(r => ({
        _uid: r._uid,
        nombre: r.proveedor || r.titulo,
        url: r.url,
        email: (r as unknown as { contacto?: string }).contacto || "",
        resultado_id: (r as unknown as { resultado_id?: string }).resultado_id,
      })));
      setEnviados(new Set());
      setModalEmailAbierto(true);

      // En background: scrapea el email de cada proveedor que no lo tenga y rellena
      selArray.forEach(async r => {
        if ((r as unknown as { contacto?: string }).contacto || !r.url) return;
        try {
          const cr = await fetch(`${API_URL}/api/contacto`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ url: r.url, proveedor: r.proveedor, nombre_item: nombreItem, cantidad }),
          });
          if (!cr.ok) return;
          const datos = await cr.json();
          if (datos.email) {
            setDestinatarios(prev => prev.map(d =>
              d._uid === r._uid && !d.email ? { ...d, email: datos.email } : d
            ));
          }
        } catch { /* silencioso */ }
      });
    } catch {
      setToast("Error generando el correo. Verifica que el backend este corriendo.");
      setTimeout(() => setToast(""), 3000);
    } finally {
      setGenerandoEmail(false);
    }
  };

  const handleEmailChange = (uid: string, email: string) => {
    setDestinatarios(prev => prev.map(d => d._uid === uid ? { ...d, email } : d));
  };

  const handleGuardarRespuesta = async () => {
    if (!modalRespuesta) return;
    setGuardandoResp(true);
    try {
      const body: Record<string, unknown> = {};
      if (formResp.precio) body.precio_respuesta = parseFloat(formResp.precio);
      if (formResp.moneda) body.moneda_respuesta = formResp.moneda;
      if (formResp.plazo) body.plazo_entrega = formResp.plazo;
      if (formResp.condiciones) body.condiciones_pago = formResp.condiciones;
      if (formResp.notas) body.notas = formResp.notas;
      await fetch(`${API_URL}/api/resultados/${modalRespuesta.resultado_id}/respuesta`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
      });
      setToast(`Respuesta de ${modalRespuesta.proveedor} registrada`);
      setTimeout(() => setToast(""), 3000);
      setModalRespuesta(null);
    } catch { /* silent */ } finally { setGuardandoResp(false); }
  };

  const handleEnviarEmails = async () => {
    const pendientes = destinatarios.filter(d => d.email.includes("@") && !enviados.has(d._uid!));
    if (!pendientes.length) return;
    setEnviando(true);
    let ok = 0;
    let errMsg = "";
    for (const dest of pendientes) {
      try {
        const res = await fetch(`${API_URL}/api/gmail/enviar`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ cotizacion_id: id, resultado_id: dest.resultado_id, to_email: dest.email, subject: emailSubject, body: emailBody, user_id: userId, proveedor_nombre: dest.nombre }),
        });
        if (!res.ok) {
          const d = await res.json().catch(() => ({}));
          errMsg = d.detail || "No se pudo enviar";
          continue;
        }
        ok++;
        setEnviados(prev => new Set([...prev, dest._uid!]));
      } catch { errMsg = "Error de red al enviar"; }
    }
    setEnviando(false);
    if (ok > 0) {
      setTimeout(() => {
        setModalEmailAbierto(false);
        setToast(`Correos enviados a ${ok} proveedor${ok !== 1 ? "es" : ""} desde tu correo`);
        setTimeout(() => setToast(""), 4000);
      }, 800);
    } else {
      setToast(errMsg.includes("Gmail no conectado")
        ? "Conecta tu Gmail en el dashboard para enviar desde tu correo"
        : errMsg || "No se pudieron enviar los correos");
      setTimeout(() => setToast(""), 4500);
    }
  };

  // Agrupa resultados que parecen ser el mismo producto (mismo número de parte,
  // o título muy similar) visto en distintas fuentes, para mostrar una sola card
  // con el desglose de precio por fuente.
  const grupos = agruparPorProducto(resultados);

  const esGrupoRelevante = (g: GrupoResultado) => {
    if ((g.principal as unknown as Record<string, unknown>).relevante === false) return false;
    const tituloNorm = normalizarTexto(g.principal.titulo);
    // Filtros de la rebusca refinada (IA + contexto del usuario)
    if (refineFiltros) {
      if (refineFiltros.excluidas.some(w => tituloNorm.includes(normalizarTexto(w)))) return false;
      if (refineFiltros.requeridas.length &&
          !refineFiltros.requeridas.some(w => tituloNorm.includes(normalizarTexto(w).slice(0, Math.max(4, w.length - 1))))) {
        return false;
      }
      return true;
    }
    return esRelevanteParaItem(g.principal.titulo, nombreItem);
  };

  const nOcultos = grupos.filter(g => !esGrupoRelevante(g)).length;

  const filtrados = grupos
    .filter(g => !soloRelevantes || esGrupoRelevante(g))
    .filter(g => {
      if (filtroPrecio === "con_precio") return g.principal.precio != null;
      if (filtroPrecio === "sin_precio") return g.principal.precio == null;
      return true;
    })
    .filter(g => {
      if (filtroPais === "chile") return g.principal.pais === "CL";
      if (filtroPais === "internacional") return g.principal.pais !== "CL";
      return true;
    })
    .sort((a, b) => {
      const pa = a.principal.precio, pb = b.principal.precio;
      if (orden === "precio_asc") { if (pa == null) return 1; if (pb == null) return -1; return pa - pb; }
      if (orden === "precio_desc") { if (pa == null) return 1; if (pb == null) return -1; return pb - pa; }
      return 0;
    });

  const nSeleccionados = seleccionados.size;
  const puedeEmitirOC = plan === "pro" || plan === "business";

  // Progreso de la lista (x/y)
  const nComparadosLista = lista?.items.filter(it => it.comparado).length ?? 0;
  const nItemsLista = lista?.items.length ?? 0;
  const idxItemActual = lista ? lista.items.findIndex(it => it.cotizacion_id === id) : -1;

  const fuentesLabel = fuentesActivas.join(" · ");

  const inputSt: React.CSSProperties = {
    background: "var(--surface)", border: "1px solid var(--n-300)", borderRadius: "var(--r-md)",
    padding: "9px 12px", fontSize: 14, color: "var(--n-900)",
    fontFamily: "var(--font-sans)", outline: "none", width: "100%",
  };

  // Botón secundario dentro de la barra flotante oscura
  const barBtn: React.CSSProperties = {
    background: "rgba(255,255,255,.1)", color: "var(--canvas)", border: "none",
    borderRadius: "var(--r-md)", padding: "9px 13px",
    fontSize: 13.5, fontWeight: 500, fontFamily: "var(--font-sans)", cursor: "pointer",
  };

  return (
    <div style={{ minHeight: "100vh", background: "var(--canvas)", padding: "24px 20px" }}>
      <div style={{ maxWidth: 800, margin: "0 auto" }}>

        {/* Modal registrar respuesta proveedor */}
        {modalRespuesta && (
          <div style={{
            position: "fixed", inset: 0, background: "rgba(0,0,0,0.5)", zIndex: 500,
            display: "flex", alignItems: "center", justifyContent: "center", padding: 20,
          }} onClick={() => setModalRespuesta(null)}>
            <div style={{ background: "var(--bg-surface)", border: "1px solid var(--border-default)", padding: 28, width: "100%", maxWidth: 400 }}
              onClick={e => e.stopPropagation()}>
              <div style={{ fontSize: 9, fontWeight: 700, color: "var(--text-muted)", letterSpacing: "0.06em", marginBottom: 4 }}>Registrar respuesta</div>
              <div style={{ fontSize: 14, fontWeight: 700, color: "var(--text-primary)", marginBottom: 20 }}>{modalRespuesta.proveedor}</div>
              <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                <div style={{ display: "flex", gap: 8 }}>
                  <input type="number" placeholder="Precio ofertado" value={formResp.precio}
                    onChange={e => setFormResp(p => ({ ...p, precio: e.target.value }))} style={{ ...inputSt, flex: 1 }} />
                  <select value={formResp.moneda} onChange={e => setFormResp(p => ({ ...p, moneda: e.target.value }))}
                    style={{ ...inputSt, width: "auto" }}>
                    {["CLP","USD","EUR"].map(m => <option key={m}>{m}</option>)}
                  </select>
                </div>
                <input type="text" placeholder="Plazo de entrega (ej: 5 días hábiles)" value={formResp.plazo}
                  onChange={e => setFormResp(p => ({ ...p, plazo: e.target.value }))} style={inputSt} />
                <input type="text" placeholder="Condiciones de pago" value={formResp.condiciones}
                  onChange={e => setFormResp(p => ({ ...p, condiciones: e.target.value }))} style={inputSt} />
                <textarea placeholder="Notas..." value={formResp.notas} rows={2}
                  onChange={e => setFormResp(p => ({ ...p, notas: e.target.value }))} style={{ ...inputSt, resize: "vertical" }} />
              </div>
              <div style={{ display: "flex", gap: 8, marginTop: 16 }}>
                <button onClick={handleGuardarRespuesta} disabled={guardandoResp} className="btn-swiss-primary" style={{ flex: 1 }}>
                  {guardandoResp ? "Guardando..." : "Guardar"}
                </button>
                <button onClick={() => setModalRespuesta(null)} className="btn-swiss-secondary">Cancelar</button>
              </div>
            </div>
          </div>
        )}

        {/* Modal rebuscar con contexto */}
        {refinarAbierto && (
          <div style={{
            position: "fixed", inset: 0, background: "rgba(0,0,0,0.5)", zIndex: 500,
            display: "flex", alignItems: "center", justifyContent: "center", padding: 20,
          }} onClick={() => !refinando && setRefinarAbierto(false)}>
            <div style={{ background: "var(--bg-surface)", border: "1px solid var(--border-default)", padding: 28, width: "100%", maxWidth: 460 }}
              onClick={e => e.stopPropagation()}>
              <div style={{ fontSize: 9, fontWeight: 700, color: "var(--text-muted)", letterSpacing: "0.06em", marginBottom: 4 }}>
                ¿NO ENCONTRASTE LO QUE BUSCABAS?
              </div>
              <div style={{ fontSize: 14, fontWeight: 700, color: "var(--text-primary)", marginBottom: 8 }}>
                Depurar búsqueda: {nombreItem}
              </div>
              <p style={{ fontSize: 11, color: "var(--text-secondary)", lineHeight: 1.6, marginBottom: 14 }}>
                Describe qué necesitas exactamente: para qué lo vas a usar, material, dimensiones,
                y qué NO es lo que buscas. La IA regenera los términos, la categoría y filtra los
                resultados que no correspondan.
              </p>
              <textarea
                value={contextoRefinar}
                onChange={e => setContextoRefinar(e.target.value)}
                rows={4}
                autoFocus
                placeholder={'Ej: "Quiero un trozo de madera de pino dimensionada (tabla o cuarton) para construir un mueble. NO busco esmaltes, protectores ni cercos."'}
                style={{
                  ...inputSt, width: "100%", boxSizing: "border-box", resize: "vertical", lineHeight: 1.5,
                }}
              />
              <div style={{ display: "flex", gap: 8, marginTop: 16 }}>
                <button
                  onClick={handleRefinar}
                  disabled={refinando || !contextoRefinar.trim()}
                  className="btn-swiss-primary disabled:opacity-40"
                  style={{ flex: 1 }}
                >
                  {refinando ? "Depurando con IA..." : "REBUSCAR →"}
                </button>
                <button onClick={() => setRefinarAbierto(false)} disabled={refinando} className="btn-swiss-secondary">
                  Cancelar
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Toast */}
        {toast && (
          <div style={{
            position: "fixed", top: 20, right: 20, zIndex: 100,
            background: "var(--bg-inverse)",
            border: "1px solid var(--border-strong)",
            padding: "12px 18px",
            fontSize: 11,
            color: "var(--text-inverse)",
            fontWeight: 700,
          }}>
            {toast}
          </div>
        )}

        {modalEmailAbierto && (
          <EmailPreviewModal
            fromEmail={userEmail}
            destinatarios={destinatarios}
            subject={emailSubject}
            body={emailBody}
            onSubjectChange={setEmailSubject}
            onBodyChange={setEmailBody}
            onEmailChange={handleEmailChange}
            onEnviar={handleEnviarEmails}
            onCancelar={() => setModalEmailAbierto(false)}
            enviando={enviando}
            enviados={enviados}
          />
        )}

        {historialItem && userId && (
          <HistorialPrecioModal
            itemNombre={historialItem.nombre}
            precioActual={historialItem.precio}
            userId={userId}
            onClose={() => setHistorialItem(null)}
          />
        )}

        {ocProveedor && (
          <OCModal
            resultado={ocProveedor}
            nombreItem={nombreItem}
            cotizacionId={id}
            userId={userId ?? ""}
            plan={plan}
            onClose={() => setOcProveedor(null)}
            onEnviada={(numeroOc) => {
              setOcEmitidas(prev => new Set([...prev, ocProveedor._uid!]));
              setOcProveedor(null);
              setToast(`OC ${numeroOc} enviada`);
              setTimeout(() => setToast(""), 4000);
            }}
          />
        )}

        {/* Header */}
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 28 }}>
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12 }}>
              <Link href="/cotizar" style={{ fontSize: 13, color: "var(--n-500)", textDecoration: "none" }}>
                ← Nueva cotización
              </Link>
              <span style={{ color: "var(--n-300)" }}>/</span>
              <span style={{ fontSize: 13, color: "var(--brand)", fontWeight: 500 }}>Proveedores</span>
            </div>
            <h1 style={{ fontSize: 26, fontWeight: 600, color: "var(--n-900)", margin: 0, letterSpacing: "-0.015em" }}>
              {nombreItem || "Buscando proveedores…"}
            </h1>
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 10, flexWrap: "wrap" }}>
              {resultados.length > 0 && (
                <span style={{
                  fontSize: 12.5, fontWeight: 500,
                  color: "var(--success)", background: "var(--st-aprobada-bg)",
                  padding: "3px 11px", borderRadius: "var(--r-pill)",
                }}>
                  {resultados.length} proveedores{loading ? "…" : ""}
                </span>
              )}
              {loading && resultados.length === 0 && (
                <span style={{ fontSize: 13, color: "var(--n-500)" }}>
                  Buscando…
                </span>
              )}
              {precargado && (
                <span style={{
                  fontSize: 12.5, fontWeight: 500,
                  color: "var(--brand-700)", background: "var(--brand-50)",
                  padding: "3px 11px", borderRadius: "var(--r-pill)",
                }} title="Búsqueda hecha en background al crear la lista. Usa Recargar para actualizar.">
                  ⚡ Precargado
                </span>
              )}
              {fuentesActivas.map(f => (
                <span key={f} style={{
                  fontSize: 12.5, fontWeight: 500,
                  color: "var(--n-600)", background: "var(--surface-2)",
                  border: "1px solid var(--n-200)",
                  padding: "3px 11px", borderRadius: "var(--r-pill)",
                  animation: "fadeIn 0.3s ease",
                }}>{f}</span>
              ))}
            </div>
          </div>
          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
            {/* Cantidad a comprar del ítem actual */}
            <span style={{ display: "inline-flex", alignItems: "center", gap: 7, border: "1px solid var(--n-300)", borderRadius: "var(--r-md)", padding: "6px 10px", background: "var(--surface)" }}>
              <span style={{ fontSize: 13, color: "var(--n-600)" }}>Cantidad</span>
              <span
                title="Cantidad a comprar de este ítem. La usamos para calcular el total (precio × cantidad), los informes PDF y el mensaje de cotización a los proveedores. Cada ítem de la lista tiene su propia cantidad; puedes editarla."
                style={{
                  cursor: "help", fontSize: 10, fontWeight: 600, color: "var(--n-500)",
                  border: "1px solid var(--n-300)", borderRadius: "50%",
                  width: 15, height: 15, display: "inline-flex", alignItems: "center",
                  justifyContent: "center", lineHeight: 1,
                }}
              >?</span>
              <input
                type="number"
                min={1}
                value={cantidad}
                onChange={e => setCantidad(parseFloat(e.target.value) || 1)}
                onBlur={e => guardarCantidad(parseFloat(e.target.value) || 1)}
                onKeyDown={e => { if (e.key === "Enter") (e.target as HTMLInputElement).blur(); }}
                style={{
                  width: 54, background: "var(--surface-2)", border: "1px solid var(--n-300)",
                  borderRadius: "var(--r-sm)", padding: "4px 6px", fontSize: 13, color: "var(--n-900)",
                  fontFamily: "var(--font-mono)", fontVariantNumeric: "tabular-nums", outline: "none", textAlign: "right",
                }}
              />
            </span>
            {lista && (
              <button
                onClick={() => router.push(`/listas/${lista.id}`)}
                className="btn-swiss-secondary"
                style={{ fontSize: 13, padding: "8px 14px", whiteSpace: "nowrap" }}
              >
                Ver lista ({nComparadosLista}/{nItemsLista})
              </button>
            )}
            <button
              onClick={() => buscar(undefined, true)}
              className="btn-swiss-secondary"
              style={{ fontSize: 13, padding: "8px 14px" }}
            >
              Recargar
            </button>
          </div>
        </div>

        {/* Barra de progreso de la lista */}
        {listaId && !lista && (
          <div style={{
            background: "var(--surface)", border: "1px solid var(--n-200)", borderRadius: "var(--r-lg)",
            padding: "12px 14px", marginBottom: 16,
          }}>
            <span style={{ fontSize: 13, color: "var(--n-500)" }}>Cargando lista…</span>
          </div>
        )}
        {lista && (
          <div style={{
            background: "var(--surface)", border: "1px solid var(--n-200)", borderRadius: "var(--r-lg)",
            padding: "12px 14px", marginBottom: 16,
          }}>
            <div style={{ fontSize: 12.5, fontWeight: 600, color: "var(--n-500)", marginBottom: 8 }}>Lista: {lista.nombre}</div>
            <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
              {lista.items.map((it, i) => {
                const actual = it.cotizacion_id === id;
                return (
                  <button
                    key={it.cotizacion_id}
                    onClick={() => !actual && router.push(`/cotizar/${it.cotizacion_id}/resultados?lista=${lista.id}`)}
                    title={it.nombre}
                    style={{
                      display: "inline-flex", alignItems: "center", gap: 5,
                      padding: "5px 11px", cursor: actual ? "default" : "pointer",
                      borderRadius: "var(--r-pill)", fontSize: 13, fontWeight: 500,
                      fontFamily: "var(--font-sans)",
                      background: actual ? "var(--brand)" : it.comparado ? "var(--st-aprobada-bg)" : "var(--surface-2)",
                      color: actual ? "#fff" : it.comparado ? "var(--success)" : "var(--n-600)",
                      border: `1px solid ${actual ? "var(--brand)" : it.comparado ? "transparent" : "var(--n-200)"}`,
                    }}
                  >
                    {it.comparado ? "✓ " : ""}{i + 1}. {it.nombre.length > 18 ? it.nombre.slice(0, 18) + "…" : it.nombre}
                  </button>
                );
              })}
            </div>
          </div>
        )}

        <div style={{ display: "flex", justifyContent: "flex-end", marginBottom: resultados.length > 0 ? 0 : 16 }}>
          <button onClick={abrirDirectorio} className="btn-swiss-secondary" style={{ fontSize: 13 }}>
            + Proveedor de mi directorio
          </button>
        </div>

        {modalDirectorioAbierto && (
          <div style={{
            position: "fixed", inset: 0, background: "rgba(0,0,0,0.5)", zIndex: 500,
            display: "flex", alignItems: "center", justifyContent: "center", padding: 20,
          }} onClick={() => setModalDirectorioAbierto(false)}>
            <div
              onClick={e => e.stopPropagation()}
              style={{
                background: "var(--surface)", borderRadius: "var(--r-lg)", border: "1px solid var(--n-200)",
                width: "100%", maxWidth: 460, maxHeight: "70vh", display: "flex", flexDirection: "column",
              }}
            >
              <div style={{ padding: "16px 18px", borderBottom: "1px solid var(--n-200)" }}>
                <div style={{ fontSize: 15, fontWeight: 600, color: "var(--n-900)", marginBottom: 2 }}>Agregar de mi directorio</div>
                <div style={{ fontSize: 12.5, color: "var(--n-600)" }}>Cotízale a un proveedor propio, sin depender del buscador.</div>
                <input
                  value={busquedaDirectorio}
                  onChange={e => setBusquedaDirectorio(e.target.value)}
                  placeholder="Buscar por nombre o correo…"
                  autoFocus
                  style={{
                    marginTop: 10, width: "100%", height: 38, padding: "0 12px",
                    background: "var(--canvas)", border: "1px solid var(--n-300)", borderRadius: "var(--r-md)",
                    fontSize: 13.5, color: "var(--n-900)", fontFamily: "var(--font-sans)", outline: "none",
                  }}
                />
              </div>
              <div style={{ overflowY: "auto", padding: 8 }}>
                {cargandoDirectorio ? (
                  <div style={{ padding: 20, textAlign: "center", fontSize: 13, color: "var(--n-500)" }}>Cargando…</div>
                ) : (
                  proveedoresDirectorio
                    .filter(p => !p.bloqueado)
                    .filter(p => {
                      const q = busquedaDirectorio.trim().toLowerCase();
                      if (!q) return true;
                      return p.nombre.toLowerCase().includes(q) || (p.email ?? "").toLowerCase().includes(q);
                    })
                    .map(p => (
                      <button
                        key={p.id}
                        onClick={() => agregarDeDirectorio(p.id)}
                        disabled={agregandoDirectorioId === p.id}
                        style={{
                          width: "100%", display: "flex", justifyContent: "space-between", alignItems: "center",
                          padding: "10px 12px", background: "none", border: "none", borderRadius: "var(--r-md)",
                          cursor: "pointer", textAlign: "left", fontFamily: "var(--font-sans)",
                          opacity: agregandoDirectorioId === p.id ? 0.5 : 1,
                        }}
                        onMouseEnter={e => (e.currentTarget.style.background = "var(--canvas)")}
                        onMouseLeave={e => (e.currentTarget.style.background = "none")}
                      >
                        <div style={{ minWidth: 0 }}>
                          <div style={{ fontSize: 13.5, fontWeight: 500, color: "var(--n-900)" }}>{p.nombre}</div>
                          <div style={{ fontSize: 12, color: "var(--n-500)" }}>{p.email || "sin correo registrado"}</div>
                        </div>
                        <span style={{ fontSize: 12.5, color: "var(--brand)", flexShrink: 0 }}>
                          {agregandoDirectorioId === p.id ? "Agregando…" : "+ Agregar"}
                        </span>
                      </button>
                    ))
                )}
                {!cargandoDirectorio && proveedoresDirectorio.length === 0 && (
                  <div style={{ padding: 20, textAlign: "center", fontSize: 13, color: "var(--n-500)" }}>
                    Aún no tienes proveedores en tu directorio. Impórtalos por Excel desde{" "}
                    <a href="/proveedores/importar" style={{ color: "var(--brand)" }}>Proveedores</a>.
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        {resultados.length > 0 && (
          <FiltrosProveedores
            filtroPrecio={filtroPrecio}
            filtroPais={filtroPais}
            orden={orden}
            total={filtrados.length}
            onFiltroPrecio={setFiltroPrecio}
            onFiltroPais={setFiltroPais}
            onOrden={setOrden}
          />
        )}

        {/* Rebuscador con contexto */}
        {!loading && resultados.length > 0 && (
          <div style={{
            display: "flex", justifyContent: "space-between", alignItems: "center", gap: 10, flexWrap: "wrap",
            border: "1px solid var(--brand-100)", background: "var(--brand-50)", borderRadius: "var(--r-md)",
            padding: "10px 14px", marginBottom: 12,
          }}>
            <span style={{ fontSize: 13.5, color: "var(--n-700)" }}>
              ¿No encontraste lo que buscabas? Cuéntanos qué necesitas exactamente y depuramos la búsqueda.
            </span>
            <button
              onClick={() => setRefinarAbierto(true)}
              style={{
                color: "#fff", background: "var(--brand)", cursor: "pointer",
                border: "none", padding: "8px 14px", borderRadius: "var(--r-md)",
                fontFamily: "var(--font-sans)", fontWeight: 600, fontSize: 13, whiteSpace: "nowrap",
              }}
            >
              Rebuscar con contexto →
            </button>
          </div>
        )}

        {/* Filtro de relevancia: oculta accesorios y resultados que no son el ítem */}
        {resultados.length > 0 && nOcultos > 0 && (
          <div style={{
            display: "flex", justifyContent: "space-between", alignItems: "center", gap: 10, flexWrap: "wrap",
            padding: "10px 14px", marginBottom: 12, borderRadius: "var(--r-md)",
            background: "var(--surface-2)", border: "1px solid var(--n-200)",
          }}>
            <span style={{ fontSize: 13, color: "var(--n-500)" }}>
              {soloRelevantes
                ? `${nOcultos} resultado${nOcultos !== 1 ? "s" : ""} poco relevante${nOcultos !== 1 ? "s" : ""} oculto${nOcultos !== 1 ? "s" : ""} (accesorios, otros productos)`
                : "Mostrando todos los resultados, incluidos los poco relevantes"}
            </span>
            <button
              onClick={() => setSoloRelevantes(v => !v)}
              style={{
                color: "var(--brand)", background: "var(--surface)",
                border: "1px solid var(--n-300)", padding: "6px 12px", borderRadius: "var(--r-md)",
                cursor: "pointer", fontFamily: "var(--font-sans)", fontSize: 13, fontWeight: 500,
              }}
            >
              {soloRelevantes ? `Mostrar todos (+${nOcultos})` : "Solo relevantes"}
            </button>
          </div>
        )}

        {/* Skeleton solo cuando no hay nada aún */}
        {loading && resultados.length === 0 && (
          <div>
            <div className="label" style={{ color: "var(--text-muted)", marginBottom: 16, textAlign: "center", padding: "12px 0" }}>
              Consultando fuentes en paralelo...
            </div>
            <SkeletonResultados n={4} />
          </div>
        )}

        {/* Indicador de carga progresiva mientras llegan más resultados */}
        {loading && resultados.length > 0 && (
          <div style={{
            display: "flex", alignItems: "center", gap: 10,
            padding: "8px 0", marginBottom: 8,
            fontSize: 13, color: "var(--n-500)",
          }}>
            <div style={{ display: "flex", gap: 5 }}>
              {[0,1,2].map(i => (
                <span key={i} style={{
                  width: 7, height: 7, borderRadius: "50%", background: "var(--brand)",
                  animation: `dotWave 1.3s ease-in-out ${i * 0.16}s infinite`,
                }} />
              ))}
            </div>
            Cargando más fuentes…
          </div>
        )}

        {!loading && error && (
          <div style={{
            background: "var(--fill-error)",
            border: "1px solid var(--border-accent)",
            padding: "16px",
            fontSize: 11,
            color: "var(--text-error)",
            textAlign: "center",
          }}>
            {error}
          </div>
        )}

        {!loading && !error && resultados.length === 0 && (
          <div style={{
            background: "var(--bg-surface)",
            border: "1px solid var(--border-default)",
            padding: "48px 20px",
            textAlign: "center",
          }}>
            <div className="label" style={{ color: "var(--text-muted)", marginBottom: 8 }}>Sin resultados</div>
            <div style={{ fontSize: 13, fontWeight: 700, color: "var(--text-primary)", marginBottom: 6 }}>
              No encontramos proveedores
            </div>
            <div style={{ fontSize: 11, color: "var(--text-secondary)", marginBottom: 20 }}>
              Danos más contexto de lo que necesitas y depuramos la búsqueda.
            </div>
            <div style={{ display: "flex", gap: 8, justifyContent: "center", flexWrap: "wrap" }}>
              <button onClick={() => setRefinarAbierto(true)} className="btn-swiss-primary">
                Rebuscar con contexto →
              </button>
              <Link href="/cotizar" className="btn-swiss-secondary" style={{ textDecoration: "none" }}>
                Nueva cotizacion
              </Link>
            </div>
          </div>
        )}

        {/* Resultados, muestran mientras carga (streaming) */}
        {filtrados.length > 0 && (
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            {filtrados.map((grupo, i) => {
              const r = grupo.principal;
              const ev = evaluaciones[r._uid!];

              return (
                <div key={r._uid ?? i} style={{
                  border: "1px solid var(--n-200)", borderRadius: "var(--r-lg)",
                  overflow: "hidden", background: "var(--surface)", boxShadow: "var(--shadow-card)",
                  animation: "slideIn 0.22s ease both",
                  animationDelay: `${Math.min(i * 40, 400)}ms`,
                }}>
                  <CardProveedor
                    resultado={r}
                    seleccionado={seleccionados.has(r._uid!)}
                    onSeleccionar={() => toggleSeleccionado(r._uid!)}
                    tasas={tasas}
                    ofertas={grupo.ofertas.length > 1 ? grupo.ofertas : undefined}
                    nombreItem={nombreItem}
                    cantidad={cantidad}
                    onToggleOferta={toggleSeleccionado}
                    seleccionadosIds={seleccionados}
                  />

                  {/* Badges fila inferior */}
                  <div style={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    padding: "8px 16px 10px",
                    background: "var(--surface-2)",
                    borderTop: "1px solid var(--n-200)",
                  }}>
                    <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                      {/* Precio histórico badge */}
                      {r.precio != null && ev && (
                        <span
                          title={ev.mensaje}
                          onClick={() => setHistorialItem({ nombre: nombreItem, precio: r.precio ?? undefined })}
                          className="label"
                          style={{
                            color: ev.color,
                            background: `${ev.color}18`,
                            border: `1px solid ${ev.color}44`,
                            padding: "2px 8px",
                            cursor: "pointer",
                          }}
                        >
                          {ev.emoji}{" "}
                          {ev.evaluacion === "primera_vez" ? "Primera vez"
                            : ev.evaluacion === "deal" ? "Mejor precio"
                            : ev.evaluacion === "alto" ? "Precio alto"
                            : ev.evaluacion === "muy_alto" ? "Muy caro"
                            : "Normal"}
                          {ev.precio_promedio_historico && ` · prom $${Math.round(ev.precio_promedio_historico).toLocaleString("es-CL")}`}
                        </span>
                      )}
                    </div>

                    {/* Registrar respuesta (si fue contactado y tiene id en DB) */}
                    {(r as unknown as Record<string, unknown>).id && enviados.has(r._uid!) && (
                      <button
                        onClick={() => {
                          setFormResp({ precio: "", moneda: "CLP", plazo: "", condiciones: "", notas: "" });
                          setModalRespuesta({ resultado_id: String((r as unknown as Record<string, unknown>).id), proveedor: r.proveedor || r.titulo });
                        }}
                        style={{
                          fontSize: 13, fontWeight: 500,
                          color: "var(--success)", background: "var(--surface)",
                          border: "1px solid var(--success)", padding: "5px 12px", borderRadius: "var(--r-md)",
                          cursor: "pointer", fontFamily: "var(--font-sans)",
                        }}
                      >
                        + Respuesta
                      </button>
                    )}

                    {/* OC button */}
                    {r.precio != null && (
                      <div>
                        {ocEmitidas.has(r._uid!) ? (
                          <span style={{
                            fontSize: 13, fontWeight: 500,
                            color: "var(--success)",
                            background: "var(--st-aprobada-bg)",
                            borderRadius: "var(--r-pill)",
                            padding: "4px 11px",
                          }}>
                            OC enviada
                          </span>
                        ) : (
                          <button
                            onClick={() => setOcProveedor(r)}
                            style={{
                              fontSize: 13, fontWeight: 500,
                              color: puedeEmitirOC ? "var(--brand)" : "var(--n-500)",
                              background: "var(--surface)",
                              border: `1px solid ${puedeEmitirOC ? "var(--brand)" : "var(--n-300)"}`,
                              padding: "5px 12px", borderRadius: "var(--r-md)",
                              cursor: "pointer",
                              fontFamily: "var(--font-sans)",
                            }}
                          >
                            {puedeEmitirOC ? "Emitir OC →" : "OC (Pro)"}
                          </button>
                        )}
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}

        {/* Barra flotante de acciones, siempre visible con selección activa */}
        {nSeleccionados > 0 && (
          <div style={{
            position: "fixed", bottom: 24, left: "50%", transform: "translateX(-50%)",
            width: "min(780px, calc(100vw - 40px))", zIndex: 300,
          }}>
            <div style={{
              background: "var(--n-900)",
              borderRadius: "var(--r-xl)",
              boxShadow: "var(--shadow-modal)",
              padding: "12px 18px",
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              gap: 10,
              flexWrap: "wrap",
            }}>
              <span style={{ fontSize: 13.5, fontWeight: 500, color: "var(--canvas)" }}>
                {nSeleccionados} seleccionado{nSeleccionados > 1 ? "s" : ""}
              </span>
              <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                <button
                  onClick={handleAgregarLista}
                  disabled={creandoLista}
                  style={{ ...barBtn, opacity: creandoLista ? 0.5 : 1 }}
                  title="Agrupa varios ítems en una lista de cotización / proyecto"
                >
                  {creandoLista ? "Creando…" : "+ Lista"}
                </button>
                <button
                  onClick={handleSolicitar}
                  disabled={generandoEmail}
                  style={{ ...barBtn, opacity: generandoEmail ? 0.5 : 1 }}
                  title="Enviar solicitud de cotización por correo"
                >
                  {generandoEmail ? "Generando…" : "✉ Correo"}
                </button>
                {lista && (
                  <button
                    onClick={() => router.push(`/listas/${lista.id}`)}
                    style={{ ...barBtn, whiteSpace: "nowrap" }}
                  >
                    Ver lista ({nComparadosLista}/{nItemsLista})
                  </button>
                )}
                <button
                  onClick={handleComparar}
                  disabled={comparando || loading}
                  title={loading ? "Espera a que termine la búsqueda antes de comparar" : undefined}
                  style={{
                    background: "var(--brand)", color: "#fff", border: "none",
                    borderRadius: "var(--r-md)", padding: "9px 16px",
                    fontSize: 13.5, fontWeight: 600, fontFamily: "var(--font-sans)",
                    cursor: comparando || loading ? "not-allowed" : "pointer",
                    opacity: comparando || loading ? 0.5 : 1,
                  }}
                >
                  {comparando
                    ? "Guardando…"
                    : loading
                      ? "Buscando…"
                      : lista && idxItemActual >= 0 && idxItemActual < nItemsLista - 1
                        ? `Comparar y seguir (${nSeleccionados}) →`
                        : `Comparar (${nSeleccionados}) →`}
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
