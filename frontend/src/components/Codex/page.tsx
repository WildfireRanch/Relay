"use client";

import { CodexEditor, CodexPromptBar, CodexPatchView } from "@/components/Codex";
import { useState } from "react";

export default function CodexPage() {
  const [code, setCode] = useState("");
  const [prompt, setPrompt] = useState("");
  const [streamingPatch, setStreamingPatch] = useState("");

  return (
    <div className="p-6 space-y-4">
      <h1 className="text-2xl font-bold">🧠 Codex — Code Editing Agent</h1>
      <CodexEditor code={code} setCode={setCode} />
      <CodexPromptBar prompt={prompt} setPrompt={setPrompt} onSubmit={async () => {
        setStreamingPatch("⏳ Working...");
        const res = await fetch("/ask/codex_stream", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ question: prompt, context: code }),
        });

        const reader = res.body?.getReader();
        const decoder = new TextDecoder();
        let patch = "";
        while (true) {
          const { value, done } = await reader!.read();
          if (done) break;
          patch += decoder.decode(value, { stream: true });
          setStreamingPatch(patch);
        }
      }} />
      <CodexPatchView patch={streamingPatch} />
    </div>
  );
}
