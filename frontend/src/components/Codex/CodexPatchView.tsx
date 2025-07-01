// File: frontend/src/components/Codex/CodexPatchView.tsx
// Purpose: Displays the generated code patch/result from the Codex agent.
//          All Markdown/code rendering MUST go through SafeMarkdown.
// Updated: 2025-07-01

"use client";

import SafeMarkdown from "@/components/SafeMarkdown";

interface Props {
  patch: string;
  loading?: boolean; // Optionally show loading state (prop-driven)
}

export default function CodexPatchView({ patch, loading = false }: Props) {
  if (typeof patch !== "string") {
    console.log("DEBUG 418:", typeof patch, patch);
  }
  return (
    <div className="mt-4">
      <label htmlFor="codex-patch" className="block text-sm font-medium mb-1">
        Generated Patch
      </label>
      <div
        id="codex-patch"
        className="w-full max-h-[500px] overflow-auto bg-black text-green-400 p-4 rounded text-sm whitespace-pre-wrap"
        aria-busy={loading}
      >
        {/* DO NOT render markdown/code any other way—SafeMarkdown only */}
        {loading ? (
          "⏳ Codex is generating your patch..."
        ) : patch?.trim() ? (
          <div className="prose prose-neutral dark:prose-invert max-w-none">
            <SafeMarkdown>{patch}</SafeMarkdown>
          </div>
        ) : (
          "No patch yet."
        )}
      </div>
    </div>
  );
}
