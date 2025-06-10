"use client";
// File: frontend/src/app/ask/page.tsx

import React, { useState, useRef, useEffect } from "react";

type Message = {
  role: "user" | "assistant";
  content: string;
};

const USER_ID = "bret-demo"; // Replace with your actual auth/user logic later

export default function AskEchoPage() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  // Scroll to bottom on new message
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // Submit handler
  async function sendMessage(e: React.FormEvent) {
    e.preventDefault();
    if (!input.trim()) return;

    // Add user's message
    setMessages((msgs) => [...msgs, { role: "user", content: input }]);
    setLoading(true);

    try {
      // POST to backend with X-User-Id header
      const res = await fetch("/ask", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-User-Id": USER_ID,
        },
        body: JSON.stringify({ question: input }),
      });
      const data = await res.json();
      setMessages((msgs) => [
        ...msgs,
        { role: "assistant", content: data.response || "[no response]" },
      ]);
    } catch {
      setMessages((msgs) => [
        ...msgs,
        { role: "assistant", content: "[error] Unable to get response." },
      ]);
    }
    setInput("");
    setLoading(false);
  }

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
            <span className="block whitespace-pre-wrap">{msg.content}</span>
          </div>
        ))}
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
          onChange={(e) => setInput(e.target.value)}
          disabled={loading}
          name="echo-message"
          id="echo-message"
        />
        <button
          type="submit"
          className="bg-blue-600 text-white rounded px-4 py-2"
          disabled={loading || !input.trim()}
        >
          {loading ? "Sending…" : "Send"}
        </button>
      </form>
    </div>
  );
}
