// File: components/AskAgent/ChatMessage.tsx

import React from "react";
import SafeMarkdown from "@/components/SafeMarkdown"; // Use the shared safe renderer

type Props = {
  role: "user" | "assistant";
  content: string;
};

export default function ChatMessage({ role, content }: Props) {
  const alignClass =
    role === "user" ? "text-right text-blue-700" : "text-left text-green-700";

  return (
    <div className={alignClass}>
      <SafeMarkdown>{content}</SafeMarkdown>
    </div>
  );
}
