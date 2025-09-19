// File: src/lib/askClient.ts
// Purpose: Minimal client for the /ask endpoint with streaming + non-stream fallback.

export type AskMessage = { role: "user" | "assistant" | "system"; content: string };

export interface AskRequest {
  /** User prompt/message */
  prompt: string;
  /** Optional thread id/correlation id if your backend supports it */
  thread_id?: string;
  /** Optional future context payload */
  context?: Record<string, unknown>;
}

export interface AskResponseChunk {
  /** partial text (token/segment) */
  text?: string;
  /** message fully complete (final chunk) */
  done?: boolean;
  /** optional metadata (corr_id, no_answer, etc.) */
  meta?: Record<string, unknown>;
}

const DEFAULT_API_BASE =
  process.env.NEXT_PUBLIC_RELAY_API?.replace(/\/+$/, "") || "https://relay.wildfireranch.us";

type AskSuccessPayload = {
  final_text?: string;
  plan?: { final_answer?: string } | null;
  routed_result?:
    | string
    | {
        response?: string | { text?: string };
        answer?: string;
      };
  meta?: {
    corr_id?: string;
    request_id?: string;
    no_answer?: boolean;
    reason?: string;
    [key: string]: unknown;
  } | null;
};

type AskErrorPayload = {
  code?: string;
  message?: string;
  corr_id?: string;
  hint?: string;
};

function extractFinalText(body: AskSuccessPayload): string {
  if (body?.final_text && body.final_text.trim()) {
    return body.final_text;
  }

  const rr = body?.routed_result;
  if (typeof rr === "string" && rr.trim()) {
    return rr;
  }
  if (rr && typeof rr === "object") {
    const resp = rr.response;
    if (typeof resp === "string" && resp.trim()) {
      return resp;
    }
    if (resp && typeof resp === "object" && typeof resp.text === "string" && resp.text.trim()) {
      return resp.text;
    }
    if (typeof rr.answer === "string" && rr.answer.trim()) {
      return rr.answer;
    }
  }

  const planAnswer = body?.plan?.final_answer;
  if (planAnswer && planAnswer.trim()) {
    return planAnswer;
  }

  if (body?.meta?.no_answer && typeof body.meta.reason === "string") {
    return `[no answer] ${body.meta.reason}`;
  }

  return "";
}

function extractCorrId(body: AskSuccessPayload): string | undefined {
  if (body?.meta?.corr_id && typeof body.meta.corr_id === "string") {
    return body.meta.corr_id;
  }
  if (body?.meta?.request_id && typeof body.meta.request_id === "string") {
    return body.meta.request_id;
  }
  return undefined;
}

/**
 * Stream text from /ask. Falls back to non-stream JSON if the response isn't a stream.
 * Usage:
 *   for await (const chunk of askStream({ prompt: "Hello" })) { ... }
 */
export async function* askStream(req: AskRequest, apiBase = DEFAULT_API_BASE): AsyncGenerator<AskResponseChunk> {
  const url = `${apiBase}/ask`;
  const res = await fetch(url, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      query: req.prompt,
      thread_id: req.thread_id,
    }),
  });

  if (!res.ok) {
    let parsed: unknown = null;
    try {
      parsed = await res.clone().json();
    } catch {
      parsed = null;
    }

    const detail =
      parsed && typeof parsed === "object" && "detail" in parsed
        ? (parsed as { detail: unknown }).detail
        : parsed;

    const err = detail && typeof detail === "object" ? (detail as AskErrorPayload) : null;
    const code = err?.code ? `[${err.code}]` : `[${res.status}]`;
    const message = err?.message ?? "ask request failed";
    const suffix = err?.corr_id ? ` (corr_id ${err.corr_id})` : "";
    const meta = err?.corr_id ? { corr_id: err.corr_id } : undefined;
    yield { text: `\n${code} ${message}${suffix}`, done: true, meta };
    return;
  }

  const contentType = res.headers.get("content-type") ?? "";
  if (contentType.includes("application/json")) {
    const data = (await res.json()) as AskSuccessPayload;
    const text = extractFinalText(data) || "[no response]";
    const meta: Record<string, unknown> = {};
    const corrId = extractCorrId(data);
    if (corrId) meta.corr_id = corrId;
    if (typeof data?.meta?.no_answer === "boolean") {
      meta.no_answer = data.meta.no_answer;
    }
    yield { text, meta };
    yield { done: true };
    return;
  }

  if (!res.body || typeof (res.body as any).getReader !== "function") {
    yield { text: "\n[ask: empty response]", done: true };
    return;
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    if (!value) continue;
    const chunk = decoder.decode(value, { stream: true });
    if (chunk) {
      yield { text: chunk };
    }
  }
  yield { done: true };
}
