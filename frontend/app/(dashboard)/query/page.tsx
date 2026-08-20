"use client";

import { FormEvent, useState } from "react";
import { Button } from "@/components/ui/button";
import { useAuditQuery } from "@/hooks/useQuery";

export default function QueryPage() {
  const [question, setQuestion] = useState("");
  const { result, pollStatus, isLoading, error, runQuery } = useAuditQuery();

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (question.trim()) runQuery(question.trim());
  }

  const isPending = result?.status === "pending_review" && pollStatus?.status !== "answered" && pollStatus?.status !== "rejected";
  const displayAnswer = pollStatus?.answer ?? result?.answer;

  return (
    <section>
      <p className="text-xs uppercase tracking-[0.24em] text-accent">Grounded search</p>
      <h2 className="mt-2 font-display text-5xl font-bold">Ask the audit file</h2>

      <form onSubmit={handleSubmit} className="mt-8 rounded-md border border-line bg-panel p-4">
        <label htmlFor="query" className="text-sm font-medium text-zinc-200">
          Query
        </label>
        <textarea
          id="query"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          className="mt-3 min-h-40 w-full rounded-md border border-line bg-ink p-4 text-zinc-100 outline-none focus:border-accent"
          placeholder="Find policy exceptions with source evidence..."
        />
        <div className="mt-1 text-right text-xs text-zinc-500">{question.length}/2000</div>
        <div className="mt-4 flex justify-end">
          <Button type="submit" disabled={isLoading || !question.trim()}>
            {isLoading ? "Running…" : "Run query"}
          </Button>
        </div>
      </form>

      {error && (
        <p className="mt-4 rounded-md border border-red-800 bg-red-950/40 p-3 text-sm text-red-400">{error}</p>
      )}

      {result && (
        <div className="mt-6 space-y-4">
          {isPending && (
            <p className="rounded-md border border-yellow-700 bg-yellow-950/40 p-3 text-sm text-yellow-400">
              Your answer is being reviewed by our compliance team.
            </p>
          )}
          {pollStatus?.status === "rejected" && (
            <p className="rounded-md border border-red-800 bg-red-950/40 p-3 text-sm text-red-400">
              This answer was rejected on review. {pollStatus.review_note}
            </p>
          )}
          {!isPending && pollStatus?.status !== "rejected" && (
            <article className="rounded-md border border-line bg-panel p-5">
              <div className="flex items-center justify-between">
                <p className="text-xs uppercase tracking-[0.18em] text-zinc-500">Answer</p>
                <span className="text-xs text-zinc-400">
                  Confidence{" "}
                  <span className={result.confidence_score >= 0.75 ? "text-accent" : "text-yellow-400"}>
                    {Math.round(result.confidence_score * 100)}%
                  </span>
                </span>
              </div>
              <p className="mt-3 text-sm leading-7 text-zinc-200">{displayAnswer}</p>
            </article>
          )}

          {result.citations.length > 0 && (
            <div>
              <p className="mb-2 text-xs uppercase tracking-[0.18em] text-zinc-500">Sources</p>
              <ul className="space-y-2">
                {result.citations.map((src, i) => (
                  <li key={`${src.document_id}-${i}`} className="rounded-md border border-line bg-panel/60 p-3 text-sm text-zinc-300">
                    Document {src.document_id?.slice(0, 8)} · page {src.page_number ?? "—"}
                    {typeof src.similarity === "number" && (
                      <span className="ml-2 text-xs text-zinc-500">{Math.round(src.similarity * 100)}% match</span>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </section>
  );
}
