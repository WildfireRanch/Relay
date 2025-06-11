"use client";
// File: app/ask/page.tsx
// Directory: frontend/src/app/ask

import React, { useState, useRef, useEffect } from "react";
import ReactMarkdown from "react-markdown";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { vscDarkPlus } from "react-syntax-highlighter/dist/esm/styles/prism"; // use cjs if esm fails
import { API_ROOT } from "@/lib/api";

type Message = {
  role: "user" | "assistant";
  content: string;
};

const USER_ID = "bret-demo"; // Replace with real auth/user logic later
const STORAGE_KEY = `echo-chat-history-${USER_ID}`;

export default function AskEchoPage() {
  const [messages, setMessages] = useState<Message[]>(() => {
    if (typeof window !== "undefined") {
      const raw = localStorage.getItem(STORAGE_KEY);
      return raw ? JSON.parse(raw) : [];
    }
    return [];
  });
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [streaming, setStreaming] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (typeof window !== "undefined") {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(messages));
    }
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  async function sendMessage(e?: React.FormEvent) {
    if (e) e.preventDefault();
    if (!input.trim() || loading) return;

    setMessages(msgs => [...msgs, { role: "user", content: input }]);
    setLoading(true);
    setStreaming(true);

    let assistantContent = "";

    try {
      const res = await fetch(`${API_ROOT}/ask`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-User-Id": USER_ID,
        },
        body: JSON.stringify({ question: input }),
      });

      if (res.body && res.headers.get("content-type")?.includes("text/event-stream")) {
        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let done = false;
        while (!done) {
          const { value, done: streamDone } = await reader.read();
          done = streamDone;
          const chunk = decoder.decode(value);
          assistantContent += chunk;
          setMessages(msgs =>
            msgs.slice(0, -1).concat([{ role: "assistant", content: assistantContent }])
          );
        }
      } else {
        const data = await res.json();
        assistantContent = data.response || "[no response]";
        setMessages(msgs =>
          [...msgs, { role: "assistant", content: assistantContent }]
        );
      }
    } catch {
      setMessages(msgs =>
        [...msgs, { role: "assistant", content: "[error] Unable to get response." }]
      );
    }
    setInput("");
    setLoading(false);
    setStreaming(false);
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
            <span className="block whitespace-pre-wrap">
              <ReactMarkdown
                components={{
                  // eslint-disable-next-line @typescript-eslint/no-explicit-any
                  code({ inline, className, children, ...props }: any) {
                    const match = /language-(\w+)/.exec(className || "");
                    return !inline && match ? (
                      <SyntaxHighlighter
                        style={vscDarkPlus}
                        language={match[1]}
                        PreTag="div"
                        {...props}
                      >
                        {String(children).replace(/\n$/, "")}
                      </SyntaxHighlighter>
                    ) : (
                      <code className={className} {...props}>
                        {children}
                      </code>
                    );
                  }
                }}
              >
                {msg.content}
              </ReactMarkdown>
            </span>
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
          {loading || streaming ? "Sending…" : "Send"}
        </button>
      </form>
      <div className="text-xs text-gray-400 text-center mt-2">
        API root: <span className="font-mono">{API_ROOT}</span>
      </div>
    </div>
  );
}
