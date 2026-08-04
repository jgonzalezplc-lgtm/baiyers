"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ListChecks } from "lucide-react";
import { createClient } from "@/lib/supabase/client";
import {
  PageHeader, Table, TableHead, TableRow, EmptyState, BtnPrimary, Badge, fmtCLP,
  SkeletonTableRow, CascadeWrapper,
} from "@/components/ui";
import { useMiembrosOrg } from "@/lib/useMiembrosOrg";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const COLS = "1fr 80px 120px 120px 140px 110px";

interface ListaResumen {
  id: string;
  nombre: string;
  created_at: string | null;
  monto_total: number;
  n_items: number;
  n_comparados: number;
  n_definitivos: number;
  aprobacion_estado: "pendiente" | "aprobado" | "rechazado" | null;
  creado_por: string | null;
}

/** Estado de autorización, siempre visible como badge (nunca texto plano). */
function BadgeAprobacion({ estado }: { estado: ListaResumen["aprobacion_estado"] }) {
  if (estado === "aprobado") return <Badge status="aprobado">Autorizado</Badge>;
  if (estado === "rechazado") return <Badge status="rechazado">Rechazada</Badge>;
  if (estado === "pendiente") return <Badge status="pendiente">Esperando</Badge>;
  return <Badge status="borrador">Sin solicitar</Badge>;
}

export default function ListasPage() {
  const [listas, setListas] = useState<ListaResumen[]>([]);
  const [loading, setLoading] = useState(true);
  const router = useRouter();
  const { nombreDe, hayVariosMiembros } = useMiembrosOrg();

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
        title="Cotizaciones"
        subtitle="Cada compra, de 1 o varios ítems, con su estado de autorización."
        actions={<BtnPrimary onClick={() => router.push("/cotizar")}>Nueva cotización</BtnPrimary>}
      />

      {loading ? (
        <Table>
          <TableHead cols={COLS}>
            <div>Cotización</div>
            <div>Ítems</div>
            <div>Comparados</div>
            <div>Definitivos</div>
            <div>Autorización</div>
            <div style={{ textAlign: "right" }}>Total</div>
          </TableHead>
          <CascadeWrapper>
            {Array.from({ length: 5 }).map((_, i) => (
              <SkeletonTableRow key={i} cols={COLS} last={i === 4} />
            ))}
          </CascadeWrapper>
        </Table>
      ) : listas.length === 0 ? (
        <Table>
          <EmptyState
            icon={ListChecks}
            title="Aún no tienes cotizaciones"
            description="Describe lo que necesitas comprar, sea un ítem o un proyecto completo con varios."
            action={<Link href="/cotizar" className="btn-swiss-primary" style={{ textDecoration: "none" }}>Crear mi primera cotización</Link>}
          />
        </Table>
      ) : (
        <Table>
          <TableHead cols={COLS}>
            <div>Cotización</div>
            <div>Ítems</div>
            <div>Comparados</div>
            <div>Definitivos</div>
            <div>Autorización</div>
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
                    {hayVariosMiembros && nombreDe(l.creado_por) && (
                      <> · por <strong style={{ color: "var(--n-700)", fontWeight: 500 }}>{nombreDe(l.creado_por)}</strong></>
                    )}
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
              <div><BadgeAprobacion estado={l.aprobacion_estado} /></div>
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
