//#region Admin Ask Console (noindex)
// Purpose: Minimal Ask-Echo admin UI. Hidden and noindex.
// Notes: Calls local proxies at /api/ask/* so secrets never reach the browser.

export const metadata = { robots: { index: false, follow: false } }

export default function AskAdmin() {
  // ── Inline client handler; no server action to keep it simple
  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault()
    const form = e.currentTarget
    const prompt = (form.querySelector("#prompt") as HTMLTextAreaElement)?.value || ""

    const outEl = document.getElementById("result") as HTMLPreElement
    outEl.textContent = "Running…"

    try {
      const res = await fetch("/api/ask/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prompt }),
      })
      const text = await res.text()
      const prefix = res.ok ? "✅" : "❌"
      const body = text ? ` — ${text.slice(0, 500)}` : ""
      outEl.textContent = `${prefix} HTTP ${res.status} ${res.statusText}${body}`
    } catch {
      outEl.textContent = "❌ Network error"
    }
  }

  return (
    <div className="p-6 max-w-3xl mx-auto space-y-4">
      {/* ── Header */}
      <h1 className="text-2xl font-semibold">Ask-Echo (Admin)</h1>

      {/* ── Form */}
      <form id="ask-form" className="space-y-3" onSubmit={onSubmit}>
        <label htmlFor="prompt" className="block text-sm font-medium">Prompt</label>
        <textarea id="prompt" className="w-full border rounded p-2 min-h-[120px]" placeholder="Ping Ask-Echo…" />
        <button className="px-4 py-2 rounded bg-black text-white">Run Ask</button>
      </form>

      {/* ── Output */}
      <pre id="result" className="text-sm bg-neutral-100 rounded p-3 whitespace-pre-wrap"></pre>

      {/* ── Footnote */}
      <p className="text-xs text-neutral-500">This page is admin-gated by Edge Middleware and uses server-side proxies; no secrets are exposed.</p>
    </div>
  )
}
//#endregion

