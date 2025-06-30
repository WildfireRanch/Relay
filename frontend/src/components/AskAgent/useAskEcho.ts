// File: components/AskAgent/useAskEcho.ts
// Purpose: Custom React hook for agent chat, POSTing to /mcp/run for full agent/critic orchestration
// Updated: 2025-06-30

import { useState, useRef, useEffect, useCallback } from "react";
import { API_ROOT } from "@/lib/api";

// Message type for chat history
export type Message = {
  role: "user" | "assistant";
  content: string;
  context?: string;
  action?: { type: string; payload: unknown };
  id?: string;
  status?: "pending" | "approved" | "denied";
};

// Set a test user ID; in production, wire this to user/session context
const USER_ID = "bret-demo";
const STORAGE_KEY = `echo-chat-history-${USER_ID}`;

export function useAskEcho() {
  // Chat state and UI controls
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [files, setFiles] = useState("");      // Comma-separated string in UI
  const [topics, setTopics] = useState("");    // Comma-separated string in UI
  const [role, setRole] = useState("planner"); // Agent role, can be "planner", "codex", etc.
  const [showContext, setShowContext] = useState<Record<number, boolean>>({});
  const bottomRef = useRef<HTMLDivElement>(null);

  // Load chat history from localStorage on mount
  useEffect(() => {
    if (typeof window !== "undefined") {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (raw) setMessages(JSON.parse(raw));
    }
  }, []);

  // Save chat history and scroll to bottom on message update
  useEffect(() => {
    if (typeof window !== "undefined") {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(messages));
    }
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // Toggle expanded context view for a message
  const toggleContext = useCallback((index: number) => {
    setShowContext((prev) => ({ ...prev, [index]: !prev[index] }));
  }, []);

  // Approve or deny an agent-suggested action (e.g., code patch)
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

  // Send user input to the backend (MCP entrypoint), add both user and agent messages
  const sendMessage = useCallback(async () => {
    if (!input.trim() || loading) return;

    const userMessage = input;
    setMessages((msgs) => [...msgs, { role: "user", content: userMessage }]);
    setInput("");
    setLoading(true);

    try {
      // Prepare the payload, parsing files/topics as arrays, include selected agent role
      const payload = {
        query: userMessage, // could also use "question", but "query" is unified
        files: files ? files.split(",").map((f) => f.trim()).filter(Boolean) : [],
        topics: topics ? topics.split(",").map((t) => t.trim()).filter(Boolean) : [],
        role,        // "planner", "codex", etc. (add a UI selector for more roles)
        debug: true, // always enable debug for richer agent responses
      };

      const res = await fetch(`${API_ROOT}/mcp/run`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-User-Id": USER_ID,
        },
        body: JSON.stringify(payload),
      });

      const data = await res.json();

      // Compose assistant's reply (try multiple possible keys)
      const result = data?.result || data;
      setMessages((msgs) => [
        ...msgs,
        {
          role: "assistant",
          content:
            result?.plan?.objective ||
            result?.plan?.recommendation ||
            result?.recommendation ||
            result?.response ||
            data?.response ||
            "[no answer]",
          context: result?.context || data?.context,
          action: result?.action,
          id: result?.id,
          status: result?.id ? "pending" : undefined,
        },
      ]);
    } catch {
      setMessages((msgs) => [
        ...msgs,
        { role: "assistant", content: "[error] Unable to get response." },
      ]);
    }

    setLoading(false);
  }, [input, loading, files, topics, role]);

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
    role,
    setRole, // Expose role setter so UI can allow agent role selection
    showContext,
    toggleContext,
    updateActionStatus,
  };
}
