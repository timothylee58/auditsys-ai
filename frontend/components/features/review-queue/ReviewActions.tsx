"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";

export function ReviewActions({
  onApprove,
  onReject,
  onOverride,
}: {
  onApprove: () => Promise<void>;
  onReject: (reason: string) => Promise<void>;
  onOverride: (correctedAnswer: string, notes?: string) => Promise<void>;
}) {
  const [mode, setMode] = useState<"idle" | "reject" | "override">("idle");
  const [text, setText] = useState("");
  const [notes, setNotes] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function run(action: () => Promise<void>) {
    setIsSubmitting(true);
    try {
      await action();
      setMode("idle");
      setText("");
      setNotes("");
    } finally {
      setIsSubmitting(false);
    }
  }

  if (mode === "reject") {
    return (
      <div className="space-y-2">
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="Reason for rejection"
          className="w-full rounded-md border border-line bg-ink p-2 text-sm text-zinc-100 outline-none focus:border-accent"
        />
        <div className="flex gap-2">
          <Button type="button" disabled={!text.trim() || isSubmitting} onClick={() => run(() => onReject(text.trim()))}>
            Confirm reject
          </Button>
          <Button type="button" variant="secondary" onClick={() => setMode("idle")}>
            Cancel
          </Button>
        </div>
      </div>
    );
  }

  if (mode === "override") {
    return (
      <div className="space-y-2">
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="Corrected answer"
          className="w-full rounded-md border border-line bg-ink p-2 text-sm text-zinc-100 outline-none focus:border-accent"
        />
        <textarea
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          placeholder="Notes (optional)"
          className="w-full rounded-md border border-line bg-ink p-2 text-sm text-zinc-100 outline-none focus:border-accent"
        />
        <div className="flex gap-2">
          <Button
            type="button"
            disabled={text.trim().length < 10 || isSubmitting}
            onClick={() => run(() => onOverride(text.trim(), notes.trim() || undefined))}
          >
            Confirm override
          </Button>
          <Button type="button" variant="secondary" onClick={() => setMode("idle")}>
            Cancel
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="flex gap-2">
      <Button type="button" disabled={isSubmitting} onClick={() => run(onApprove)}>
        Approve
      </Button>
      <Button type="button" variant="secondary" onClick={() => setMode("reject")}>
        Reject
      </Button>
      <Button type="button" variant="secondary" onClick={() => setMode("override")}>
        Override
      </Button>
    </div>
  );
}
