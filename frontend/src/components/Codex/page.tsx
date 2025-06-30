// File: frontend/src/components/Codex/CodexPage.tsx
// Purpose: UI for Codex agent with code editor, prompt bar, and streaming patch view
// Updated: 2025-06-30

"use client";

import { CodexEditor, CodexPromptBar, CodexPatchView } from "@/components/Codex";
import { useState } from "react";
import { API_ROOT } from "@/lib/api";

export default function CodexPage() {
  const [code, setCode] = useState("");           // User's source code
  const [prompt, setPrompt] = useState("");       // Editing instruction (prompt)
  const [streamingPatch, setStreamingPatch] = useState(""); // Live code patch output
  const [loading, setLoading] = useState(false);  // Loading state for UX

  // Handler for submitting the edit prompt to the Codex agent
  const handleSubmit = async () => {
    if (!prompt.trim() || !code.trim() || loading) return;

    setStreamingPatch("⏳ Working...");
    setLoading(true);

    try {
      const res = await fetch(`${API_ROOT}/ask/codex_stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: prompt, context: code }),
      });

      const reader = res.body?.getReader();
      const decoder = new TextDecoder();
      let patch = "";

      while (reader) {
        const { value, done } = await reader.read();
        if (done) break;
        patch += decoder.decode(value, { stream: true });
        setStreamingPatch(patch);
      }
    } catch {
      setStreamingPatch("❌ Error streaming patch from Codex agent.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="p-6 space-y-4">
      <h1 className="text-2xl font-bold">🧠 Codex — Code Editing Agent</h1>
      {/* Code input area */}
      <CodexEditor code={code} setCode={setCode} />

      {/* Prompt bar for edit instructions */}
      <CodexPromptBar
        prompt={prompt}
        setPrompt={setPrompt}
        onSubmit={handleSubmit}
        loading={loading}
      />

      {/* Patch/result area */}
      <CodexPatchView patch={streamingPatch} loading={loading} />
    </div>
  );
}
