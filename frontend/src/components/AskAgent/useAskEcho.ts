// File: components/AskAgent/useAskEcho.ts

import { useState, useRef, useEffect, useCallback } from "react";
import { API_ROOT } from "@/lib/api";

export type Message = {
  role: "user" | "assistant";
  content: string;
  context?: string;
  action?: { type: string; payload: unknown };
  id?: string;
  status?: "pending" | "approved" | "denied";
};

const USER_ID = "bret-demo";
const STORAGE_KEY = `echo-chat-history-${USER_ID}`;

export function useAskEcho() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [files, setFiles] = useState("");
  const [topics, setTopics] = useState("");
  const [showContext, setShowContext] = useState<Record<number, boolean>>({});
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

  const toggleContext = useCallback((index: number) => {
    setShowContext((prev) => ({ ...prev, [index]: !prev[index] }));
  }, []);

  const updateActionStatus = useCallback(
    async (id: string, action: "approve" | "deny", idx: number) => {
      try {
        await fetch(`${API_ROOT}/control/${action}_action`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-User-Id": USER_ID,
          },
          body: JSON.stringify({ id, comment: "inline approval" }),
        });

        setMessages((prev) => {
          const updated = [...prev];
          if (updated[idx]) {
            updated[idx] = {
              ...updated[idx],
              status: action === "approve" ? "approved" : "denied",
            };
          }
          return updated;
        });
      } catch {
        alert("Error approving/denying action.");
      }
    },
    []
  );

  const sendMessage = useCallback(async () => {
    if (!input.trim() || loading) return;

    const userMessage = input;
    setMessages((msgs) => [...msgs, { role: "user", content: userMessage }]);
    setInput("");
    setLoading(true);

    try {
      const res = await fetch(`${API_ROOT}/ask?debug=true`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-User-Id": USER_ID,
        },
        body: JSON.stringify({
          question: userMessage,
          files: files ? files.split(",").map((f) => f.trim()) : undefined,
          topics: topics ? topics.split(",").map((t) => t.trim()) : undefined,
        }),
      });

      const data = await res.json();

      setMessages((msgs) => [
        ...msgs,
        {
          role: "assistant",
          content: data?.response ?? "[no answer]",
          context: data?.context,
          action: data?.action,
          id: data?.id,
          status: data?.id ? "pending" : undefined,
        },
      ]);
    } catch {
      setMessages((msgs) => [
        ...msgs,
        { role: "assistant", content: "[error] Unable to get response." },
      ]);
    }

    setLoading(false);
  }, [input, loading, files, topics]);

  return {
    input,
    setInput,
    messages,
    sendMessage,
    loading,
    bottomRef,
    files,
    setFiles,
    topics,
    setTopics,
    showContext,
    toggleContext,
    updateActionStatus,
  };
}

