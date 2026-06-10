import { AppShell } from "@/components/layout/app-shell";

export function Sidebar({ children }: { children?: React.ReactNode }) {
  return <AppShell>{children}</AppShell>;
}
