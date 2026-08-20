import type { AuditEvent } from "@/types/audit";

export function AuditTable({ events }: { events: AuditEvent[] }) {
  return (
    <div className="divide-y divide-line rounded-md border border-line">
      {events.map((event) => (
        <div key={event.id} className="p-4 text-sm text-zinc-300">
          {event.query} — {event.status}
        </div>
      ))}
    </div>
  );
}
