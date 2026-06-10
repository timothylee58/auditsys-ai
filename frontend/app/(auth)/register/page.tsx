import { Button } from "@/components/ui/button";

export default function RegisterPage() {
  return (
    <main className="flex min-h-screen items-center justify-center bg-ink px-4">
      <form className="w-full max-w-md rounded-md border border-line bg-panel p-6">
        <p className="text-xs uppercase tracking-[0.24em] text-accent">AuditSys AI</p>
        <h1 className="mt-2 font-display text-4xl font-bold">Create account</h1>
        <label className="mt-6 block text-sm text-zinc-300" htmlFor="name">
          Name
        </label>
        <input id="name" className="mt-2 w-full rounded-md border border-line bg-ink p-3" />
        <label className="mt-4 block text-sm text-zinc-300" htmlFor="email">
          Email
        </label>
        <input id="email" type="email" className="mt-2 w-full rounded-md border border-line bg-ink p-3" />
        <Button className="mt-6 w-full">Register</Button>
      </form>
    </main>
  );
}
