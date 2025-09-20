//#region /api/ask/stream → streaming proxy (POST, optional)
// Purpose: Proxy streaming Ask-Echo to upstream and pipe the response body.
// Security: Injects X-Api-Key from server env; no secrets sent to client.

function apiBase(): string {
  const base = process.env.NEXT_PUBLIC_API_URL || process.env.API_ROOT || ""
  return base
}

function adminKey(): string {
  return (
    process.env.ADMIN_API_KEY ||
    process.env.RELAY_API_KEY ||
    process.env.API_KEY ||
    ""
  )
}

export async function POST(req: Request): Promise<Response> {
  const base = apiBase()
  const key = adminKey()
  if (!base) {
    return new Response("API base URL not configured", { status: 500 })
  }

  try {
    // Backend /ask/stream requires body.question (alias to query)
    // Normalize incoming payload to ensure `question` is present.
    const incomingText = await req.text()
    let normalized: Record<string, unknown> = {}
    try {
      const parsed = incomingText ? JSON.parse(incomingText) : {}
      const q =
        parsed?.question ||
        parsed?.query ||
        parsed?.prompt ||
        parsed?.text ||
        ""
      if (typeof q === "string" && q.trim()) {
        normalized.question = q.trim()
      }
      if (typeof parsed?.context === "string") normalized.context = parsed.context
      if (typeof parsed?.user_id === "string") normalized.user_id = parsed.user_id
    } catch {
      // If not JSON, pass through as-is (backend will 422)
      normalized = {}
    }

    const body = JSON.stringify(normalized)

    const upstream = await fetch(`${base}/ask/stream`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Api-Key": key,
      },
      body,
    })

    const contentType = upstream.headers.get("Content-Type") || "text/event-stream"
    return new Response(upstream.body, {
      status: upstream.status,
      headers: { "Content-Type": contentType },
    })
  } catch {
    return new Response("Upstream stream failed", { status: 502 })
  }
}
//#endregion
