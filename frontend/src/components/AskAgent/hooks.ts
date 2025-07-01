// File: frontend/src/components/AskAgent/hooks.ts
// Purpose: Reusable React hook for AskAgent chat—now wired to /mcp/run for agent/critic orchestration
//          Ensures ALL message fields for markdown rendering are always strings (prevents React #418).
// Updated: 2025-07-01

import { useState } from "react";
import { API_ROOT } from "@/lib/api";
import { toMDString } from "@/lib/toMDString";

// Message interface for chat history
export interface Message {
  user: string;   // User's input
  agent: string;  // Agent's reply (ALWAYS stringified)
  context?: string; // (ALWAYS stringified if present)
  action?: { type: string; payload: unknown };
  id?: string;
  status?: "pending" | "approved" | "denied";
}


// Main hook for agent chat
export function useAskAgent(userId: string) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [loading, setLoading] = useState(false);

  // Send user query to backend, add both user and agent messages
  const sendQuery = async (
    query: string,
    files: string[] = [],
    topics: string[] = [],
    role: string = "planner", // Optionally allow agent selection
    debug: boolean = true,
    scrollToBottom?: () => void
  ) => {
    if (!query.trim()) return;

    // Add user message
    setMessages((prev) => [...prev, { user: toMDString(query), agent: "" }]);
    setLoading(true);

    try {
      // Build payload for unified MCP endpoint
      const payload = {
        query,
        files,
        topics,
        role,
        debug,
      };

      const res = await fetch(`${API_ROOT}/mcp/run`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-User-Id": userId,
        },
        body: JSON.stringify(payload),
      });

      const data = await res.json();
      const result = data?.result || data;

      // Coerce all markdown-displayed fields to strings for safety
      setMessages((prev) => [
        ...prev.slice(0, -1),
        {
          user: query,
          agent: toMDString(
            result?.plan?.objective ||
            result?.plan?.recommendation ||
            result?.recommendation ||
            result?.response ||
            data?.response ||
            "[no answer]"
          ),
          context: toMDString(result?.context || data?.context),
          action: result?.action,
          id: result?.id,
          status: result?.id ? "pending" : undefined,
        },
      ]);

      scrollToBottom?.();
    } catch {
      setMessages((prev) => [
        ...prev.slice(0, -1),
        { user: toMDString(query), agent: toMDString("Error contacting Relay.") },
      ]);
    } finally {
      setLoading(false);
    }
  };

  // Approve/deny an agent-generated action, update status in message array
  const updateActionStatus = async (
    id: string,
    action: "approve" | "deny",
    idx: number
  ) => {
    try {
      await fetch(`${API_ROOT}/control/${action}_action`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-User-Id": userId,
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
  };

  return {
    messages,
    setMessages,
    sendQuery,
    updateActionStatus,
    loading,
  };
}
