// File: components/AskEcho/useAskEcho.ts

import { useState, useRef, useEffect } from "react";
import { API_ROOT } from "@/lib/api";

export type Message = { role: "user" | "assistant"; content: string };

const USER_ID = "bret-demo";
const STORAGE_KEY = `echo-chat-history-${USER_ID}`;

export function useAskEcho() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (typeof window !== "undefined") {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (raw) setMessages(JSON.parse(raw));
    }
  }, []);

  useEffect(() => {
    if (typeof window !== "undefined") {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(messages));
    }
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  async function sendMessage() {
    if (!input.trim() || loading) return;

    const userMessage = input;
    setMessages((msgs) => [...msgs, { role: "user", content: userMessage }]);
    setInput("");
    setLoading(true);

    let assistantContent = "";

    try {
      const res = await fetch(`${API_ROOT}/ask`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-User-Id": USER_ID,
        },
        body: JSON.stringify({ question: userMessage }),
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

          setMessages((msgs) =>
            msgs.filter((m) => m.role !== "assistant").concat({
              role: "assistant",
              content: assistantContent,
            })
          );
        }
      } else {
        const data = await res.json();
        assistantContent = data.response || "[no response]";
        setMessages((msgs) => [
          ...msgs,
          { role: "assistant", content: assistantContent },
        ]);
      }
    } catch {
      setMessages((msgs) => [
        ...msgs,
        { role: "assistant", content: "[error] Unable to get response." },
      ]);
    }

    setLoading(false);
  }

  return {
    input,
    setInput,
    messages,
    sendMessage,
    loading,
    bottomRef,
  };
}
