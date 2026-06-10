export function SourceCitations({ sources = [] }: { sources?: string[] }) {
  return (
    <ol className="space-y-2 text-sm text-zinc-400">
      {sources.map((source) => (
        <li key={source}>{source}</li>
      ))}
    </ol>
  );
}
