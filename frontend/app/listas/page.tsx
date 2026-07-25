"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ListChecks } from "lucide-react";
import { createClient } from "@/lib/supabase/client";
import {
  PageHeader, Table, TableHead, TableRow, EmptyState, Spinner, BtnPrimary, fmtCLP,
} from "@/components/ui";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const COLS = "1fr 90px 120px 120px 130px";

interface ListaResumen {
  id: string;
  nombre: string;
  created_at: string | null;
  monto_total: number;
  n_items: number;
  n_comparados: number;
  n_definitivos: number;
}

export default function ListasPage() {
  const [listas, setListas] = useState<ListaResumen[]>([]);
  const [loading, setLoading] = useState(true);
  const router = useRouter();

  useEffect(() => {
    createClient().auth.getUser().then(({ data }) => {
      const uid = data.user?.id;
      if (!uid) { setLoading(false); return; }
      fetch(`${API_URL}/api/listas?user_id=${uid}`)
        .then(r => (r.ok ? r.json() : []))
        .then(setListas)
        .catch(() => {})
        .finally(() => setLoading(false));
    });
  }, []);

  return (
    <>
      <PageHeader
        title="Listas de cotización"
        subtitle="Varios ítems cotizados en paralelo."
        actions={<BtnPrimary onClick={() => router.push("/cotizar")}>Nueva cotización</BtnPrimary>}
      />

      {loading ? (
        <Spinner />
      ) : listas.length === 0 ? (
        <Table>
          <EmptyState
            icon={ListChecks}
            title="Aún no tienes listas"
            description={'Escribe varios ítems separados por ";" en Nueva cotización, por ejemplo: martillo; taladro; madera.'}
            action={<Link href="/cotizar" className="btn-swiss-primary" style={{ textDecoration: "none" }}>Crear mi primera lista</Link>}
          />
        </Table>
      ) : (
        <Table>
          <TableHead cols={COLS}>
            <div>Lista</div>
            <div>Ítems</div>
            <div>Comparados</div>
            <div>Definitivos</div>
            <div style={{ textAlign: "right" }}>Total</div>
          </TableHead>
          {listas.map((l, i) => (
            <TableRow
              key={l.id}
              cols={COLS}
              zebra={i % 2 === 1}
              last={i === listas.length - 1}
              onClick={() => router.push(`/listas/${l.id}`)}
            >
              <div style={{ minWidth: 0 }}>
                <div style={{ fontWeight: 600, color: "var(--n-900)" }}>{l.nombre}</div>
                {l.created_at && (
                  <div style={{ fontSize: 12.5, color: "var(--n-500)", marginTop: 1 }}>
                    {new Date(l.created_at).toLocaleDateString("es-CL", { day: "numeric", month: "short", year: "numeric" })}
                  </div>
                )}
              </div>
              <div style={{ color: "var(--n-600)" }}>{l.n_items}</div>
              <div style={{ color: l.n_comparados === l.n_items ? "var(--success)" : "var(--n-600)", fontWeight: l.n_comparados === l.n_items ? 600 : 400 }}>
                {l.n_comparados}/{l.n_items}
              </div>
              <div style={{ color: l.n_definitivos === l.n_items ? "var(--success)" : "var(--n-600)", fontWeight: l.n_definitivos === l.n_items ? 600 : 400 }}>
                {l.n_definitivos}/{l.n_items}
              </div>
              <div style={{
                fontWeight: 600, color: "var(--n-900)", textAlign: "right",
                fontFamily: "var(--font-mono)", fontVariantNumeric: "tabular-nums",
              }}>
                {l.monto_total ? fmtCLP(l.monto_total) : "—"}
              </div>
            </TableRow>
          ))}
        </Table>
      )}
    </>
  );
}
