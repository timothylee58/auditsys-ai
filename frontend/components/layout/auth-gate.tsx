"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { getSupabaseClient } from "@/lib/supabase";

/**
 * Client-side auth guard for the dashboard: redirects to /login when there
 * is no Supabase session. The backend independently enforces JWT auth on
 * every request — this is UX, not security.
 */
export function AuthGate({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const [checked, setChecked] = useState(false);

  useEffect(() => {
    const supabase = getSupabaseClient();
    if (!supabase) {
      // Auth not configured — let the API's 401s surface the problem rather
      // than trapping the user in a redirect loop.
      setChecked(true);
      return;
    }

    let cancelled = false;
    supabase.auth.getSession().then(({ data }) => {
      if (cancelled) return;
      if (!data.session) {
        router.replace("/login");
        return;
      }
      setChecked(true);
    });

    const {
      data: { subscription }
    } = supabase.auth.onAuthStateChange((event) => {
      if (cancelled) return;
      if (event === "SIGNED_OUT") {
        router.replace("/login");
      }
    });

    return () => {
      cancelled = true;
      subscription.unsubscribe();
    };
  }, [router]);

  if (!checked) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-ink text-sm text-zinc-400">
        Checking session…
      </div>
    );
  }

  return <>{children}</>;
}
