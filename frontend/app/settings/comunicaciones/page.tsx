"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowLeft, Mail } from "lucide-react";
import { authFetch } from "@/lib/authFetch";
import { Card, SkeletonBox, CascadeWrapper } from "@/components/ui";
import { MailTemplateEditor, type PlantillaCorreo } from "@/components/workflow/MailTemplateEditor";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type Plantilla = PlantillaCorreo;

function Insignia({ personalizada }: { personalizada: boolean }) {
  return (
    <span style={{
      fontSize: 11, padding: "3px 9px", borderRadius: 999,
      background: personalizada ? "var(--brand-50)" : "var(--n-100)",
      color: personalizada ? "var(--brand)" : "var(--n-500)",
      border: `1px solid ${personalizada ? "var(--brand-100)" : "var(--n-200)"}`,
    }}>
      {personalizada ? "Personalizada" : "Default"}
    </span>
  );
}

export default function ComunicacionesPage() {
  const router = useRouter();
  const [cargando, setCargando] = useState(true);
  const [esAdmin, setEsAdmin] = useState(false);
  const [plantillas, setPlantillas] = useState<Plantilla[]>([]);
  const [editando, setEditando] = useState<Plantilla | null>(null);

  const cargar = async () => {
    setCargando(true);
    try {
      const [org, lista] = await Promise.all([
        authFetch(`${API_URL}/api/organizacion/mia`).then(r => r.json()).catch(() => ({})),
        authFetch(`${API_URL}/api/mail-templates`).then(r => r.json()).catch(() => []),
      ]);
      setEsAdmin(!!org.es_admin);
      setPlantillas(Array.isArray(lista) ? lista : []);
    } finally {
      setCargando(false);
    }
  };

  useEffect(() => { cargar(); }, []);

  const internas = plantillas.filter(p => p.audiencia === "internal");
  const externas = plantillas.filter(p => p.audiencia === "external");

  const renderGrupo = (titulo: string, items: Plantilla[]) => (
    <div style={{ marginBottom: 24 }}>
      <h2 style={{ fontSize: 14, fontWeight: 600, color: "var(--n-700)", margin: "0 0 10px" }}>{titulo}</h2>
      <Card padding={0}>
        {items.map((p, i) => (
          <div
            key={p.evento}
            onClick={() => setEditando(p)}
            style={{
              display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12,
              padding: "13px 16px", cursor: "pointer",
              borderBottom: i === items.length - 1 ? "none" : "1px solid var(--n-100)",
            }}
          >
            <div style={{ minWidth: 0 }}>
              <div style={{ fontSize: 13.5, fontWeight: 500, color: "var(--n-900)" }}>{p.descripcion}</div>
              <div style={{ fontSize: 12, color: "var(--n-500)", marginTop: 2 }}>{p.evento}</div>
              <div style={{ fontSize: 11, color: "var(--n-500)", marginTop: 2 }}>{p.usos_en_nodos || 0} uso(s) en tarjetas</div>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 10, flexShrink: 0 }}>
              <Insignia personalizada={p.origen !== "default"} />
              <span style={{ fontSize: 12.5, color: "var(--brand)" }}>{esAdmin ? "Editar →" : "Ver →"}</span>
            </div>
          </div>
        ))}
      </Card>
    </div>
  );

  if (cargando) {
    return (
      <div style={{ maxWidth: 680, margin: "0 auto" }}>
        <SkeletonBox height={13} width={120} style={{ marginBottom: 16 }} />
        <SkeletonBox height={26} width={280} style={{ marginBottom: 8 }} />
        <SkeletonBox height={13} width={380} style={{ marginBottom: 20 }} />
        <CascadeWrapper>
          <Card padding={18}><SkeletonBox height={120} width="100%" /></Card>
          <Card padding={18} style={{ marginTop: 16 }}><SkeletonBox height={160} width="100%" /></Card>
        </CascadeWrapper>
      </div>
    );
  }

  return (
    <div style={{ maxWidth: 680, margin: "0 auto" }}>
      <button onClick={() => router.push("/settings")} style={{ border: 0, background: "none", color: "var(--n-600)", cursor: "pointer", display: "inline-flex", alignItems: "center", gap: 6, marginBottom: 16, fontSize: 13.5 }}>
        <ArrowLeft size={16} /> Configuración
      </button>

      <div style={{ marginBottom: 20 }}>
        <h1 style={{ fontSize: 22, fontWeight: 600, color: "var(--n-900)", margin: "0 0 4px", display: "flex", alignItems: "center", gap: 8 }}>
          <Mail size={20} strokeWidth={1.75} /> Biblioteca de correos
        </h1>
        <p style={{ fontSize: 13.5, color: "var(--n-600)", margin: 0 }}>
          {esAdmin
            ? "Defaults reutilizables de tu organización. Las cadencias, destinatarios y loops se configuran dentro de cada tarjeta del ciclo de compras."
            : "Defaults reutilizables de tu organización. La automatización se consulta dentro del ciclo de compras."}
        </p>
      </div>

      {renderGrupo("Comunicaciones internas", internas)}
      {renderGrupo("Comunicaciones externas", externas)}

      {editando && (
        <MailTemplateEditor
          plantilla={editando}
          esAdmin={esAdmin}
          onClose={() => setEditando(null)}
          onGuardado={() => { setEditando(null); cargar(); }}
        />
      )}
    </div>
  );
}
