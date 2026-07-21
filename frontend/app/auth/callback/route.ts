import { NextResponse } from "next/server";
import { createClient } from "@/lib/supabase/server";

// Callback de OAuth (Google): intercambia el código por sesión y redirige.
// Los usuarios nuevos van a /onboarding (que rebota a /dashboard si ya lo hicieron).
export async function GET(request: Request) {
  const { searchParams, origin } = new URL(request.url);
  const code = searchParams.get("code");
  const next = searchParams.get("next") ?? "/onboarding";

  if (code) {
    const supabase = await createClient();
    const { error } = await supabase.auth.exchangeCodeForSession(code);
    if (!error) {
      return NextResponse.redirect(`${origin}${next}`);
    }
  }
  // Si algo falla, de vuelta al login
  return NextResponse.redirect(`${origin}/login?error=oauth`);
}
