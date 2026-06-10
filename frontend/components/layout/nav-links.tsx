"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { Route } from "next";
import { Activity, ClipboardCheck, FileText, MessageSquareText, ShieldCheck } from "lucide-react";

const navItems: Array<{ href: Route; label: string; icon: typeof FileText }> = [
  { href: "/documents", label: "Documents", icon: FileText },
  { href: "/query", label: "Query", icon: MessageSquareText },
  { href: "/review-queue", label: "Review", icon: ClipboardCheck },
  { href: "/audit-log", label: "Audit Log", icon: ShieldCheck },
  { href: "/evals", label: "Evals", icon: Activity },
];

export function NavLinks() {
  const pathname = usePathname();

  return (
    <nav className="mt-10 space-y-1" aria-label="Dashboard">
      {navItems.map((item) => {
        const active = pathname.startsWith(item.href);
        return (
          <Link
            key={item.href}
            href={item.href}
            className={[
              "flex items-center gap-3 rounded-md px-3 py-2 text-sm transition",
              "focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent",
              active
                ? "bg-white/8 text-white"
                : "text-zinc-400 hover:bg-white/5 hover:text-zinc-200",
            ].join(" ")}
            aria-current={active ? "page" : undefined}
          >
            <item.icon className="h-4 w-4 shrink-0" aria-hidden="true" />
            {item.label}
          </Link>
        );
      })}
    </nav>
  );
}
