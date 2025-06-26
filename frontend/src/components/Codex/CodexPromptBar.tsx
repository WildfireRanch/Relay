// File: frontend/src/components/Codex/CodexPromptBar.tsx
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { useState } from "react";

interface Props {
  prompt: string;
  setPrompt: (val: string) => void;
  onSubmit: () => void;
}

export default function CodexPromptBar({ prompt, setPrompt, onSubmit }: Props) {
  const [loading, setLoading] = useState(false);

  const handleSubmit = async () => {
    setLoading(true);
    await onSubmit();
    setLoading(false);
  };

  return (
    <div className="flex items-center gap-4">
      <Input
        value={prompt}
        onChange={(e) => setPrompt(e.target.value)}
        onKeyDown={(e) => e.key === "Enter" && handleSubmit()}
        placeholder="What should Codex do? e.g., Add docstrings"
        className="flex-1"
      />
      <Button onClick={handleSubmit} disabled={loading}>
        {loading ? "Running..." : "Run"}
      </Button>
    </div>
  );
}
