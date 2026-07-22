"use client";

interface Citation {
  document_id?: string;
  chunk_index?: number;
  content?: string;
  score?: number;
}

interface SourceCitationsProps {
  citations: Citation[];
}

/**
 * Renders source citations for an AI-generated answer.
 * Each citation shows the source document reference and a content excerpt.
 */
export function SourceCitations({ citations }: SourceCitationsProps) {
  if (citations.length === 0) return null;

  return (
    <div>
      <p className="mb-2 text-xs uppercase tracking-[0.18em] text-zinc-500">
        Sources ({citations.length})
      </p>
      <ul className="space-y-2">
        {citations.map((citation, idx) => (
          <li
            key={`${citation.document_id}-${citation.chunk_index}-${idx}`}
            className="rounded-md border border-line bg-panel/60 p-3"
          >
            <div className="flex items-center justify-between">
              <span className="inline-flex items-center gap-2 text-xs font-medium text-zinc-300">
                <span className="flex h-5 w-5 items-center justify-center rounded-full bg-accent/20 text-[10px] font-bold text-accent">
                  {idx + 1}
                </span>
                {citation.document_id
                  ? `Document: ${citation.document_id.slice(0, 8)}...`
                  : `Source ${idx + 1}`}
              </span>
              {citation.score !== undefined && (
                <span className="text-[10px] text-zinc-500">
                  relevance: {Math.round(citation.score * 100)}%
                </span>
              )}
            </div>
            {citation.content && (
              <p className="mt-2 text-xs leading-5 text-zinc-400">
                {citation.content.length > 200
                  ? `${citation.content.slice(0, 200)}...`
                  : citation.content}
              </p>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
