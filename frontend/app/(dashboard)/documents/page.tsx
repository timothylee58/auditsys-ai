import { DocumentTable } from "@/components/features/document-upload/document-table";
import { Button } from "@/components/ui/button";
import { apiGet } from "@/lib/api";
import type { DocumentRecord } from "@/types/audit";

export const dynamic = "force-dynamic";

export default async function DocumentsPage() {
  const documents = await apiGet<DocumentRecord[]>("/documents");

  return (
    <section>
      <div className="flex flex-col justify-between gap-4 border-b border-line pb-6 sm:flex-row sm:items-end">
        <div>
          <p className="text-xs uppercase tracking-[0.24em] text-accent">Evidence vault</p>
          <h2 className="mt-2 font-display text-5xl font-bold">Documents</h2>
        </div>
        <Button>Upload document</Button>
      </div>
      <div className="mt-6">
        <DocumentTable documents={documents} />
      </div>
    </section>
  );
}
