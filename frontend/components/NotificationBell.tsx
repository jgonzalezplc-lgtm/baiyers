"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Bell, CheckCheck, Mail, ThumbsUp } from "lucide-react";
import { authFetch } from "@/lib/authFetch";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const POLL_MS = 30_000;

interface Notificacion {
  id: string;
  tipo: string;
  titulo: string;
  mensaje: string;
  data: Record<string, unknown>;
  leido: boolean;
  created_at: string;
}

function fmtRelativo(iso: string) {
  const ms = Date.now() - new Date(iso).getTime();
  const min = Math.floor(ms / 60_000);
  if (min < 1) return "ahora";
  if (min < 60) return `hace ${min} min`;
  const h = Math.floor(min / 60);
  if (h < 24) return `hace ${h} h`;
  const d = Math.floor(h / 24);
  return `hace ${d} d`;
}

function iconoDe(tipo: string) {
  if (tipo === "cotizacion_aprobada") return ThumbsUp;
  if (tipo === "email_cotizacion") return Mail;
  return Bell;
}

function destinoDe(n: Notificacion): string | null {
  const data = n.data || {};
  if (n.tipo === "email_cotizacion" && data.conversation_id) return `/conversaciones/${data.conversation_id}`;
  if (n.tipo === "cotizacion_aprobada" && data.lista_id) return `/listas/${data.lista_id}`;
  return null;
}

export default function NotificationBell({ userId }: { userId: string }) {
  const [items, setItems] = useState<Notificacion[]>([]);
  const [noLeidas, setNoLeidas] = useState(0);
  const [open, setOpen] = useState(false);
  const router = useRouter();
  const cargado = useRef(false);

  const cargar = useCallback(() => {
    authFetch(`${API_URL}/api/notificaciones`)
      .then(r => (r.ok ? r.json() : null))
      .then(body => {
        if (!body) return;
        setItems(body.notificaciones || []);
        setNoLeidas(body.no_leidas || 0);
      })
      .catch(() => {});
  }, [userId]);

  useEffect(() => {
    if (!userId) return;
    cargar();
    const id = setInterval(cargar, POLL_MS);
    return () => clearInterval(id);
  }, [userId, cargar]);

  const marcarLeida = (n: Notificacion) => {
    if (!n.leido) {
      authFetch(`${API_URL}/api/notificaciones/${n.id}/leer`, { method: "POST" }).catch(() => {});
      setItems(prev => prev.map(x => (x.id === n.id ? { ...x, leido: true } : x)));
      setNoLeidas(c => Math.max(0, c - 1));
    }
    const destino = destinoDe(n);
    setOpen(false);
    if (destino) router.push(destino);
  };

  const marcarTodasLeidas = () => {
    authFetch(`${API_URL}/api/notificaciones/leer-todas`, { method: "POST" }).catch(() => {});
    setItems(prev => prev.map(x => ({ ...x, leido: true })));
    setNoLeidas(0);
  };

  const toggle = () => {
    if (!open && !cargado.current) { cargado.current = true; cargar(); }
    setOpen(v => !v);
  };

  return (
    <div style={{ position: "relative" }}>
      <button
        onClick={toggle}
        aria-label="Notificaciones"
        style={{
          position: "relative", background: "none", border: "none", cursor: "pointer",
          color: "var(--n-700)", display: "inline-flex", padding: 6, borderRadius: "var(--r-md)",
        }}
      >
        <Bell size={19} strokeWidth={1.75} />
        {noLeidas > 0 && (
          <span style={{
            position: "absolute", top: 2, right: 2,
            minWidth: 15, height: 15, padding: "0 3px", borderRadius: "50%",
            background: "var(--danger, #c0392b)", color: "#fff",
            fontSize: 10, fontWeight: 700, lineHeight: "15px", textAlign: "center",
            border: "1.5px solid var(--surface)",
          }}>{noLeidas > 9 ? "9+" : noLeidas}</span>
        )}
      </button>

      {open && (
        <>
          <div onClick={() => setOpen(false)} style={{ position: "fixed", inset: 0, zIndex: 65 }} />
          <div style={{
            position: "absolute", top: "calc(100% + 8px)", right: 0, zIndex: 70,
            width: 340, maxHeight: 420, overflowY: "auto",
            background: "var(--surface)", border: "1px solid var(--n-200)",
            borderRadius: "var(--r-md)", boxShadow: "var(--shadow-pop)",
          }}>
            <div style={{
              display: "flex", justifyContent: "space-between", alignItems: "center",
              padding: "10px 14px", borderBottom: "1px solid var(--n-200)",
            }}>
              <span style={{ fontSize: 13, fontWeight: 600, color: "var(--n-900)" }}>Notificaciones</span>
              {noLeidas > 0 && (
                <button onClick={marcarTodasLeidas} style={{
                  display: "inline-flex", alignItems: "center", gap: 4,
                  background: "none", border: "none", cursor: "pointer",
                  color: "var(--brand)", fontSize: 12, fontWeight: 600, fontFamily: "inherit",
                }}>
                  <CheckCheck size={14} strokeWidth={1.75} /> Marcar todas
                </button>
              )}
            </div>

            {items.length === 0 ? (
              <div style={{ padding: "28px 14px", textAlign: "center", color: "var(--n-500)", fontSize: 13 }}>
                Sin notificaciones por ahora
              </div>
            ) : (
              items.map(n => {
                const Icon = iconoDe(n.tipo);
                return (
                  <button
                    key={n.id}
                    onClick={() => marcarLeida(n)}
                    style={{
                      display: "flex", gap: 10, width: "100%", textAlign: "left",
                      padding: "10px 14px", border: "none", borderBottom: "1px solid var(--n-200)",
                      background: n.leido ? "transparent" : "var(--brand-50)",
                      cursor: "pointer", fontFamily: "inherit",
                    }}
                  >
                    <Icon size={16} strokeWidth={1.75} color="var(--brand)" style={{ flexShrink: 0, marginTop: 2 }} />
                    <div style={{ minWidth: 0 }}>
                      <div style={{ fontSize: 13, fontWeight: 600, color: "var(--n-900)" }}>{n.titulo}</div>
                      <div style={{ fontSize: 12, color: "var(--n-600)", marginTop: 2 }}>{n.mensaje}</div>
                      <div style={{ fontSize: 11, color: "var(--n-500)", marginTop: 4 }}>{fmtRelativo(n.created_at)}</div>
                    </div>
                  </button>
                );
              })
            )}
          </div>
        </>
      )}
    </div>
  );
}
