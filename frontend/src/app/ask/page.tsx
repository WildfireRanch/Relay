// File: src/app/ask/page.tsx
// Purpose: Ask Echo — robust LLM chat interface wired to /mcp/run
// Notes:
//  - Default lets backend planner choose route (no role sent).
//  - Handles structured errors from the server and surfaces corr_id.
//  - Reads the modern MCP envelope: final_text, routed_result, meta, etc.
//  - Renders grounding sources (if present) below each assistant turn.

"use client";

import React, { useState, useRef, useEffect, useCallback } from "react";
import SafeMarkdown from "@/components/SafeMarkdown";
import { API_ROOT } from "@/lib/api";

// ─────────────────────────────────────────────────────────────────────────────
// Types
// ─────────────────────────────────────────────────────────────────────────────

type Message = {
  role: "user" | "assistant";
  content: string;
  // Optional render extras (e.g., sources for assistant messages)
  sources?: Array<{ path?: string; source?: string; score?: number }>;
  corrId?: string;
};

type MCPGrounding = Array<{ path?: string; source?: string; score?: number }>;

type MCPEnvelope = {
  plan?: any;
  routed_result?: { response?: string | { text?: string; meta?: any }; answer?: string; grounding?: MCPGrounding } | string;
  critics?: any;
  context?: string;
  files_used?: any[];
  meta?: { request_id?: string; corr_id?: string; kb?: { hits?: number; max_score?: number }; [k: string]: any };
  final_text?: string;
  error?: string; // on non-200 responses our route returns {error, corr_id, hint}
  corr_id?: string; // sometimes top-level
  message?: string; // optional human message on errors
  detail?: any;     // legacy wrappers
};

const USER_ID = "bret-demo";
const STORAGE_KEY = `echo-chat-history-${USER_ID}`;
const INPUT_KEY = `echo-chat-input-${USER_ID}`;

// ─────────────────────────────────────────────────────────────────────────────
// Utilities
// ─────────────────────────────────────────────────────────────────────────────

function isMessage(val: unknown): val is Message {
  return (
    typeof val === "object" &&
    val !== null &&
    (val as Message).role &&
    typeof (val as Message).content === "string" &&
    ((val as Message).role === "user" || (val as Message).role === "assistant")
  );
}

function normalizeMessages(arr: unknown[]): Message[] {
  return Array.isArray(arr)
    ? arr
        .filter(isMessage)
        .map((msg) => ({
          role: msg.role,
          content: String(msg.content),
          ...(Array.isArray(msg.sources) && { sources: msg.sources }),
          ...(typeof msg.corrId === "string" && { corrId: msg.corrId }),
        }))
    : [];
}

function toMDString(val: unknown): string {
  if (val == null) return "_(no content)_";
  if (typeof val === "string") return val;
  if (Array.isArray(val)) return val.map(toMDString).join("\n\n");
  try {
    return "```json\n" + JSON.stringify(val, null, 2) + "\n```";
  } catch {
    return String(val);
  }
}

// Prefer browser crypto for corr IDs, fallback to random
function newCorrId(): string {
  try {
    // @ts-ignore
    return crypto?.randomUUID?.() || Math.random().toString(36).slice(2);
  } catch {
    return Math.random().toString(36).slice(2);
  }
}

// Extract a friendly answer & sources from the MCP envelope
function extractAnswerAndSources(envelope: MCPEnvelope): {
  text: string;
  sources: MCPGrounding;
} {
  const rr = envelope?.routed_result as any;

  // 1) final_text (preferred)
  let text =
    (typeof envelope?.final_text === "string" && envelope.final_text) || "";

  // 2) routed_result.response (string or { text })
  if (!text && rr && typeof rr === "object" && typeof rr.response === "string") {
    text = rr.response;
  }
  if (!text && rr && typeof rr?.response === "object") {
    const t = rr.response.text;
    if (typeof t === "string" && t.trim()) text = t;
  }

  // 3) routed_result.answer (string)
  if (!text && rr && typeof rr?.answer === "string") {
    text = rr.answer;
  }

  // 4) routed_result is itself a string
  if (!text && typeof envelope?.routed_result === "string") {
    text = envelope.routed_result;
  }

  // 5) planner final_answer (last resort)
  if (!text && typeof envelope?.plan?.final_answer === "string") {
    text = envelope.plan.final_answer;
  }

  if (!text) text = "[no answer]";

  // Gather sources
  let sources: MCPGrounding = [];
  if (rr && Array.isArray(rr.grounding)) {
    sources = rr.grounding;
  }
  return { text, sources };
}

// ─────────────────────────────────────────────────────────────────────────────
// Component
// ─────────────────────────────────────────────────────────────────────────────

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

  const [input, setInput] = useState<string>("");
  const [loading, setLoading] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  // Load cached input on mount
  useEffect(() => {
    const cached = localStorage.getItem(INPUT_KEY);
    if (cached) setInput(cached);
  }, []);

  // Persist messages + scroll to bottom
  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(messages));
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // Persist input while typing
  useEffect(() => {
    localStorage.setItem(INPUT_KEY, input);
  }, [input]);

  const sendMessage = useCallback(
    async (e?: React.FormEvent): Promise<void> => {
      if (e) e.preventDefault();
      if (!input.trim() || loading) return;

      const userMessage = input.trim();

      // Add user message immediately
      setMessages((msgs) => [
        ...msgs,
        { role: "user", content: toMDString(userMessage) },
      ]);
      setLoading(true);
      setInput("");

      const corrId = newCorrId();

      try {
        const res = await fetch(`${API_ROOT}/mcp/run`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-User-Id": USER_ID,
            "X-Corr-Id": corrId, // echoed by backend; useful for log triage
          },
          body: JSON.stringify({
            query: userMessage,
            // role: "planner", // ← let backend planner choose; uncomment only for explicit routing tests
            debug: true,
          }),
        });

        let data: MCPEnvelope | null = null;
        try {
          data = (await res.json()) as MCPEnvelope;
        } catch {
          data = null;
        }

        if (!res.ok || !data) {
          const msg =
            data?.message ||
            data?.error ||
            data?.detail?.error ||
            "Server error";
          const cid =
            data?.corr_id ||
            data?.detail?.corr_id ||
            (data?.meta as any)?.request_id ||
            corrId;

          setMessages((msgs) => [
            ...msgs,
            {
              role: "assistant",
              content: toMDString(
                `**Error:** ${msg}\n\n_Corr ID:_ \`${cid}\``
              ),
              corrId: cid,
            },
          ]);
          setLoading(false);
          return;
        }

        // Extract final text and sources from the envelope
        const { text, sources } = extractAnswerAndSources(data);

        setMessages((msgs) => [
          ...msgs,
          {
            role: "assistant",
            content: toMDString(text),
            sources: Array.isArray(sources) ? sources : undefined,
            corrId:
              data?.meta?.corr_id ||
              data?.meta?.request_id ||
              data?.corr_id ||
              corrId,
          },
        ]);
      } catch (err) {
        console.error("⚠️ fetch error:", err);
        setMessages((msgs) => [
          ...msgs,
          {
            role: "assistant",
            content: toMDString(
              "**Network error** — unable to reach the server."
            ),
          },
        ]);
      } finally {
        setLoading(false);
      }
    },
    [input, loading]
  );

  // Render a single assistant bubble's source chips (if any)
  const SourcesChips: React.FC<{ sources?: MCPGrounding }> = ({ sources }) => {
    if (!Array.isArray(sources) || !sources.length) return null;
    return (
      <div className="mt-2 flex flex-wrap gap-2">
        {sources.slice(0, 8).map((s, idx) => {
          const label = s?.path || s?.source || "source";
          const score =
            typeof s?.score === "number" ? ` (${s.score.toFixed(3)})` : "";
          return (
            <span
              key={`${label}-${idx}`}
              className="inline-flex items-center rounded-full border px-2 py-0.5 text-xs bg-white/50 dark:bg-black/20"
              title={label + score}
            >
              <span className="truncate max-w-[16rem]">{label}</span>
              <span className="opacity-60">{score}</span>
            </span>
          );
        })}
      </div>
    );
  };

  const renderedMessages = messages.map((msg, i) => {
    const isUser = msg.role === "user";
    return (
      <div
        key={i}
        className={isUser ? "text-right text-blue-700" : "text-left text-green-700"}
      >
        <div className="prose prose-neutral dark:prose-invert max-w-none">
          <SafeMarkdown>{msg.content}</SafeMarkdown>
        </div>
        {!isUser && <SourcesChips sources={msg.sources} />}
        {!isUser && msg.corrId && (
          <div className="mt-1 text-[10px] text-gray-500">
            corr_id: <code>{msg.corrId}</code>
          </div>
        )}
      </div>
    );
  });

  return (
    <div className="w-full max-w-2xl mx-auto min-h-screen flex flex-col">
      <h1 className="text-3xl font-bold my-4">Ask Echo</h1>

      <div className="flex-1 space-y-2 overflow-y-auto border rounded-xl p-4 bg-muted">
        {renderedMessages}

        {loading && (
          <div className="text-left text-green-600 italic">Thinking…</div>
        )}
        <div ref={bottomRef} />
      </div>

      <form onSubmit={sendMessage} className="flex items-center gap-2 mt-4" autoComplete="off">
        <input
          type="text"
          className="flex-1 rounded border px-3 py-2"
          placeholder="Type your question…"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          disabled={loading}
          name="echo-message"
          id="echo-message"
          onKeyDown={(e) => {
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
