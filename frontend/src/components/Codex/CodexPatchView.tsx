// File: frontend/src/components/Codex/CodexPatchView.tsx

"use client";

interface Props {
  patch: string;
}

export default function CodexPatchView({ patch }: Props) {
  return (
    <div className="mt-4">
      <label className="block text-sm font-medium mb-1">Generated Patch</label>
      <pre className="w-full max-h-[500px] overflow-auto bg-black text-green-400 p-4 rounded text-sm whitespace-pre-wrap">
        {patch || "No patch yet."}
      </pre>
    </div>
  );
}
