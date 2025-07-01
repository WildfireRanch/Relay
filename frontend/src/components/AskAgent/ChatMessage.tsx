// File: components/AskAgent/ChatMessage.tsx
// Purpose: Renders a single chat message, always string-coercing content for SafeMarkdown.

import React from "react";
import SafeMarkdown from "@/components/SafeMarkdown"; // Use the shared safe renderer
import { toMDString } from "@/lib/toMDString";

type Props = {
  role: "user" | "assistant";
  content: unknown; // Accept anything, always coerce to string for safety
};


export default function ChatMessage({ role, content }: Props) {
  const alignClass =
    role === "user" ? "text-right text-blue-700" : "text-left text-green-700";

  return (
    <div className={alignClass}>
      <div className="prose prose-neutral dark:prose-invert max-w-none">
        {typeof content !== "string" &&
          console.log("DEBUG 418:", typeof content, content)}
        <SafeMarkdown>{toMDString(content)}</SafeMarkdown>
      </div>
    </div>
  );
}
