"use client";
/**
 * Hook compartido para el "hecho por X" (Fase D del multi-usuario).
 *
 * Trae una vez los miembros de la organización y devuelve:
 *  - nombres: mapa { user_id -> nombre amigable }
 *  - hayVariosMiembros: true si vale la pena mostrar chips "por X" (con un
 *    solo miembro sería siempre "por vos", ruido visual innecesario).
 *  - nombreDe(userId?): helper que devuelve el nombre o "" si no está.
 *
 * Cacheado a nivel de módulo por userId para que múltiples pantallas no
 * peguen al backend en paralelo — la lista de miembros cambia rara vez.
 */
import { useEffect, useState } from "react";
import { createClient } from "@/lib/supabase/client";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export interface MiembroOrg {
  user_id: string;
  nombre: string;
  rol: "admin" | "miembro";
}

const cache = new Map<string, MiembroOrg[]>();
const inflight = new Map<string, Promise<MiembroOrg[]>>();

async function cargar(userId: string): Promise<MiembroOrg[]> {
  const cacheHit = cache.get(userId);
  if (cacheHit) return cacheHit;
  const enVuelo = inflight.get(userId);
  if (enVuelo) return enVuelo;
  const p = fetch(`${API_URL}/api/organizacion/miembros?user_id=${userId}`)
    .then(r => (r.ok ? r.json() : []))
    .then((data: MiembroOrg[]) => {
      cache.set(userId, data || []);
      return data || [];
    })
    .catch(() => [] as MiembroOrg[])
    .finally(() => inflight.delete(userId));
  inflight.set(userId, p);
  return p;
}

export function useMiembrosOrg() {
  const [miembros, setMiembros] = useState<MiembroOrg[]>([]);

  useEffect(() => {
    (async () => {
      const { data } = await createClient().auth.getUser();
      const uid = data.user?.id;
      if (!uid) return;
      const lista = await cargar(uid);
      setMiembros(lista);
    })();
  }, []);

  const nombres = Object.fromEntries(miembros.map(m => [m.user_id, m.nombre || ""])) as Record<string, string>;
  const hayVariosMiembros = miembros.length > 1;
  const nombreDe = (userId?: string | null): string => (userId && nombres[userId]) || "";

  return { miembros, nombres, hayVariosMiembros, nombreDe };
}
