// File: src/app/codex/page.tsx
"use client";

import { useState } from "react";
import CodexPatchView from "@/components/Codex/CodexPatchView";
import { Button } from "@/components/ui/button";

export default function CodexPage() {
  const [patch, setPatch] = useState<string>("");

  const generatePatch = async () => {
    // Replace this with actual API call to Codex agent
    const res = await fetch("/api/codex/mock", {
      method: "POST",
      body: JSON.stringify({ prompt: "example code" }),
    });
    const data = await res.json();
    setPatch(data.patch || "No patch generated.");
  };

  return (
    <div className="p-6">
      <h1 className="text-2xl font-semibold mb-4">Codex Agent</h1>
      <Button onClick={generatePatch}>Generate Patch</Button>
      <CodexPatchView patch={patch} />
    </div>
  );
}
