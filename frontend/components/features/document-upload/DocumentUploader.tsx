"use client";

import { useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { apiUpload } from "@/lib/api";

export function DocumentUploader() {
  const inputRef = useRef<HTMLInputElement>(null);
  const router = useRouter();
  const [isUploading, setIsUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;

    setIsUploading(true);
    setError(null);
    try {
      await apiUpload("/documents/upload", file);
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setIsUploading(false);
      if (inputRef.current) inputRef.current.value = "";
    }
  }

  return (
    <div className="rounded-md border border-dashed border-line bg-panel p-6">
      <p className="text-sm text-zinc-300">Upload audit evidence documents (PDF, up to 20MB) for indexing.</p>
      <input
        ref={inputRef}
        type="file"
        accept="application/pdf"
        className="hidden"
        onChange={handleFileChange}
      />
      <Button className="mt-4" type="button" disabled={isUploading} onClick={() => inputRef.current?.click()}>
        {isUploading ? "Uploading…" : "Select files"}
      </Button>
      {error && <p className="mt-3 text-sm text-red-400">{error}</p>}
    </div>
  );
}
