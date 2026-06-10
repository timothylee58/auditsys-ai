import Link from "next/link";
import { NavLinks } from "@/components/layout/nav-links";

export function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen bg-ink text-zinc-50">
      <aside className="fixed inset-y-0 left-0 hidden w-64 border-r border-line bg-panel/80 px-5 py-6 lg:block">
        <Link href="/documents" className="block">
          <p className="text-xs uppercase tracking-[0.24em] text-accent">AuditSys</p>
          <h1 className="mt-2 font-display text-4xl font-bold leading-none">AI Review Room</h1>
        </Link>
        <NavLinks />
      </aside>
      <main className="min-h-screen px-4 py-5 lg:ml-64 lg:px-8 lg:py-8">
        <div className="mx-auto max-w-6xl">{children}</div>
      </main>
    </div>
  );
}
