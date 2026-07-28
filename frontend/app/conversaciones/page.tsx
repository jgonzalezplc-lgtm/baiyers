"use client";
import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Mail, ExternalLink, RefreshCw } from "lucide-react";
import { createClient } from "@/lib/supabase/client";
import { PageHeader, Table, TableHead, TableRow, EmptyState, Spinner, Badge, BtnSecondary } from "@/components/ui";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const COLS = "1fr 1.4fr 160px 130px 120px 32px";

interface Conversacion {
  id: string;
  proveedor_nombre: string | null;
  proveedor_email: string | null;
  subject: string | null;
  estado: string;
  last_message_at: string | null;
  gmail_url: string;
  propuestas_pendientes: number;
}

const ESTADO_LABEL: Record<string, { label: string; tipo: "success" | "warning" | "error" | "info" | "default" }> = {
  draft: { label: "Borrador", tipo: "default" },
  ready_to_send: { label: "Por enviar", tipo: "default" },
  sent: { label: "Enviado", tipo: "info" },
  waiting_for_supplier: { label: "Esperando respuesta", tipo: "info" },
  supplier_replied: { label: "Respondió", tipo: "default" },
  partially_answered: { label: "Respuesta parcial", tipo: "warning" },
  clarification_required: { label: "Necesita aclaración", tipo: "warning" },
  complete: { label: "Completa", tipo: "success" },
  closed: { label: "Cerrada", tipo: "default" },
  human_review_required: { label: "Revisar manualmente", tipo: "warning" },
  failed: { label: "Falló", tipo: "error" },
  compra_iniciada: { label: "Iniciando compra", tipo: "info" },
};

function fmtFecha(iso: string | null) {
  if (!iso) return "—";
  const d = new Date(iso);
  return `${d.getDate()} ${["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"][d.getMonth()]}, ${d.getHours().toString().padStart(2, "0")}:${d.getMinutes().toString().padStart(2, "0")}`;
}

export default function ConversacionesPage() {
  const [userId, setUserId] = useState<string | null>(null);
  const [convs, setConvs] = useState<Conversacion[]>([]);
  const [loading, setLoading] = useState(true);
  const [sincronizando, setSincronizando] = useState(false);
  const [error, setError] = useState("");
  const router = useRouter();

  const cargar = useCallback((uid: string) => {
    setLoading(true);
    fetch(`${API_URL}/api/gmail/conversaciones?user_id=${uid}`)
      .then(r => (r.ok ? r.json() : []))
      .then(setConvs)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    createClient().auth.getUser().then(({ data }) => {
      const uid = data.user?.id;
      if (!uid) { setLoading(false); return; }
      setUserId(uid);
      cargar(uid);
    });
  }, [cargar]);

  const sincronizar = async () => {
    if (!userId) return;
    setSincronizando(true);
    setError("");
    try {
      const res = await fetch(`${API_URL}/api/gmail/sincronizar-respuestas?user_id=${userId}`, { method: "POST" });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || "No se pudo sincronizar");
      }
      cargar(userId);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSincronizando(false);
    }
  };

  return (
    <>
      <PageHeader
        title="Conversaciones"
        subtitle="Correos con proveedores, con lo que el agente entendió de cada respuesta. Se revisan solas cada pocos minutos — el botón es para forzarlo ahora mismo."
        actions={
          <BtnSecondary onClick={sincronizar} disabled={sincronizando || !userId}>
            <RefreshCw size={15} strokeWidth={1.75} style={{ marginRight: 6, animation: sincronizando ? "spin 1s linear infinite" : undefined }} />
            {sincronizando ? "Sincronizando…" : "Sincronizar respuestas"}
          </BtnSecondary>
        }
      />

      {error && (
        <div style={{ marginBottom: 16, padding: "10px 14px", borderRadius: "var(--r-md)", background: "var(--st-rechazada-bg)", color: "var(--st-rechazada-fg)", fontSize: 13.5 }}>
          {error}
        </div>
      )}

      {loading ? (
        <Spinner />
      ) : convs.length === 0 ? (
        <Table>
          <EmptyState
            icon={<Mail size={26} strokeWidth={1.5} />}
            title="Aún no hay conversaciones"
            description="Cuando envíes una cotización por correo desde una lista, aparecerá acá el hilo con el proveedor."
          />
        </Table>
      ) : (
        <Table>
          <TableHead cols={COLS}>
            <span>Proveedor</span>
            <span>Asunto</span>
            <span>Estado</span>
            <span>Propuestas</span>
            <span>Último mensaje</span>
            <span />
          </TableHead>
          {convs.map((c, i) => {
            const est = ESTADO_LABEL[c.estado] ?? { label: c.estado, tipo: "default" as const };
            return (
              <TableRow key={c.id} cols={COLS} onClick={() => router.push(`/conversaciones/${c.id}`)} last={i === convs.length - 1}>
                <div style={{ minWidth: 0 }}>
                  <div style={{ fontWeight: 500, color: "var(--n-900)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    {c.proveedor_nombre || c.proveedor_email || "Proveedor"}
                  </div>
                  {c.proveedor_email && <div style={{ fontSize: 12, color: "var(--n-500)" }}>{c.proveedor_email}</div>}
                </div>
                <div style={{ color: "var(--n-700)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{c.subject || "—"}</div>
                <Badge tipo={est.tipo}>{est.label}</Badge>
                <span>
                  {c.propuestas_pendientes > 0 ? (
                    <Badge tipo="warning">{c.propuestas_pendientes} pendiente{c.propuestas_pendientes > 1 ? "s" : ""}</Badge>
                  ) : (
                    <span style={{ color: "var(--n-400)", fontSize: 13 }}>—</span>
                  )}
                </span>
                <span style={{ color: "var(--n-500)", fontSize: 13 }}>{fmtFecha(c.last_message_at)}</span>
                <a
                  href={c.gmail_url} target="_blank" rel="noreferrer"
                  onClick={e => e.stopPropagation()}
                  title="Abrir en Gmail"
                  style={{ color: "var(--n-500)", display: "inline-flex" }}
                >
                  <ExternalLink size={15} strokeWidth={1.75} />
                </a>
              </TableRow>
            );
          })}
        </Table>
      )}
      <style>{`@keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }`}</style>
    </>
  );
}
