"use client";

import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";
import { Button } from "@/components/ui/button";
import { getSupabaseClient } from "@/lib/supabase";

export default function RegisterPage() {
  const router = useRouter();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [confirmationRequired, setConfirmationRequired] = useState(false);
  const [isLoading, setIsLoading] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setIsLoading(true);

    const supabase = getSupabaseClient();
    if (!supabase) {
      setError("Authentication is not configured (missing NEXT_PUBLIC_SUPABASE_URL / ANON_KEY).");
      setIsLoading(false);
      return;
    }

    const { data, error: signUpError } = await supabase.auth.signUp({
      email,
      password,
      options: { data: { full_name: name } }
    });
    setIsLoading(false);

    if (signUpError) {
      setError(signUpError.message);
      return;
    }

    if (data.session) {
      // Email confirmation is disabled — signed straight in.
      router.push("/query");
      router.refresh();
      return;
    }
    // Email confirmation is enabled — ask the user to verify.
    setConfirmationRequired(true);
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-ink px-4">
      <form className="w-full max-w-md rounded-md border border-line bg-panel p-6" onSubmit={handleSubmit}>
        <p className="text-xs uppercase tracking-[0.24em] text-accent">AuditSys AI</p>
        <h1 className="mt-2 font-display text-4xl font-bold">Create account</h1>

        {confirmationRequired ? (
          <p className="mt-6 text-sm text-zinc-300">
            Account created. Check <span className="text-accent">{email}</span> for a
            confirmation link, then sign in.
          </p>
        ) : (
          <>
            <label className="mt-6 block text-sm text-zinc-300" htmlFor="name">
              Name
            </label>
            <input
              id="name"
              required
              autoComplete="name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="mt-2 w-full rounded-md border border-line bg-ink p-3"
            />
            <label className="mt-4 block text-sm text-zinc-300" htmlFor="email">
              Email
            </label>
            <input
              id="email"
              type="email"
              required
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="mt-2 w-full rounded-md border border-line bg-ink p-3"
            />
            <label className="mt-4 block text-sm text-zinc-300" htmlFor="password">
              Password
            </label>
            <input
              id="password"
              type="password"
              required
              minLength={8}
              autoComplete="new-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="mt-2 w-full rounded-md border border-line bg-ink p-3"
            />
            {error ? <p className="mt-4 text-sm text-red-400">{error}</p> : null}
            <Button className="mt-6 w-full" type="submit" disabled={isLoading}>
              {isLoading ? "Creating account…" : "Register"}
            </Button>
          </>
        )}
        <p className="mt-4 text-sm text-zinc-400">
          Already have an account?{" "}
          <a href="/login" className="text-accent hover:underline">
            Sign in
          </a>
        </p>
      </form>
    </main>
  );
}
