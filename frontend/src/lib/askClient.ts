// File: src/lib/askClient.ts
// Purpose: Minimal client for the /ask endpoint with streaming + non-stream fallback.

export type AskMessage = { role: "user" | "assistant" | "system"; content: string };

export interface AskRequest {
  /** User prompt/message */
  prompt: string;
  /** Optional thread id/correlation id if your backend supports it */
  thread_id?: string;
  /** Optional context packs or flags */
  context?: Record<string, unknown>;
}

export interface AskResponseChunk {
  /** partial text (token/segment) */
  text?: string;
  /** message fully complete (final chunk) */
  done?: boolean;
  /** optional metadata */
  meta?: Record<string, unknown>;
}

const DEFAULT_API_BASE =
  process.env.NEXT_PUBLIC_RELAY_API?.replace(/\/+$/, "") || "https://relay.wildfireranch.us";

/**
 * Stream text from /ask. Falls back to non-stream JSON if the response isn't a stream.
 * Usage:
 *   for await (const chunk of askStream({ prompt: "Hello" })) { ... }
 */
export async function* askStream(req: AskRequest, apiBase = DEFAULT_API_BASE): AsyncGenerator<AskResponseChunk> {
  const url = `${apiBase}/ask`;
  // Adjust to your backend verb; POST is assumed.
  const res = await fetch(url, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(req),
  });

  // Non-2xx -> surface as error chunk
  if (!res.ok) {
    yield { text: `\n[ask error ${res.status}]`, done: true };
    return;
  }

  // If no body or not readable, try JSON fallback
  if (!res.body || typeof (res.body as any).getReader !== "function") {
    try {
      const data = (await res.json()) as { answer?: string } | string;
      const text = typeof data === "string" ? data : data?.answer ?? "";
      if (text) yield { text };
      yield { done: true };
    } catch {
      yield { text: "\n[ask: empty response]", done: true };
    }
    return;
  }

  // Streaming read
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let done = false;
  while (!done) {
    const { value, done: readerDone } = await reader.read();
    if (readerDone) break;
    if (value) {
      const chunk = decoder.decode(value, { stream: true });
      // If your backend uses SSE ("data: ...\n\n"), parse here. For now, plain text:
      yield { text: chunk };
    }
  }
  yield { done: true };
}
