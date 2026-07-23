import { NextResponse } from "next/server";
import { createClient } from "@/lib/supabase/server";

// Cierra sesión y vuelve al login. POST desde el botón "Salir" del AppShell.
export async function POST(request: Request) {
  const { origin } = new URL(request.url);
  const supabase = await createClient();
  await supabase.auth.signOut();

  // Detrás de proxy (Railway), usar el host público para el redirect.
  const fwHost = request.headers.get("x-forwarded-host");
  const fwProto = request.headers.get("x-forwarded-proto") ?? "https";
  const base = fwHost ? `${fwProto}://${fwHost}` : origin;

  return NextResponse.redirect(`${base}/login`, { status: 303 });
}
