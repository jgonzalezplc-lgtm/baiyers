import AppShellServer from "@/components/AppShellServer";

export default function Layout({ children }: { children: React.ReactNode }) {
  return <AppShellServer>{children}</AppShellServer>;
}
