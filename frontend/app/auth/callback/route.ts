import { NextResponse } from "next/server";
import { createClient } from "@/lib/supabase/server";

// Callback de OAuth (Google): intercambia el código por sesión y redirige.
// Los usuarios nuevos van a /onboarding (que rebota a /dashboard si ya lo hicieron).
export async function GET(request: Request) {
  const { searchParams, origin } = new URL(request.url);
  const code = searchParams.get("code");
  const next = searchParams.get("next") ?? "/onboarding";

  // Detrás de proxy (Railway/Vercel), el origin del request es el host INTERNO
  // (ej: localhost:8080). Usamos el host público reenviado para redirigir bien.
  const forwardedHost = request.headers.get("x-forwarded-host");
  const forwardedProto = request.headers.get("x-forwarded-proto") ?? "https";
  const base = forwardedHost ? `${forwardedProto}://${forwardedHost}` : origin;

  if (code) {
    const supabase = await createClient();
    const { error } = await supabase.auth.exchangeCodeForSession(code);
    if (!error) {
      return NextResponse.redirect(`${base}${next}`);
    }
  }
  // Si algo falla, de vuelta al login
  return NextResponse.redirect(`${base}/login?error=oauth`);
}
