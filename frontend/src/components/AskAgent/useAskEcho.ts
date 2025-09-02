// File: components/AskAgent/useAskEcho.ts
// Purpose: Production-ready React hook for Echo chat.
//          Uses normalized /ask response contract and renders final_text-first.
// Updated: 2025-09-02
//
// Backend response contract (guaranteed):
// {
//   plan?: { final_answer?: string, ... },
//   routed_result?: { response?: string, ... } | string | null,
//   critics?: unknown,
//   context?: string,
//   files_used?: unknown[],
//   meta?: { origin?: string; timings_ms?: Record<string, number>; request_id?: string; [k: string]: unknown },
//   final_text?: string,
// }
// UI rule: final_text (primary) → plan.final_answer → routed_result.response → "" (no placeholders)

import { useState, useRef, useEffect, useCallback } from "react";
import { API_ROOT } from "@/lib/api";
import { toMDString } from "@/lib/toMDString";

// ---------------------------
// Types
// ---------------------------

export type Message = {
  role: "user" | "assistant";
  content: string;                        // already markdown-coerced
  context?: string;                       // markdown-coerced context (debug view)
  action?: { type: string; payload: unknown } | null;
  id?: string | null;                     // server-side action/request id
  status?: "pending" | "approved" | "denied";
  meta?: Record<string, unknown> | null;  // timings, origin, etc (optional)
  error?: string | null;                  // populated for error messages
};

type AskResponse = {
  final_text?: string;
  plan?: { final_answer?: string } | null;
  routed_result?: { response?: unknown; answer?: unknown } | string | null;
  critics?: unknown;
  context?: string;
  files_used?: unknown[];
  meta?: Record<string, unknown> | null;
};

type NormalizedEnvelope = AskResponse | { result?: AskResponse };

type Role = "planner" | "codex" | "docs" | "control";

// ---------------------------
// Config
// ---------------------------

const USER_ID = "bret-demo"; // wire to auth/session later

const storageKey = (role: string) => `echo-chat-history-${USER_ID}-${role}`;

const REQUEST_TIMEOUT_MS = 45_000; // mirrors typical backend timeouts
const DEFAULT_DEBUG = true;

// ---------------------------
// Helpers
// ---------------------------

/**
 * Pick the primary UI text from a normalized /ask result.
 * Order: final_text → plan.final_answer → routed_result.response|answer → ""
 */
function pickFinalText(data: unknown): string {
  const body: AskResponse | undefined =
    (data as { result?: AskResponse })?.result ?? (data as AskResponse);

  const rr = body?.routed_result;
  const fromRR =
    typeof rr === "string"
      ? rr
      : typeof (rr as { response?: unknown })?.response === "string"
      ? String((rr as { response?: unknown })?.response)
      : typeof (rr as { answer?: unknown })?.answer === "string"
      ? String((rr as { answer?: unknown })?.answer)
      : "";

  return (
    (typeof body?.final_text === "string" && body.final_text) ||
    (typeof body?.plan?.final_answer === "string" && body.plan.final_answer) ||
    fromRR ||
    ""
  );
}

/** Safe JSON stringify for persistent storage. */
function safeSave<T>(key: string, value: T) {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    // ignore quota/private-mode errors
  }
}

/** Safe JSON parse for persistent storage. */
function safeLoad<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(key);
    if (!raw) return fallback;
    return JSON.parse(raw) as T;
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
async function fetchWithTimeout(input: RequestInfo | URL, init: RequestInit, timeoutMs: number) {
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

/** Parse normalized response into UI fields safely. */
function parseNormalized(data: NormalizedEnvelope) {
  const body: AskResponse | undefined = (data as { result?: AskResponse })?.result ?? (data as AskResponse);
  const content = toMDString(pickFinalText(data));
  const context =
    typeof body?.context === "string"
      ? toMDString(body.context)
      : typeof (data as { result?: AskResponse })?.result?.context === "string"
      ? toMDString((data as { result?: AskResponse })?.result?.context as string)
      : "";

  const meta =
    (body?.meta as Record<string, unknown> | null | undefined) ??
    ((data as { result?: AskResponse })?.result?.meta as Record<string, unknown> | null | undefined) ??
    null;

  // Optional action / request id inference
  const rr = body?.routed_result ?? (data as { result?: AskResponse })?.result?.routed_result;
  const action =
    rr && typeof rr === "object" && "action" in rr ? ((rr as { action?: unknown }).action ?? null) : null;

  const requestId =
    (meta && typeof meta === "object" && "request_id" in meta
      ? (meta.request_id as string | undefined)
      : undefined) ??
    (rr && typeof rr === "object" && "id" in rr ? (rr as { id?: string }).id : undefined) ??
    null;

  return {
    content,
    context,
    meta,
    action: (action as { type: string; payload: unknown } | null) ?? null,
    requestId: requestId ?? null,
  };
}

// ---------------------------
// Hook
// ---------------------------

export function useAskEcho() {
  // Chat state and UI controls
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState<string>("");
  const [loading, setLoading] = useState<boolean>(false);
  const [files, setFiles] = useState<string>("");   // CSV in UI
  const [topics, setTopics] = useState<string>(""); // CSV in UI
  const [role, setRole] = useState<Role>("planner");
  const [debug, setDebug] = useState<boolean>(DEFAULT_DEBUG);
  const [showContext, setShowContext] = useState<Record<number, boolean>>({});
  const bottomRef = useRef<HTMLDivElement>(null);

  // Avoid setState on unmounted component
  const isMountedRef = useRef<boolean>(true);
  useEffect(() => {
    isMountedRef.current = true;
    return () => {
      isMountedRef.current = false;
    };
  }, []);

  // Load chat history on mount or role change
  useEffect(() => {
    if (typeof window === "undefined") return;
    const persisted = safeLoad<Message[]>(storageKey(role), []);
    if (Array.isArray(persisted)) {
      const normalized = persisted
        .filter(
          (m: unknown): m is Partial<Message> =>
            !!m && typeof m === "object" && "content" in (m as Record<string, unknown>)
        )
        .map((m) => ({
          role: m.role === "user" || m.role === "assistant" ? m.role : "assistant",
          content: toMDString((m as { content?: unknown }).content ?? ""),
          context:
            typeof (m as { context?: unknown }).context === "string"
              ? toMDString((m as { context?: unknown }).context as string)
              : undefined,
          action: (m as { action?: { type: string; payload: unknown } | null }).action ?? null,
          id: (m as { id?: string | null }).id ?? null,
          status: (m as { status?: Message["status"] }).status,
          meta: (m as { meta?: Record<string, unknown> | null }).meta ?? null,
          error: (m as { error?: string | null }).error ?? null,
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
      } catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        // Surface as a system message instead of alert()
        setMessages((prev) => [
          ...prev,
          { role: "assistant", content: toMDString(""), error: `Action ${action} failed: ${msg}`, meta: { control_error: true } },
        ]);
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
      role,            // planner, codex, docs, control
      debug,           // expose context/meta back to UI
      user_id: USER_ID // optional, if backend honors this
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
        if (!isMountedRef.current) return;
        setMessages((msgs) => [
          ...msgs,
          { role: "assistant", content: toMDString(""), error: msg, meta: { http_error: true } },
        ]);
        setLoading(false);
        return;
      }

      // Parse normalized response
      const data = (await res.json()) as NormalizedEnvelope;
      const parsed = parseNormalized(data);

      if (!isMountedRef.current) return;
      setMessages((msgs) => [
        ...msgs,
        {
          role: "assistant",
          content: parsed.content,                // canonical text
          context: parsed.context || undefined,   // optional
          action: parsed.action,
          id: parsed.requestId,
          status: parsed.requestId ? "pending" : undefined,
          meta: parsed.meta,
          error: null,
        },
      ]);
    } catch (err) {
      const msg =
        err instanceof DOMException && err.name === "AbortError"
          ? "Request timed out."
          : `Network error: ${err instanceof Error ? err.message : String(err)}`;

      if (!isMountedRef.current) return;
      setMessages((msgs) => [
        ...msgs,
        { role: "assistant", content: toMDString(""), error: msg, meta: { network_error: true } },
      ]);
    } finally {
      if (isMountedRef.current) setLoading(false);
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
