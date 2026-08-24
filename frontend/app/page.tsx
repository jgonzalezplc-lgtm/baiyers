import { redirect } from "next/navigation";
import LandingContent from "@/components/landing/LandingContent";

export default async function LandingPage({
  searchParams,
}: {
  searchParams: Promise<{ code?: string }>;
}) {
  // Salvavidas OAuth: si Supabase redirige el código de login a la raíz
  // (por fallback de Site URL), lo reenviamos al handler que crea la sesión.
  const { code } = await searchParams;
  if (code) redirect(`/auth/callback?code=${code}&next=/dashboard`);

  return <LandingContent />;
}
