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
    const upstream = await fetch(`${base}/ask/stream`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Api-Key": key,
      },
      body: await req.text(),
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

