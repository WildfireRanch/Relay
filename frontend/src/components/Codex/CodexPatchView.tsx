// File: frontend/src/components/Codex/CodexPatchView.tsx
// Purpose: Displays the generated code patch/result from the Codex agent
// Updated: 2025-06-30

"use client";

interface Props {
  patch: string;
  loading?: boolean; // Optionally show loading state (prop-driven)
}

export default function CodexPatchView({ patch, loading = false }: Props) {
  return (
    <div className="mt-4">
      <label htmlFor="codex-patch" className="block text-sm font-medium mb-1">
        Generated Patch
      </label>
      <pre
        id="codex-patch"
        className="w-full max-h-[500px] overflow-auto bg-black text-green-400 p-4 rounded text-sm whitespace-pre-wrap"
        aria-busy={loading}
      >
        {loading
          ? "⏳ Codex is generating your patch..."
          : patch?.trim()
            ? patch
            : "No patch yet."}
      </pre>
    </div>
  );
}
