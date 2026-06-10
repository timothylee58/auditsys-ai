import { Button } from "@/components/ui/button";

export function DocumentUploader() {
  return (
    <div className="rounded-md border border-dashed border-line bg-panel p-6">
      <p className="text-sm text-zinc-300">Upload audit evidence documents for indexing.</p>
      <Button className="mt-4" type="button">
        Select files
      </Button>
    </div>
  );
}
