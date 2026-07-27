import { createClient } from "@/lib/supabase/server";
import { redirect } from "next/navigation";
import AppShell from "./AppShell";

const PLAN_META: Record<string, { label: string; limit: string }> = {
  free:     { label: "Free",     limit: "3" },
  starter:  { label: "Starter",  limit: "20" },
  pro:      { label: "Pro",      limit: "100" },
  business: { label: "Business", limit: "∞" },
};

const CAMPOS_REQUERIDOS = ["empresa", "nombre_usuario", "rut", "industria"];

export default async function AppShellServer({ children }: { children: React.ReactNode }) {
  let user;
  try {
    const supabase = await createClient();
    const { data } = await supabase.auth.getUser();
    user = data.user;
  } catch (e) {
    console.error("[AppShellServer] auth.getUser tiró:", (e as Error).message);
    redirect("/login");
  }
  if (!user) redirect("/login");

  const m = (user.user_metadata ?? {}) as Record<string, unknown>;
  const plan: string = typeof m.plan === "string" ? m.plan : "free";
  const empresa: string = (typeof m.empresa === "string" && m.empresa) || user.email || "";
  const meta = PLAN_META[plan] ?? PLAN_META.free;
  const perfilIncompleto = CAMPOS_REQUERIDOS.some(k => {
    const v = m[k];
    return typeof v !== "string" || !v.trim();
  });

  return (
    <AppShell
      empresa={empresa}
      planLabel={meta.label}
      planLimitLabel={meta.limit}
      userId={user.id}
      perfilIncompleto={perfilIncompleto}
    >
      {children}
    </AppShell>
  );
}
