"use client";

import { useCallback, useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { apiGet, apiPost } from "@/lib/api";

interface EvalRun {
  id: string;
  run_id: string;
  dataset_name: string;
  faithfulness: number | null;
  answer_relevancy: number | null;
  context_recall: number | null;
  context_precision: number | null;
  status: string;
  created_at: string;
}

const METRIC_LABELS: Record<string, string> = {
  faithfulness: "Faithfulness",
  answer_relevancy: "Answer relevancy",
  context_recall: "Context recall",
  context_precision: "Context precision",
};

export default function EvalsPage() {
  const [runs, setRuns] = useState<EvalRun[]>([]);
  const [isRunning, setIsRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const { runs } = await apiGet<{ runs: EvalRun[] }>("/evals/results");
      setRuns(runs);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load eval results");
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  async function runEvals() {
    setIsRunning(true);
    setError(null);
    try {
      const { job_id } = await apiPost<{ job_id: string }>("/evals/run");
      await pollJob(job_id);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Eval run failed");
    } finally {
      setIsRunning(false);
    }
  }

  async function pollJob(jobId: string, attempt = 0): Promise<void> {
    if (attempt > 120) return; // ~10 minutes at 5s intervals
    const job = await apiGet<{ status: string }>(`/evals/run/${jobId}`);
    if (job.status === "completed" || job.status === "failed") return;
    await new Promise((resolve) => setTimeout(resolve, 5000));
    return pollJob(jobId, attempt + 1);
  }

  const latest = runs[0];
  const previous = runs[1];

  return (
    <section>
      <div className="flex flex-col justify-between gap-4 border-b border-line pb-6 sm:flex-row sm:items-end">
        <div>
          <p className="text-xs uppercase tracking-[0.24em] text-accent">Quality gates</p>
          <h2 className="mt-2 font-display text-5xl font-bold">Evaluation Dashboard</h2>
        </div>
        <Button type="button" disabled={isRunning} onClick={runEvals}>
          {isRunning ? "Running…" : "Run Evals"}
        </Button>
      </div>

      {error && <p className="mt-4 text-sm text-red-400">{error}</p>}

      {latest ? (
        <div className="mt-8 grid gap-4 md:grid-cols-4">
          {Object.entries(METRIC_LABELS).map(([key, label]) => {
            const score = latest[key as keyof EvalRun] as number | null;
            const prevScore = previous?.[key as keyof EvalRun] as number | null | undefined;
            const trend = score != null && prevScore != null ? score - prevScore : null;
            return (
              <article key={key} className="rounded-md border border-line bg-panel p-6">
                <p className="text-sm text-zinc-400">{label}</p>
                <p className="mt-3 font-display text-5xl font-bold text-accent">
                  {score != null ? `${Math.round(score * 100)}%` : "—"}
                </p>
                {trend != null && (
                  <p className={trend >= 0 ? "mt-2 text-xs text-accent" : "mt-2 text-xs text-red-400"}>
                    {trend >= 0 ? "▲" : "▼"} {Math.abs(Math.round(trend * 100))}pt vs last run
                  </p>
                )}
              </article>
            );
          })}
        </div>
      ) : (
        <p className="mt-8 rounded-md border border-line bg-panel/50 p-6 text-sm text-zinc-400">
          No eval runs yet. Click &ldquo;Run Evals&rdquo; to score the agent against the golden dataset.
        </p>
      )}

      {runs.length > 0 && (
        <div className="mt-8">
          <p className="mb-2 text-xs uppercase tracking-[0.18em] text-zinc-500">History</p>
          <ul className="space-y-2">
            {runs.map((run) => (
              <li key={run.id} className="rounded-md border border-line bg-panel/60 p-3 text-sm text-zinc-300">
                {new Date(run.created_at).toLocaleString()} · {run.dataset_name} · {run.status}
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
