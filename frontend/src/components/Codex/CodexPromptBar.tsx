// File: frontend/src/components/Codex/CodexPromptBar.tsx
// Purpose: Prompt input bar for Codex code editing agent
// Updated: 2025-06-30

"use client";

import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";

interface Props {
  prompt: string;                 // Prompt/instruction for the code agent
  setPrompt: (val: string) => void; // Handler to update prompt in parent state
  onSubmit: () => void;           // Handler called when user submits
  loading?: boolean;              // Show loading state, disable input (prop-driven)
}

export default function CodexPromptBar({ prompt, setPrompt, onSubmit, loading = false }: Props) {
  // Handle Enter key to submit (unless Shift is held for multi-line, if ever needed)
  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter" && !e.shiftKey && prompt.trim() && !loading) {
      e.preventDefault();
      onSubmit();
    }
  };

  return (
    <div className="flex items-center gap-4">
      <Input
        value={prompt}
        onChange={(e) => setPrompt(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder="What should Codex do? (e.g., Add docstrings)"
        className="flex-1"
        disabled={loading}
      />
      <Button onClick={onSubmit} disabled={loading || !prompt.trim()}>
        {loading ? "Running..." : "Run"}
      </Button>
    </div>
  );
}
