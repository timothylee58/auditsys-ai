import { DocumentTable } from "@/components/features/document-upload/document-table";
import { DocumentUploader } from "@/components/features/document-upload/DocumentUploader";
import { apiGet } from "@/lib/api";
import type { DocumentPage } from "@/types/audit";

export const dynamic = "force-dynamic";

export default async function DocumentsPage() {
  const { documents } = await apiGet<DocumentPage>("/documents");

  return (
    <section>
      <div className="flex flex-col justify-between gap-4 border-b border-line pb-6 sm:flex-row sm:items-end">
        <div>
          <p className="text-xs uppercase tracking-[0.24em] text-accent">Evidence vault</p>
          <h2 className="mt-2 font-display text-5xl font-bold">Documents</h2>
        </div>
      </div>
      <div className="mt-6">
        <DocumentUploader />
      </div>
      <div className="mt-6">
        <DocumentTable documents={documents} />
      </div>
    </section>
  );
}
