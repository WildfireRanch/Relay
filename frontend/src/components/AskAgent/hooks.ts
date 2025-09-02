// File: frontend/src/components/AskAgent/hooks.ts
// Purpose: Reusable React hook for AskAgent chat — now wired to /ask (normalized).
//          Ensures all markdown-rendered fields are string-coerced and uses
//          final_text-first fallbacks.
// Updated: 2025-09-02

"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { API_ROOT } from "@/lib/api";
import { toMDString } from "@/lib/toMDString";

// ---------------------------
// Types
// ---------------------------

type AskResponse = {
  final_text?: string;
  plan?: { final_answer?: string } | null;
  routed_result?: { response?: unknown; answer?: unknown } | string | null;
  context?: string;
  meta?: Record<string, unknown> | null;
};

type NormalizedEnvelope = AskResponse | { result?: AskResponse };

// Public message interface (kept compatible with your UI)
export interface Message {
  user: string;   // User's input (markdown-safe)
  agent: string;  // Agent's reply (markdown-safe)
  context?: string; // Debug/injected context (markdown-safe)
  action?: { type: string; payload: unknown } | null;
  id?: string | null;
  status?: "pending" | "approved" | "denied";
  // Optional extras (don't break existing callers)
  meta?: Record<string, unknown> | null;
  error?: string | null;
}

// ---------------------------
// Helpers
// ---------------------------

function pickFinalText(data: NormalizedEnvelope): string {
  const body: AskResponse | undefined =
    (data as { result?: AskResponse })?.result ?? (data as AskResponse);

  const rr = body?.routed_result;
  const fromRR =
    typeof rr === "string"
      ? rr
      : typeof (rr as { response?: unknown })?.response === "string"
      ? String((rr as { response?: unknown }).response)
      : typeof (rr as { answer?: unknown })?.answer === "string"
      ? String((rr as { answer?: unknown }).answer)
      : "";

  return (
    (typeof body?.final_text === "string" && body.final_text) ||
    (typeof body?.plan?.final_answer === "string" && body.plan.final_answer) ||
    fromRR ||
    ""
  );
}

async function extractHttpError(res: Response): Promise<string> {
  try {
    const ct = res.headers.get("content-type") || "";
    if (ct.includes("application/json")) {
      const j = (await res.json()) as Record<string, unknown>;
      const msg =
        (j?.error as { message?: string } | undefined)?.message ||
        (j?.message as string | undefined) ||
        (j?.detail as string | undefined) ||
        (j?.error as string | undefined) ||
        JSON.stringify(j);
      return `HTTP ${res.status} ${res.statusText} — ${msg}`;
    }
    const t = await res.text();
    return `HTTP ${res.status} ${res.statusText} — ${t.slice(0, 800)}`;
  } catch {
    return `HTTP ${res.status} ${res.statusText}`;
  }
}

async function fetchWithTimeout(input: RequestInfo | URL, init: RequestInit, timeoutMs: number) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(input, { ...init, signal: controller.signal });
  } finally {
    clearTimeout(timer);
  }
}

// ---------------------------
// Hook
// ---------------------------

export function useAskAgent(userId: string) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [loading, setLoading] = useState<boolean>(false);

  // Avoid state updates after unmount
  const isMountedRef = useRef<boolean>(true);
  useEffect(() => {
    isMountedRef.current = true;
    return () => {
      isMountedRef.current = false;
    };
  }, []);

  // Send user query to backend, add both user and agent messages
  const sendQuery = useCallback(
    async (
      query: string,
      files: string[] = [],
      topics: string[] = [],
      role: string = "planner",
      debug: boolean = true,
      scrollToBottom?: () => void
    ) => {
      const q = query.trim();
      if (!q) return;

      // Add user message placeholder (agent empty until response arrives)
      setMessages((prev) => [...prev, { user: toMDString(q), agent: "" }]);
      setLoading(true);

      try {
        const res = await fetchWithTimeout(
          `${API_ROOT}/ask`,
          {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
              "X-User-Id": userId,
            },
            body: JSON.stringify({ query: q, files, topics, role, debug }),
          },
          45_000
        );

        if (!res.ok) {
          const errText = await extractHttpError(res);
          if (!isMountedRef.current) return;
          setMessages((prev) => [
            ...prev.slice(0, -1),
            {
              user: toMDString(q),
              agent: toMDString(""),
              error: errText,
              meta: { http_error: true },
            },
          ]);
          return;
        }

        const data = (await res.json()) as NormalizedEnvelope;
        const answer = toMDString(pickFinalText(data));
        const body: AskResponse | undefined =
          (data as { result?: AskResponse })?.result ?? (data as AskResponse);

        // derive context/meta/action/id
        const ctx = typeof body?.context === "string" ? body.context : "";
        const meta = body?.meta ?? null;

        const rr = body?.routed_result;
        const action =
          rr && typeof rr === "object" && "action" in rr
            ? ((rr as { action?: { type: string; payload: unknown } }).action ?? null)
            : null;
        const requestId =
          (meta && typeof meta === "object" && "request_id" in meta
            ? (meta.request_id as string | undefined)
            : undefined) ?? null;

        if (!isMountedRef.current) return;
        setMessages((prev) => [
          ...prev.slice(0, -1),
          {
            user: toMDString(q),
            agent: answer, // canonical final_text-first
            context: toMDString(ctx),
            action,
            id: requestId,
            status: requestId ? "pending" : undefined,
            meta,
            error: null,
          },
        ]);

        scrollToBottom?.();
      } catch (err) {
        const msg =
          err instanceof DOMException && err.name === "AbortError"
            ? "Request timed out."
            : `Network error: ${err instanceof Error ? err.message : String(err)}`;
        if (!isMountedRef.current) return;
        setMessages((prev) => [
          ...prev.slice(0, -1),
          { user: toMDString(q), agent: toMDString(""), error: msg, meta: { network_error: true } },
        ]);
      } finally {
        if (isMountedRef.current) setLoading(false);
      }
    },
    [userId]
  );

  // Approve/deny an agent-generated action, update status in message array
  const updateActionStatus = useCallback(
    async (id: string, action: "approve" | "deny", idx: number) => {
      try {
        const res = await fetch(`${API_ROOT}/control/${action}_action`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-User-Id": userId,
          },
          body: JSON.stringify({ id, comment: "inline approval" }),
        });

        if (!res.ok) {
          const msg = await extractHttpError(res);
          throw new Error(msg);
        }

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
      } catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        // Surface as a system-style row instead of alert()
        setMessages((prev) => [
          ...prev,
          { user: "", agent: toMDString(""), error: `Action ${action} failed: ${msg}`, meta: { control_error: true } },
        ]);
      }
    },
    [userId]
  );

  return {
    messages,
    setMessages,
    sendQuery,
    updateActionStatus,
    loading,
  };
}
