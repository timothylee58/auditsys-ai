"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { getSupabaseClient } from "@/lib/supabase";

export function Navbar() {
  const router = useRouter();
  const [email, setEmail] = useState<string | null>(null);

  useEffect(() => {
    const supabase = getSupabaseClient();
    if (!supabase) return;
    supabase.auth.getSession().then(({ data }) => {
      setEmail(data.session?.user.email ?? null);
    });
  }, []);

  async function handleSignOut() {
    const supabase = getSupabaseClient();
    if (supabase) {
      await supabase.auth.signOut();
    }
    router.push("/login");
    router.refresh();
  }

  return (
    <header className="flex items-center justify-between border-b border-line bg-panel px-4 py-3">
      <p className="text-sm font-medium text-zinc-100">AuditSys AI</p>
      {email ? (
        <div className="flex items-center gap-3">
          <span className="text-xs text-zinc-400">{email}</span>
          <button
            type="button"
            onClick={handleSignOut}
            className="rounded-md border border-line px-3 py-1 text-xs text-zinc-300 hover:bg-zinc-800"
          >
            Sign out
          </button>
        </div>
      ) : null}
    </header>
  );
}
