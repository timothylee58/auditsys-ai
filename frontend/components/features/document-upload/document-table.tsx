import type { DocumentRecord } from "@/types/audit";

export function DocumentTable({ documents }: { documents: DocumentRecord[] }) {
  if (documents.length === 0) {
    return (
      <p className="rounded-md border border-line bg-panel/50 p-6 text-sm text-zinc-400">
        No documents indexed yet. Upload a PDF to get started.
      </p>
    );
  }

  return (
    <div className="overflow-hidden rounded-md border border-line">
      <table className="w-full border-collapse text-left text-sm">
        <thead className="bg-white/5 text-xs uppercase tracking-[0.18em] text-zinc-400">
          <tr>
            <th className="px-4 py-3">Document</th>
            <th className="px-4 py-3">Status</th>
            <th className="px-4 py-3">Chunks</th>
            <th className="px-4 py-3">Uploaded</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-line">
          {documents.map((document) => (
            <tr key={document.id} className="bg-panel/50">
              <td className="px-4 py-4 font-medium text-zinc-100">{document.filename}</td>
              <td className="px-4 py-4 text-zinc-300">{document.status.replace("_", " ")}</td>
              <td className="px-4 py-4 text-accent">{document.chunk_count}</td>
              <td className="px-4 py-4 text-zinc-400">{new Date(document.created_at).toLocaleString()}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
