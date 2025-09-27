/**
 * Dynamic catch-all API proxy for ops dashboard
 * Proxies requests from /api/ops/* to backend API with authentication
 */

// Helper functions
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

// Main handler for all HTTP methods
async function handleRequest(
  req: Request,
  { params }: { params: { path: string[] } }
): Promise<Response> {
  const base = apiBase()
  const key = adminKey()

  if (!base) {
    return new Response(
      JSON.stringify({ error: "API base URL not configured" }),
      { status: 500, headers: { "Content-Type": "application/json" } }
    )
  }

  // Reconstruct the path and query string
  const path = params.path.join('/')
  const url = new URL(req.url)
  const queryString = url.search
  const backendUrl = `${base}/${path}${queryString}`

  try {
    // Get request body if it exists
    let body: string | undefined
    if (req.method !== 'GET' && req.method !== 'HEAD') {
      body = await req.text()
    }

    // Make request to backend
    const upstream = await fetch(backendUrl, {
      method: req.method,
      headers: {
        "Content-Type": req.headers.get("Content-Type") || "application/json",
        "X-Api-Key": key,
        "Accept": req.headers.get("Accept") || "application/json",
      },
      body,
    })

    // Handle streaming responses (for SSE endpoints)
    if (upstream.headers.get("Content-Type")?.includes("text/event-stream") ||
        upstream.headers.get("Transfer-Encoding") === "chunked") {
      return new Response(upstream.body, {
        status: upstream.status,
        headers: {
          "Content-Type": upstream.headers.get("Content-Type") || "text/plain",
          "Cache-Control": "no-cache",
          "Connection": "keep-alive",
        },
      })
    }

    // Handle regular responses
    const responseBody = await upstream.text()
    const contentType = upstream.headers.get("Content-Type") || "application/json"

    return new Response(responseBody, {
      status: upstream.status,
      headers: {
        "Content-Type": contentType,
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type, Authorization, X-Api-Key",
      },
    })
  } catch (error) {
    console.error(`Ops proxy error for ${backendUrl}:`, error)
    return new Response(
      JSON.stringify({
        error: "Upstream request failed",
        path: `/${path}`,
        method: req.method
      }),
      { status: 502, headers: { "Content-Type": "application/json" } }
    )
  }
}

// Export handlers for all HTTP methods
export const GET = handleRequest
export const POST = handleRequest
export const PUT = handleRequest
export const DELETE = handleRequest
export const PATCH = handleRequest
export const OPTIONS = async (req: Request) => {
  return new Response(null, {
    status: 204,
    headers: {
      "Access-Control-Allow-Origin": "*",
      "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS",
      "Access-Control-Allow-Headers": "Content-Type, Authorization, X-Api-Key",
    },
  })
}