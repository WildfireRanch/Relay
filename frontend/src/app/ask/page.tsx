// File: app/ask/page.tsx
"use client";

import React, { useState, useRef, useEffect, useCallback } from "react";
import SafeMarkdown from "@/components/SafeMarkdown";
import { API_ROOT } from "@/lib/api";

// Message type
type Message = {
  role: "user" | "assistant";
  content: string;
  context?: string;
};

const USER_ID = "bret-demo";
const STORAGE_KEY = `echo-chat-history-${USER_ID}`;

// Helper to coerce any loaded array into Message[]
function normalizeMessages(arr: unknown[]): Message[] {
  return Array.isArray(arr)
    ? arr
        .filter(
  (msg: unknown): msg is { role?: unknown; content?: unknown; context?: unknown } =>
    typeof msg === "object" &&
    msg !== null &&
    "content" in msg &&
    typeof (msg as { content?: unknown }).content === "string"
)
        .map((msg) => ({
          role:
            msg.role === "user" || msg.role === "assistant"
              ? msg.role
              : "assistant",
          content: String(msg.content),
          ...(typeof msg.context === "string" && { context: msg.context }),
        }))
    : [];
}

// Markdown stringifier (bulletproof)
function toMDString(val: unknown): string {
  if (val == null) return "";
  if (typeof val === "string") return val;
  if (Array.isArray(val)) return val.map(toMDString).join("\n\n");
  try {
    return "```json\n" + JSON.stringify(val, null, 2) + "\n```";
  } catch {
    return String(val);
  }
}

export default function AskPage() {
  const [messages, setMessages] = useState<Message[]>(() => {
    if (typeof window !== "undefined") {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (raw) {
        try {
          return normalizeMessages(JSON.parse(raw));
        } catch {
          return [];
        }
      }
    }
    return [];
  });

  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (typeof window !== "undefined") {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(messages));
    }
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const sendMessage = useCallback(async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!input.trim() || loading) return;

    const userMessage = input;
    setMessages(msgs => [
      ...msgs,
      { role: "user", content: toMDString(userMessage) }
    ]);
    setLoading(true);
    setInput("");

    try {
      const res = await fetch(`${API_ROOT}/mcp/run`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-User-Id": USER_ID,
        },
        body: JSON.stringify({
          query: userMessage,
          role: "planner",
          debug: true,
        }),
      });

      const data = await res.json();
      const result = data?.result || data;

      const content =
        result?.plan?.objective ||
        result?.plan?.recommendation ||
        result?.recommendation ||
        result?.response ||
        data?.response ||
        "[no answer]";

      setMessages(msgs => [
        ...msgs,
        { role: "assistant", content: toMDString(content) }
      ]);
    } catch {
      setMessages(msgs => [
        ...msgs,
        { role: "assistant", content: toMDString("[error] Unable to get response.") }
      ]);
    }

    setLoading(false);
  }, [input, loading]);

  return (
    <div className="w-full max-w-2xl mx-auto min-h-screen flex flex-col">
      <h1 className="text-3xl font-bold my-4">Ask Echo</h1>
      <div className="flex-1 space-y-2 overflow-y-auto border rounded-xl p-4 bg-muted">
        {messages.map((msg, i) => (
          <div
            key={i}
            className={
              msg.role === "user"
                ? "text-right text-blue-700"
                : "text-left text-green-700"
            }
          >
            <div className="prose prose-neutral dark:prose-invert max-w-none">
              <SafeMarkdown>{msg.content}</SafeMarkdown>
            </div>
          </div>
        ))}
        {loading && (
          <div className="text-left text-green-700 animate-pulse">
            <span className="block whitespace-pre-wrap">Echo is thinking…</span>
          </div>
        )}
        <div ref={bottomRef} />
      </div>
      <form
        onSubmit={sendMessage}
        className="flex items-center gap-2 mt-4"
        autoComplete="off"
      >
        <input
          type="text"
          className="flex-1 rounded border px-3 py-2"
          placeholder="Type your question…"
          value={input}
          onChange={e => setInput(e.target.value)}
          disabled={loading}
          name="echo-message"
          id="echo-message"
          onKeyDown={e => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              sendMessage();
            }
          }}
        />
        <button
          type="submit"
          className="bg-blue-600 text-white rounded px-4 py-2"
          disabled={loading || !input.trim()}
        >
          {loading ? "Sending…" : "Send"}
        </button>
      </form>
      <div className="text-xs text-gray-400 text-center mt-2">
        API root: <span className="font-mono">{API_ROOT}</span>
      </div>
    </div>
  );
}
