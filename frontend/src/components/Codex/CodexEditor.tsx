// File: src/components/Codex/CodexEditor.tsx
// Purpose: Simple text/code editor for Codex agent
// Updated: 2025-06-30

import { Dispatch, SetStateAction } from "react";

export interface Props {
  code: string; // Source code being edited
  setCode: Dispatch<SetStateAction<string>>; // Update function
}

export default function CodexEditor({ code, setCode }: Props) {
  return (
    <div>
      <label htmlFor="codex-editor" className="block text-sm font-medium mb-1">
        Source Code
      </label>
      <textarea
        id="codex-editor"
        value={code}
        onChange={(e) => setCode(e.target.value)}
        className="w-full h-48 p-2 border rounded font-mono resize-y"
        spellCheck={false}
        placeholder="Paste or type your code here…"
        aria-label="Code input for Codex"
      />
    </div>
  );
}
