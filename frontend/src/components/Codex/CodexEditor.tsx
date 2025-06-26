// File: frontend/src/components/Codex/CodexEditor.tsx
"use client";

import { Textarea } from "@/components/ui/textarea";

interface Props {
  code: string;
  setCode: (val: string) => void;
}

export default function CodexEditor({ code, setCode }: Props) {
  return (
    <div>
      <label className="block text-sm font-medium mb-1">Code Context</label>
      <Textarea
        value={code}
        onChange={(e) => setCode(e.target.value)}
        className="w-full min-h-[200px] font-mono text-sm bg-gray-50"
        placeholder="Paste your code here..."
      />
    </div>
  );
}
