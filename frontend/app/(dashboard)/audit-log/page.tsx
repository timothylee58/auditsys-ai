import { apiGet } from "@/lib/api";
import type { AuditEvent } from "@/types/audit";

export const dynamic = "force-dynamic";

export default async function AuditLogPage() {
  const events = await apiGet<AuditEvent[]>("/audit-log");

  return (
    <section>
      <p className="text-xs uppercase tracking-[0.24em] text-accent">Chain of custody</p>
      <h2 className="mt-2 font-display text-5xl font-bold">Audit Log</h2>
      <div className="mt-8 space-y-3">
        {events.map((event) => (
          <article key={event.id} className="rounded-md border border-line bg-panel p-4">
            <p className="text-sm text-zinc-300">
              <span className="font-medium text-zinc-50">{event.actor}</span> {event.action}{" "}
              <span className="text-accent">{event.target}</span>
            </p>
            <p className="mt-2 text-xs text-zinc-500">{event.createdAt}</p>
          </article>
        ))}
      </div>
    </section>
  );
}
