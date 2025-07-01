// File: components/AskAgent/ChatMessage.tsx
// Purpose: Renders a single chat message, always string-coercing content for SafeMarkdown.

import React from "react";
import SafeMarkdown from "@/components/SafeMarkdown"; // Use the shared safe renderer

type Props = {
  role: "user" | "assistant";
  content: any; // Accept anything, always coerce to string for safety
};

// Defensive: always return a string for SafeMarkdown
function toMDString(val: any): string {
  if (val == null) return "";
  if (typeof val === "string") return val;
  try {
    return "```json\n" + JSON.stringify(val, null, 2) + "\n```";
  } catch {
    return String(val);
  }
}

export default function ChatMessage({ role, content }: Props) {
  const alignClass =
    role === "user" ? "text-right text-blue-700" : "text-left text-green-700";

  return (
    <div className={alignClass}>
      <SafeMarkdown>{toMDString(content)}</SafeMarkdown>
    </div>
  );
}
