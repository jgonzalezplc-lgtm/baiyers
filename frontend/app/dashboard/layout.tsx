import AppShellServer from "@/components/AppShellServer";

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  return <AppShellServer>{children}</AppShellServer>;
}
