// File: src/app/ask/page.tsx
// Purpose: Ask Echo — robust LLM chat interface wired to /mcp/run
// Notes:
//  - Default lets backend planner choose route (no role sent).
//  - Handles structured errors from the server and surfaces corr_id.
//  - Reads the MCP envelope: final_text, routed_result, meta, etc.
//  - Renders grounding sources (if present) below each assistant turn.

"use client";

import React, { useState, useRef, useEffect, useCallback } from "react";
import SafeMarkdown from "@/components/SafeMarkdown";
import { API_ROOT } from "@/lib/api";

// ─────────────────────────────────────────────────────────────────────────────
// Types
// ─────────────────────────────────────────────────────────────────────────────

type Role = "user" | "assistant";

type GroundingItem = {
  path?: string;
  source?: string;
  score?: number;
};

type ResponseObject = {
  text?: string;
  meta?: Record<string, unknown>;
};

type RoutedResultObject = {
  response?: string | ResponseObject;
  answer?: string;
  grounding?: GroundingItem[];
};

type RoutedResult = RoutedResultObject | string;

type KBMeta = {
  hits?: number;
  max_score?: number | null;
};

type Meta = {
  request_id?: string;
  corr_id?: string;
  kb?: KBMeta;
} & Record<string, unknown>;

type Plan = {
  final_answer?: string;
} & Record<string, unknown>;

type MCPDetail = {
  error?: string;
  corr_id?: string;
} & Record<string, unknown>;

// Envelope shape returned by /mcp/run
type MCPEnvelope = {
  plan?: Plan | null;
  routed_result?: RoutedResult | null;
  critics?: unknown;
  context?: string;
  files_used?: Array<Record<string, unknown>>;
  meta?: Meta;
  final_text?: string;
  error?: string; // when server returns structured error JSON
  corr_id?: string; // sometimes top-level on errors
  message?: string; // optional human message on errors
  detail?: MCPDetail | unknown; // legacy/global error wrapper
};

type Message = {
  role: Role;
  content: string;
  sources?: GroundingItem[];
  corrId?: string;
};

type MCPGrounding = GroundingItem[];

// ─────────────────────────────────────────────────────────────────────────────
// Utilities
// ─────────────────────────────────────────────────────────────────────────────

const USER_ID = "bret-demo";
const STORAGE_KEY = `echo-chat-history-${USER_ID}`;
const INPUT_KEY = `echo-chat-input-${USER_ID}`;

function isMessage(val: unknown): val is Message {
  if (typeof val !== "object" || val === null) return false;
  const rec = val as Record<string, unknown>;
  return (
    (rec.role === "user" || rec.role === "assistant") &&
    typeof rec.content === "string"
  );
}

function normalizeMessages(arr: unknown[]): Message[] {
  if (!Array.isArray(arr)) return [];
  return arr
    .filter(isMessage)
    .map((msg) => ({
      role: msg.role,
      content: String(msg.content),
      sources: Array.isArray(msg.sources) ? msg.sources : undefined,
      corrId: typeof msg.corrId === "string" ? msg.corrId : undefined,
    }));
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

// Feature-safe corr ID
function newCorrId(): string {
  const globalCrypto = typeof window !== "undefined" ? window.crypto : undefined;
  if (globalCrypto && "randomUUID" in globalCrypto) {
    // `randomUUID` is present in modern browsers
    return (globalCrypto as Crypto).randomUUID();
  }
  return Math.random().toString(36).slice(2);
}

// Type guards to narrow routed_result shape
function isRoutedResultObject(val: unknown): val is RoutedResultObject {
  return typeof val === "object" && val !== null;
}

function isResponseObject(val: unknown): val is ResponseObject {
  return typeof val === "object" && val !== null;
}

// Extract a friendly answer & sources from the MCP envelope
function extractAnswerAndSources(envelope: MCPEnvelope): {
  text: string;
  sources: MCPGrounding;
} {
  const rr = envelope?.routed_result;

  // 1) final_text (preferred)
  let text =
    typeof envelope?.final_text === "string" ? envelope.final_text : "";

  // 2) routed_result.response (string or { text })
  if (!text && rr && isRoutedResultObject(rr)) {
    const resp = rr.response;
    if (typeof resp === "string" && resp.trim()) {
      text = resp;
    } else if (isResponseObject(resp) && typeof resp.text === "string" && resp.text.trim()) {
      text = resp.text;
    }
  }

  // 3) routed_result.answer (string)
  if (!text && rr && isRoutedResultObject(rr)) {
    const ans = rr.answer;
    if (typeof ans === "string" && ans.trim()) {
      text = ans;
    }
  }

  // 4) routed_result is itself a string
  if (!text && typeof rr === "string" && rr.trim()) {
    text = rr;
  }

  // 5) planner final_answer (last resort)
  if (!text && envelope?.plan && typeof envelope.plan.final_answer === "string") {
    text = envelope.plan.final_answer;
  }

  if (!text) text = "[no answer]";

  // Gather sources
  let sources: MCPGrounding = [];
  if (rr && isRoutedResultObject(rr) && Array.isArray(rr.grounding)) {
    sources = rr.grounding;
  }
  return { text, sources };
}

// ─────────────────────────────────────────────────────────────────────────────
export default function AskPage() {
  const [messages, setMessages] = useState<Message[]>(() => {
    if (typeof window !== "undefined") {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (raw) {
        try {
          const parsed = JSON.parse(raw) as unknown;
          return Array.isArray(parsed) ? normalizeMessages(parsed) : [];
        } catch {
          return [];
        }
      }
    }
    return [];
  });

  const [input, setInput] = useState<string>("");
  const [loading, setLoading] = useState<boolean>(false);
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
            // role: "planner", // ← let backend choose; uncomment only for explicit routing tests
            debug: true,
          }),
        });

        // Try to parse JSON even when !ok (server returns structured error JSON)
        let data: MCPEnvelope | null = null;
        try {
          data = (await res.json()) as MCPEnvelope;
        } catch {
          data = null;
        }

        if (!res.ok || !data) {
          const msg =
            (data?.message && String(data.message)) ||
            (data?.error && String(data.error)) ||
            (typeof data?.detail === "object" &&
              data?.detail !== null &&
              "error" in (data.detail as MCPDetail) &&
              String((data.detail as MCPDetail).error)) ||
            "Server error";

          const cid =
            (typeof data?.corr_id === "string" && data.corr_id) ||
            (typeof data?.detail === "object" &&
              data?.detail !== null &&
              "corr_id" in (data.detail as MCPDetail) &&
              typeof (data.detail as MCPDetail).corr_id === "string" &&
              (data.detail as MCPDetail).corr_id) ||
            (data?.meta && typeof data.meta.request_id === "string" && data.meta.request_id) ||
            corrId;

          setMessages((msgs) => [
            ...msgs,
            {
              role: "assistant",
              content: toMDString(`**Error:** ${msg}\n\n_Corr ID:_ \`${cid}\``),
              corrId: cid,
            },
          ]);
          setLoading(false);
          return;
        }

        // Extract final text and sources from the envelope
        const { text, sources } = extractAnswerAndSources(data);

        const showSources = Array.isArray(sources) ? sources : undefined;
        const displayCorrId =
          (data.meta && (data.meta.corr_id || data.meta.request_id)) ||
          data.corr_id ||
          corrId;

        setMessages((msgs) => [
          ...msgs,
          {
            role: "assistant",
            content: toMDString(text),
            sources: showSources,
            corrId: typeof displayCorrId === "string" ? displayCorrId : undefined,
          },
        ]);
      } catch (err) {
        // Network or parsing-level failure
        setMessages((msgs) => [
          ...msgs,
          {
            role: "assistant",
            content: toMDString("**Network error** — unable to reach the server."),
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
    if (!Array.isArray(sources) || sources.length === 0) return null;
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
              title={`${label}${score}`}
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
        {loading && <div className="text-left text-green-600 italic">Thinking…</div>}
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
              void sendMessage();
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
