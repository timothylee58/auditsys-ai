"use client";

import { ConfidenceBadge } from "./ConfidenceBadge";
import { SourceCitations } from "./SourceCitations";

interface Citation {
  document_id?: string;
  chunk_index?: number;
  content?: string;
  score?: number;
}

interface AnswerCardProps {
  answer: string;
  citations: Citation[];
  confidenceScore: number;
  traceId?: string;
}

/**
 * Renders the AI-generated answer with markdown support,
 * inline citation highlights, and confidence scoring.
 */
export function AnswerCard({ answer, citations, confidenceScore, traceId }: AnswerCardProps) {
  // Simple markdown-like rendering: bold, inline code, line breaks
  const renderAnswer = (text: string) => {
    const parts = text.split(/(\*\*.*?\*\*|`.*?`|\[(\d+)\])/g);
    return parts.map((part, idx) => {
      if (!part) return null;
      if (part.startsWith("**") && part.endsWith("**")) {
        return (
          <strong key={idx} className="font-semibold text-zinc-100">
            {part.slice(2, -2)}
          </strong>
        );
      }
      if (part.startsWith("`") && part.endsWith("`")) {
        return (
          <code key={idx} className="rounded bg-white/10 px-1.5 py-0.5 text-xs text-accent">
            {part.slice(1, -1)}
          </code>
        );
      }
      // Citation reference like [1], [2]
      if (/^\[\d+\]$/.test(part)) {
        return (
          <span
            key={idx}
            className="mx-0.5 inline-flex h-5 w-5 items-center justify-center rounded-full bg-accent/20 text-[10px] font-bold text-accent"
            title={`Citation ${part}`}
          >
            {part.replace(/[\[\]]/g, "")}
          </span>
        );
      }
      return <span key={idx}>{part}</span>;
    });
  };

  return (
    <div className="space-y-4">
      <article className="rounded-md border border-line bg-panel p-5">
        <div className="flex items-center justify-between">
          <p className="text-xs uppercase tracking-[0.18em] text-zinc-500">Answer</p>
          <ConfidenceBadge score={confidenceScore} />
        </div>
        <div className="mt-3 text-sm leading-7 text-zinc-200">
          {answer.split("\n").map((line, i) => (
            <p key={i} className={i > 0 ? "mt-2" : ""}>
              {renderAnswer(line)}
            </p>
          ))}
        </div>
        {traceId && (
          <p className="mt-4 text-[10px] text-zinc-600">
            Trace: {traceId}
          </p>
        )}
      </article>

      {citations.length > 0 && <SourceCitations citations={citations} />}
    </div>
  );
}
