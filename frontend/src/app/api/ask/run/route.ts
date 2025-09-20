//#region /api/ask/run → server-side proxy (POST)
// Purpose: Safely proxy Ask-Echo run requests to the backend API.
// Security: Injects X-Api-Key from server env; browser never sees secrets.

// -- Small helpers -----------------------------------------------------------
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

// -- Handler ----------------------------------------------------------------
export async function POST(req: Request): Promise<Response> {
  // Read raw body as text to forward verbatim
  const body = await req.text()
  const base = apiBase()
  const key = adminKey()

  if (!base) {
    return new Response(
      JSON.stringify({ error: "API base URL not configured" }),
      { status: 500, headers: { "Content-Type": "application/json" } }
    )
  }

  try {
    const upstream = await fetch(`${base}/ask/run`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Api-Key": key,
      },
      body,
    })

    // Read as text to preserve non-JSON responses as-is
    const text = await upstream.text()
    const contentType = upstream.headers.get("Content-Type") || "application/json"

    return new Response(text, {
      status: upstream.status,
      headers: { "Content-Type": contentType },
    })
  } catch {
    // Do not leak sensitive details; provide a generic gateway error
    return new Response(
      JSON.stringify({ error: "Upstream request failed" }),
      { status: 502, headers: { "Content-Type": "application/json" } }
    )
  }
}
//#endregion

