"use client";
import { useState, useEffect } from "react";
import { useParams } from "next/navigation";
import { createClient } from "@/lib/supabase/client";
import Link from "next/link";
import RatingModal from "@/components/RatingModal";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface OcInfo {
  numero_oc: string;
  proveedor_nombre: string;
  proveedor_id?: string;
  nombre_item?: string;
  estado: string;
}

export default function RatingPage() {
  const params = useParams();
  const ocId = params.oc_id as string;

  const [oc, setOc] = useState<OcInfo | null>(null);
  const [userId, setUserId] = useState<string | null>(null);
  const [proveedorId, setProveedorId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [yaCalificado, setYaCalificado] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    const init = async () => {
      const supabase = createClient();
      const { data: authData } = await supabase.auth.getUser();
      const uid = authData.user?.id ?? null;
      setUserId(uid);

      try {
        const supabase2 = createClient();
        const { data, error: ocErr } = await supabase2
          .from("ordenes_compra")
          .select("numero_oc, proveedor_nombre, nombre_item, estado, id")
          .eq("id", ocId)
          .single();
        if (ocErr || !data) {
          setError("No se encontro la OC.");
          return;
        }
        setOc(data);

        if (uid) {
          const suppRes = await fetch(`${API_URL}/api/suppliers?user_id=${uid}`);
          if (suppRes.ok) {
            const suppliers = await suppRes.json();
            const match = suppliers.find((s: { nombre: string; id: string }) =>
              s.nombre?.toLowerCase() === data.proveedor_nombre?.toLowerCase()
            );
            if (match) {
              setProveedorId(match.id);
              const { data: ratings } = await supabase
                .from("supplier_ratings")
                .select("id")
                .eq("proveedor_id", match.id)
                .eq("user_id", uid);
              if (ratings && ratings.length > 0) {
                setYaCalificado(true);
              }
            }
          }
        }
      } catch {
        setError("Error cargando la OC.");
      } finally {
        setLoading(false);
      }
    };
    init();
  }, [ocId]);

  const cardStyle = {
    background: "var(--bg-surface)",
    border: "1px solid var(--border-default)",
    padding: "40px 32px",
    textAlign: "center" as const,
    maxWidth: 400,
    width: "100%",
  };

  const wrapper = {
    minHeight: "100vh",
    background: "var(--bg-base)",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    padding: 20,
  };

  if (loading) {
    return (
      <div style={wrapper}>
        <div style={{ fontSize: 11, color: "var(--text-muted)" }}>Cargando...</div>
      </div>
    );
  }

  if (error || !oc) {
    return (
      <div style={wrapper}>
        <div style={cardStyle}>
          <div className="section-rule" style={{ margin: "0 auto 16px" }} />
          <div style={{ fontSize: 13, color: "var(--text-error)", fontWeight: 700 }}>{error || "OC no encontrada"}</div>
        </div>
      </div>
    );
  }

  if (yaCalificado) {
    return (
      <div style={wrapper}>
        <div style={{ ...cardStyle, borderColor: "var(--palette-green-500)" }}>
          <div className="section-rule" style={{ margin: "0 auto 16px", background: "var(--text-success)" }} />
          <div style={{ fontSize: 13, color: "var(--text-success)", fontWeight: 700, marginBottom: 8 }}>
            Ya calificaste a {oc.proveedor_nombre}
          </div>
          <div style={{ fontSize: 11, color: "var(--text-muted)", marginBottom: 20 }}>Gracias por tu feedback.</div>
          <Link href="/proveedores" className="btn-swiss-secondary" style={{ textDecoration: "none", display: "inline-block" }}>
            Ver todos los proveedores
          </Link>
        </div>
      </div>
    );
  }

  if (!userId) {
    return (
      <div style={wrapper}>
        <div style={cardStyle}>
          <div className="section-rule" style={{ margin: "0 auto 16px" }} />
          <div style={{ fontSize: 13, color: "var(--text-primary)", fontWeight: 700, marginBottom: 12 }}>
            Inicia sesion para calificar
          </div>
          <Link href="/login" className="btn-swiss-primary" style={{ textDecoration: "none", display: "inline-block" }}>
            Iniciar sesion
          </Link>
        </div>
      </div>
    );
  }

  if (!proveedorId) {
    return (
      <div style={wrapper}>
        <div style={cardStyle}>
          <div style={{ fontSize: 11, color: "var(--text-muted)" }}>No se encontro el proveedor para calificar.</div>
        </div>
      </div>
    );
  }

  return (
    <div style={{ minHeight: "100vh", background: "var(--bg-base)" }}>
      <RatingModal
        proveedorNombre={oc.proveedor_nombre}
        proveedorId={proveedorId}
        userId={userId}
        ocId={ocId}
        onGuardado={() => setYaCalificado(true)}
        onCerrar={() => { window.location.href = "/proveedores"; }}
      />
    </div>
  );
}
