import { createClient } from "@/lib/supabase/server";
import { redirect } from "next/navigation";
import AppShell from "./AppShell";

const PLAN_META: Record<string, { label: string; limit: string }> = {
  free:     { label: "Free",     limit: "3" },
  starter:  { label: "Starter",  limit: "20" },
  pro:      { label: "Pro",      limit: "100" },
  business: { label: "Business", limit: "∞" },
};

export default async function AppShellServer({ children }: { children: React.ReactNode }) {
  const supabase = await createClient();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) redirect("/login");

  const plan: string = user.user_metadata?.plan || "free";
  const empresa: string = user.user_metadata?.empresa || user.email || "";
  const meta = PLAN_META[plan] ?? PLAN_META.free;

  return (
    <AppShell
      empresa={empresa}
      planLabel={meta.label}
      planLimitLabel={meta.limit}
      userId={user.id}
    >
      {children}
    </AppShell>
  );
}
