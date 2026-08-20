import { apiGet } from "@/lib/api";
import type { AuditLogPage } from "@/types/audit";

export const dynamic = "force-dynamic";

export default async function AuditLogPage() {
  const { entries } = await apiGet<AuditLogPage>("/audit-log");

  return (
    <section>
      <p className="text-xs uppercase tracking-[0.24em] text-accent">Chain of custody</p>
      <h2 className="mt-2 font-display text-5xl font-bold">Audit Log</h2>
      <div className="mt-8 space-y-3">
        {entries.length === 0 && (
          <p className="rounded-md border border-line bg-panel/50 p-6 text-sm text-zinc-400">
            No queries have been logged yet.
          </p>
        )}
        {entries.map((entry) => (
          <article key={entry.id} className="rounded-md border border-line bg-panel p-4">
            <div className="flex items-center justify-between">
              <p className="text-sm text-zinc-300">
                <span className="font-medium text-zinc-50">{entry.query}</span>
              </p>
              <span
                className={
                  "shrink-0 rounded-full border px-2 py-0.5 text-xs " +
                  (entry.status === "answered"
                    ? "border-accent/40 text-accent"
                    : entry.status === "pending_review"
                      ? "border-yellow-700 text-yellow-400"
                      : "border-red-800 text-red-400")
                }
              >
                {entry.status.replace("_", " ")}
              </span>
            </div>
            <p className="mt-2 flex flex-wrap gap-3 text-xs text-zinc-500">
              <span>{new Date(entry.created_at).toLocaleString()}</span>
              {entry.confidence_score !== null && <span>Confidence {Math.round(entry.confidence_score * 100)}%</span>}
              {entry.model_name && <span>{entry.model_name}</span>}
              {entry.pii_detected && <span className="text-yellow-400">PII redacted</span>}
            </p>
          </article>
        ))}
      </div>
    </section>
  );
}
