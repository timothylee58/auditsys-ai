"use client";

import { FormEvent } from "react";
import { Button } from "@/components/ui/button";

interface QueryInputProps {
  question: string;
  onQuestionChange: (value: string) => void;
  onSubmit: (e: FormEvent) => void;
  isLoading: boolean;
  maxLength?: number;
}

/**
 * Reusable query input component with character counter and validation.
 */
export function QueryInput({
  question,
  onQuestionChange,
  onSubmit,
  isLoading,
  maxLength = 2000,
}: QueryInputProps) {
  const charCount = question.length;
  const isOverLimit = charCount > maxLength;
  const isValid = question.trim().length >= 5 && !isOverLimit;

  return (
    <form onSubmit={onSubmit} className="rounded-md border border-line bg-panel p-4">
      <div className="flex items-center justify-between">
        <label htmlFor="query-input" className="text-sm font-medium text-zinc-200">
          Query
        </label>
        <span className={`text-xs ${isOverLimit ? "text-red-400" : "text-zinc-500"}`}>
          {charCount}/{maxLength}
        </span>
      </div>
      <textarea
        id="query-input"
        value={question}
        onChange={(e) => onQuestionChange(e.target.value)}
        className="mt-3 min-h-40 w-full rounded-md border border-line bg-ink p-4 text-zinc-100 outline-none focus:border-accent"
        placeholder="Find policy exceptions with source evidence..."
        maxLength={maxLength}
      />
      <div className="mt-4 flex justify-end">
        <Button type="submit" disabled={isLoading || !isValid}>
          {isLoading ? "Running..." : "Run query"}
        </Button>
      </div>
    </form>
  );
}
