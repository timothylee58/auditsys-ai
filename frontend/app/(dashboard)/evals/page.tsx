"use client";

import { useCallback, useEffect, useState } from "react";
import { Button } from "@/components/ui/button";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

interface EvalResult {
  id: string;
  status: string;
  started_at: string;
  completed_at?: string;
  metrics: Record<string, number>;
}

interface MetricCard {
  label: string;
  key: string;
  current: number;
  previous: number | null;
}

export default function EvalsPage() {
  const [results, setResults] = useState<EvalResult[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isRunning, setIsRunning] = useState(false);

  const fetchResults = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE_URL}/evals/results`);
      if (res.ok) {
        const data = await res.json();
        setResults(data.results || []);
      }
    } catch {
      // silent
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchResults();
  }, [fetchResults]);

  const handleRunEvals = async () => {
    setIsRunning(true);
    try {
      const res = await fetch(`${API_BASE_URL}/evals/run`, { method: "POST" });
      if (res.ok) {
        // Wait a moment then refresh
        setTimeout(() => fetchResults(), 2000);
      }
    } catch {
      // silent
    } finally {
      setIsRunning(false);
    }
  };

  // Compute metric cards from latest two runs
  const latestRun = results[0];
  const previousRun = results.length > 1 ? results[1] : null;

  const metricCards: MetricCard[] = [
    {
      label: "Faithfulness",
      key: "faithfulness",
      current: latestRun?.metrics?.faithfulness ?? 0,
      previous: previousRun?.metrics?.faithfulness ?? null,
    },
    {
      label: "Answer Relevancy",
      key: "answer_relevancy",
      current: latestRun?.metrics?.answer_relevancy ?? 0,
      previous: previousRun?.metrics?.answer_relevancy ?? null,
    },
    {
      label: "Context Recall",
      key: "context_recall",
      current: latestRun?.metrics?.context_recall ?? 0,
      previous: previousRun?.metrics?.context_recall ?? null,
    },
  ];

  const getTrend = (current: number, previous: number | null) => {
    if (previous === null) return null;
    const diff = current - previous;
    if (Math.abs(diff) < 0.01) return { direction: "flat" as const, value: 0 };
    return { direction: diff > 0 ? ("up" as const) : ("down" as const), value: Math.abs(diff) };
  };

  return (
    <section>
      <div className="flex items-center justify-between">
        <div>
          <p className="text-xs uppercase tracking-[0.24em] text-accent">Quality gates</p>
          <h2 className="mt-2 font-display text-5xl font-bold">Evaluation Dashboard</h2>
        </div>
        <Button onClick={handleRunEvals} disabled={isRunning}>
          {isRunning ? "Running..." : "Run Evals"}
        </Button>
      </div>

      {/* Score Cards */}
      <div className="mt-8 grid gap-4 md:grid-cols-3">
        {metricCards.map((metric) => {
          const trend = getTrend(metric.current, metric.previous);
          return (
            <article key={metric.key} className="rounded-md border border-line bg-panel p-6">
              <p className="text-sm text-zinc-400">{metric.label}</p>
              <div className="mt-3 flex items-end gap-2">
                <p className="font-display text-5xl font-bold text-accent">
                  {metric.current > 0 ? `${Math.round(metric.current * 100)}%` : "--"}
                </p>
                {trend && (
                  <span
                    className={`mb-1 flex items-center gap-0.5 text-xs font-medium ${
                      trend.direction === "up"
                        ? "text-emerald-400"
                        : trend.direction === "down"
                          ? "text-red-400"
                          : "text-zinc-500"
                    }`}
                  >
                    {trend.direction === "up" && (
                      <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 17l5-5 5 5M7 7l5 5 5-5" />
                      </svg>
                    )}
                    {trend.direction === "down" && (
                      <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 7l-5 5-5-5m0 10l5-5 5 5" />
                      </svg>
                    )}
                    {trend.value > 0 && `${(trend.value * 100).toFixed(1)}%`}
                  </span>
                )}
              </div>
            </article>
          );
        })}
      </div>

      {/* Historical Chart (simplified without recharts dependency) */}
      <div className="mt-8 rounded-md border border-line bg-panel p-6">
        <h3 className="text-sm font-medium text-zinc-300">Historical Scores</h3>
        {results.length === 0 ? (
          <p className="mt-4 text-sm text-zinc-500">
            No evaluation runs yet. Click &quot;Run Evals&quot; to generate baseline scores.
          </p>
        ) : (
          <div className="mt-4 space-y-3">
            {results.slice(0, 10).map((run) => (
              <div key={run.id} className="flex items-center gap-4 text-sm">
                <span className="w-36 text-xs text-zinc-500">
                  {run.completed_at
                    ? new Date(run.completed_at).toLocaleDateString()
                    : new Date(run.started_at).toLocaleDateString()}
                </span>
                <div className="flex flex-1 gap-3">
                  {Object.entries(run.metrics || {}).map(([key, value]) => (
                    <div key={key} className="flex items-center gap-1">
                      <div className="h-2 w-16 overflow-hidden rounded-full bg-zinc-700">
                        <div
                          className="h-full rounded-full bg-accent"
                          style={{ width: `${(value as number) * 100}%` }}
                        />
                      </div>
                      <span className="text-[10px] text-zinc-500">
                        {key.replace("_", " ").slice(0, 8)}
                      </span>
                    </div>
                  ))}
                </div>
                <span
                  className={`rounded-full px-2 py-0.5 text-[10px] font-medium ${
                    run.status === "completed"
                      ? "bg-emerald-500/20 text-emerald-400"
                      : "bg-amber-500/20 text-amber-400"
                  }`}
                >
                  {run.status}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </section>
  );
}
