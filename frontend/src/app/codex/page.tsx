"use client";

// File: src/app/codex/page.tsx

import React from "react";
import { useState } from "react";
import { CodexEditor, CodexPromptBar, CodexPatchView } from "@/components/Codex";
import { Button } from "@/components/ui/button";

const CodexPage: React.FC = () => {
  const [code, setCode] = useState<string>("");
  const [prompt, setPrompt] = useState<string>("");
  const [streamingPatch, setStreamingPatch] = useState<string>("");
  const [parsedPatch, setParsedPatch] = useState<{
    file: string;
    patch: string;
    reason: string;
  } | null>(null);
  const [status, setStatus] = useState<string>("");

  const handleSubmit = async (): Promise<void> => {
    setStreamingPatch("⏳ Working...");
    setParsedPatch(null);

    try {
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

      const fileMatch = patch.match(/File:\s*(.*)/);
      const reasonMatch = patch.match(/Reason:\s*([\s\S]*)/);
      const patchStart = patch.indexOf("Patch:");
      const reasonStart = patch.indexOf("Reason:");

      const extracted = {
        file: fileMatch?.[1]?.trim() || "",
        patch: patchStart !== -1 && reasonStart !== -1 ? patch.slice(patchStart + 6, reasonStart).trim() : "",
        reason: reasonMatch?.[1]?.trim() || ""
      };

      if (extracted.file && extracted.patch) setParsedPatch(extracted);
    } catch (err) {
      setStreamingPatch("❌ Error while generating patch");
    }
  };

  const applyPatch = async (): Promise<void> => {
    if (!parsedPatch) return;
    setStatus("⏳ Applying patch...");

    try {
      const res = await fetch("/codex/apply_patch", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          target_file: parsedPatch.file,
          patch: parsedPatch.patch,
          reason: parsedPatch.reason
        })
      });

      if (res.ok) {
        setStatus("✅ Patch applied successfully.");
      } else {
        const err = await res.text();
        setStatus("❌ Failed to apply patch: " + err);
      }
    } catch (err) {
      setStatus("❌ Patch request failed: " + String(err));
    }
  };

  return (
    <div className="p-6 space-y-4">
      <h1 className="text-2xl font-bold">🧠 Codex — Code Editing Agent</h1>

      <CodexEditor code={code} setCode={setCode} />
      <CodexPromptBar prompt={prompt} setPrompt={setPrompt} onSubmit={handleSubmit} />
      <CodexPatchView patch={streamingPatch} />

      {parsedPatch && (
        <div className="space-y-2">
          <Button onClick={applyPatch}>✅ Approve & Apply Patch</Button>
          {status && <div className="text-sm text-muted-foreground">{status}</div>}
        </div>
      )}
    </div>
  );
};

export default CodexPage;
