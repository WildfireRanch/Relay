"use client"
//#region Admin Ask Console (client UI)
// Purpose: Minimal Ask-Echo admin UI with run and stream test.
// Security: Calls only local proxies (/api/ask/*). No secrets in HTML or logs.

import { useRef, useState } from "react"

export default function AskConsole() {
  // ── State & refs ----------------------------------------------------------
  const promptRef = useRef<HTMLTextAreaElement | null>(null)
  const [result, setResult] = useState<string>("")
  const [streaming, setStreaming] = useState<boolean>(false)
  const [controller, setController] = useState<AbortController | null>(null)

  // ── Helpers ---------------------------------------------------------------
  const getPrompt = () => (promptRef.current?.value || "").trim()

  // ── Run (non-stream) -----------------------------------------------------
  async function runAsk(e: React.FormEvent) {
    e.preventDefault()
    const prompt = getPrompt()
    setResult("Running…")
    try {
      const res = await fetch("/api/ask/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prompt }),
      })
      const text = await res.text()
      const prefix = res.ok ? "✅" : "❌"
      const body = text ? ` — ${text.slice(0, 500)}` : ""
      setResult(`${prefix} HTTP ${res.status} ${res.statusText}${body}`)
    } catch {
      setResult("❌ Network error")
    }
  }

  // ── Stream (SSE-like via fetch + reader) ---------------------------------
  async function streamAsk() {
    if (streaming) return
    const prompt = getPrompt()
    const ctrl = new AbortController()
    setController(ctrl)
    setStreaming(true)
    setResult("Streaming…\n")
    try {
      const res = await fetch("/api/ask/stream", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prompt }),
        signal: ctrl.signal,
      })
      const prefix = res.ok ? "✅" : "❌"
      if (!res.body) {
        const text = await res.text()
        setResult(`${prefix} HTTP ${res.status} ${res.statusText}${text ? ` — ${text.slice(0, 500)}` : ""}`)
        setStreaming(false)
        setController(null)
        return
      }
      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let acc = `${prefix} HTTP ${res.status} ${res.statusText}\n\n`
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        acc += decoder.decode(value, { stream: true })
        setResult(acc)
      }
      setStreaming(false)
      setController(null)
    } catch (_err) {
      setResult("❌ Stream error or aborted")
      setStreaming(false)
      setController(null)
    }
  }

  function stopStream() {
    controller?.abort()
  }

  // ── Render ---------------------------------------------------------------
  return (
    <div className="p-6 max-w-3xl mx-auto space-y-4">
      {/* ── Header */}
      <h1 className="text-2xl font-semibold">Ask-Echo (Admin)</h1>

      {/* ── Form */}
      <form className="space-y-3" onSubmit={runAsk}>
        <label htmlFor="prompt" className="block text-sm font-medium">Prompt</label>
        <textarea ref={promptRef} id="prompt" className="w-full border rounded p-2 min-h-[120px]" placeholder="Ping Ask-Echo…" />
        <div className="flex gap-2">
          <button type="submit" className="px-4 py-2 rounded bg-black text-white">Run Ask</button>
          <button type="button" onClick={streamAsk} disabled={streaming} className="px-4 py-2 rounded bg-blue-600 text-white disabled:opacity-50">Stream Ask</button>
          <button type="button" onClick={stopStream} disabled={!streaming} className="px-4 py-2 rounded bg-red-600 text-white disabled:opacity-50">Stop</button>
        </div>
      </form>

      {/* ── Output */}
      <pre id="result" className="text-sm bg-neutral-100 rounded p-3 whitespace-pre-wrap">{result}</pre>

      {/* ── Footnote */}
      <p className="text-xs text-neutral-500">Admin-gated and proxied; secrets never leave the server.</p>
    </div>
  )
}
//#endregion
