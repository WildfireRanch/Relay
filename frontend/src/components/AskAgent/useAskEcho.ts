// File: components/AskAgent/useAskEcho.ts
// Purpose: Production-ready React hook for Echo chat.
//          Uses normalized /ask response contract and renders final_text-first.
// Updated: 2025-09-02
//
// Backend response contract (guaranteed):
// {
//   plan?: { final_answer?: string, ... },
//   routed_result?: { response?: string, ... } | string | null,
//   critics?: any,
//   context?: string,
//   files_used?: any[],
//   meta?: { origin?: string; timings_ms?: Record<string, number>; request_id?: string; [k: string]: any },
//   final_text?: string,
//   final_text is the UI-safe primary answer; plan.final_answer is secondary; routed_result.response is tertiary.
// }
//
// Notable behavior:
// - POSTs to /ask (not /mcp/run) with { query, files[], topics[], role, debug }
// - Eliminates legacy reads: plan.objective, plan.recommendation, recommendation, data.answer, etc.
// - No “not available” placeholders; empty string means “no content”, which UI can handle gracefully.
// - Adds robust error handling (HTTP status lines, JSON error body, network timeouts).
// - Supports action approvals via /control/approve_action|/deny_action.
// - Persists chat in localStorage per user/role; safely coerces markdown strings.
//
// Usage in UI:
//   const { messages, input, setInput, sendMessage, loading, ... } = useAskEcho();
//
// Optional: pair with a renderer component that shows data.context/meta/critics when desired.

import { useState, useRef, useEffect, useCallback } from "react";
import { API_ROOT } from "@/lib/api";
import { toMDString } from "@/lib/toMDString";

// ---------------------------
// Types
// ---------------------------

export type Message = {
  role: "user" | "assistant";
  content: string;                 // already markdown-coerced
  context?: string;                // markdown-coerced context (debug view)
  action?: { type: string; payload: unknown } | null;
  id?: string | null;              // server-side action/request id
  status?: "pending" | "approved" | "denied";
  meta?: Record<string, any> | null; // timings, origin, etc (optional)
  error?: string | null;           // populated for error messages
};

type AskResponse = {
  final_text?: string;
  plan?: { final_answer?: string } | null;
  routed_result?: { response?: unknown; answer?: unknown } | string | null;
  critics?: unknown;
  context?: string;
  files_used?: unknown[];
  meta?: Record<string, unknown>;
};

// ---------------------------
// Config
// ---------------------------

// Wire this to your auth/session later
const USER_ID = "bret-demo";

// Increase uniqueness to keep histories separate per role
const storageKey = (role: string) => `echo-chat-history-${USER_ID}-${role}`;

// Network guardrails
const REQUEST_TIMEOUT_MS = 45_000; // mirrors typical backend planner timeout
const DEFAULT_DEBUG = true;

// ---------------------------
// Helpers
// ---------------------------

/**
 * Pick the primary UI text from a normalized /ask result.
 * Order: final_text → plan.final_answer → routed_result.response|answer → ""
 */
function pickFinalText(data: any): string {
  const d = (data?.result ?? data) as AskResponse;

  const fromRR =
    typeof d?.routed_result === "string"
      ? d.routed_result
      : (d?.routed_result as any)?.response || (d?.routed_result as any)?.answer;

  return (
    (typeof d?.final_text === "string" && d.final_text) ||
    (typeof d?.plan?.final_answer === "string" && d.plan.final_answer) ||
    (typeof fromRR === "string" && fromRR) ||
    ""
  );
}

/** Safe JSON stringify for persistent storage. */
function safeSave<T>(key: string, value: T) {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    // no-op (quota, private mode, etc.)
  }
}

/** Safe JSON parse for persistent storage. */
function safeLoad<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(key);
    if (!raw) return fallback;
    const parsed = JSON.parse(raw);
    return parsed as T;
  } catch {
    return fallback;
  }
}

/** Turn comma-separated inputs into trimmed arrays. */
function csvToArray(input: string): string[] {
  return input
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
}

/** Abortable fetch with timeout. */
async function fetchWithTimeout(input: RequestInfo, init: RequestInit, timeoutMs: number) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(input, { ...init, signal: controller.signal });
    return res;
  } finally {
    clearTimeout(timer);
  }
}

/** Attempt to extract a human-readable error from a failed response. */
async function extractHttpError(res: Response): Promise<string> {
  try {
    const ct = res.headers.get("content-type") || "";
    if (ct.includes("application/json")) {
      const j = await res.json();
      const msg =
        j?.error?.message || j?.message || j?.detail || j?.error || JSON.stringify(j);
      return `HTTP ${res.status} ${res.statusText} — ${msg}`;
    }
    const t = await res.text();
    return `HTTP ${res.status} ${res.statusText} — ${t.slice(0, 800)}`;
  } catch {
    return `HTTP ${res.status} ${res.statusText}`;
  }
}

// ---------------------------
// Hook
// ---------------------------

export function useAskEcho() {
  // Chat state and UI controls
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [files, setFiles] = useState("");      // CSV in UI
  const [topics, setTopics] = useState("");    // CSV in UI
  const [role, setRole] = useState("planner"); // "planner" | "codex" | etc.
  const [debug, setDebug] = useState<boolean>(DEFAULT_DEBUG);
  const [showContext, setShowContext] = useState<Record<number, boolean>>({});
  const bottomRef = useRef<HTMLDivElement>(null);

  // Load chat history on mount or role change
  useEffect(() => {
    if (typeof window === "undefined") return;
    const persisted = safeLoad<Message[]>(storageKey(role), []);
    if (Array.isArray(persisted)) {
      // Coerce strings to markdown, sanitize shape
      const normalized = persisted
        .filter(
          (m: unknown): m is Partial<Message> =>
            !!m && typeof m === "object" && "content" in (m as any)
        )
        .map((m) => ({
          role:
            (m.role === "user" || m.role === "assistant") ? m.role : "assistant",
          content: toMDString((m as any).content ?? ""),
          context: typeof (m as any).context === "string" ? toMDString((m as any).context) : undefined,
          action: (m as any).action ?? null,
          id: (m as any).id ?? null,
          status: (m as any).status,
          meta: (m as any).meta ?? null,
          error: (m as any).error ?? null,
        }));
      setMessages(normalized);
    } else {
      setMessages([]);
    }
  }, [role]);

  // Persist on change & scroll
  useEffect(() => {
    if (typeof window !== "undefined") {
      safeSave(storageKey(role), messages);
    }
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, role]);

  // Toggle expanded context view for a message
  const toggleContext = useCallback((index: number) => {
    setShowContext((prev) => ({ ...prev, [index]: !prev[index] }));
  }, []);

  // Approve or deny an agent-suggested action
  const updateActionStatus = useCallback(
    async (id: string, action: "approve" | "deny", idx: number) => {
      try {
        const res = await fetch(`${API_ROOT}/control/${action}_action`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-User-Id": USER_ID,
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
      } catch (err: any) {
        alert(`Action ${action} failed: ${String(err?.message || err)}`);
      }
    },
    []
  );

  // Send user input to backend /ask and append both user + assistant messages
  const sendMessage = useCallback(async () => {
    const userMessage = input.trim();
    if (!userMessage || loading) return;

    // Optimistic UI: add the user message
    setMessages((msgs) => [...msgs, { role: "user", content: toMDString(userMessage) }]);
    setInput("");
    setLoading(true);

    // Prepare payload (normalized)
    const payload = {
      query: userMessage,
      files: files ? csvToArray(files) : [],
      topics: topics ? csvToArray(topics) : [],
      role,            // planner, codex, etc.
      debug,           // expose context/meta back to UI
      user_id: USER_ID // if backend honors this
    };

    try {
      const res = await fetchWithTimeout(
        `${API_ROOT}/ask`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-User-Id": USER_ID,
          },
          body: JSON.stringify(payload),
        },
        REQUEST_TIMEOUT_MS
      );

      if (!res.ok) {
        const msg = await extractHttpError(res);
        setMessages((msgs) => [
          ...msgs,
          {
            role: "assistant",
            content: toMDString(""),
            error: msg,
            meta: { http_error: true },
          },
        ]);
        setLoading(false);
        return;
      }

      // Parse normalized response
      const data = (await res.json()) as AskResponse | { result?: AskResponse };
      const primary = toMDString(pickFinalText(data));
      const context = toMDString((data as any)?.context ?? (data as any)?.result?.context ?? "");
      const meta = (data as any)?.meta ?? (data as any)?.result?.meta ?? null;

      // If the server attached an actionable suggestion, surface it
      const routed = (data as any)?.routed_result ?? (data as any)?.result?.routed_result ?? null;
      const maybeAction =
        routed && typeof routed === "object" && "action" in routed ? (routed as any).action : null;
      const requestId =
        (meta && (meta as any).request_id) ||
        (routed && typeof routed === "object" ? (routed as any).id : null) ||
        null;

      setMessages((msgs) => [
        ...msgs,
        {
          role: "assistant",
          content: primary,          // ← canonical text
          context: context || undefined,
          action: maybeAction ?? null,
          id: requestId,
          status: requestId ? "pending" : undefined,
          meta: meta,
          error: null,
        },
      ]);
    } catch (err: any) {
      const msg =
        err?.name === "AbortError"
          ? "Request timed out."
          : `Network error: ${String(err?.message || err)}`;
      setMessages((msgs) => [
        ...msgs,
        {
          role: "assistant",
          content: toMDString(""),
          error: msg,
          meta: { network_error: true },
        },
      ]);
    } finally {
      setLoading(false);
    }
  }, [input, loading, files, topics, role, debug]);

  return {
    // Chat contents
    messages,
    // Compose & send
    input,
    setInput,
    sendMessage,
    loading,
    // UI helpers
    bottomRef,
    showContext,
    toggleContext,
    // Filters/controls
    files,
    setFiles,
    topics,
    setTopics,
    role,
    setRole,
    debug,
    setDebug,
    // Action approvals
    updateActionStatus,
  };
}
