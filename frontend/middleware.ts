//#region Admin Ask Gate (Edge Middleware)
// Purpose: Gate admin Ask UI with IP allowlist and Bearer token.
// Security: Never exposes server secrets; only checks headers and path.

import { NextResponse } from "next/server"
import type { NextRequest } from "next/server"

// -- Paths protected by this middleware
const ADMIN_MATCHERS = [
  /^\/admin\/ask(\/.*)?$/,
  /^\/status\/ask(\/.*)?$/,
]

// -- Environment: optional IP allowlist and required admin token
const RAW_IPS = process.env.ADMIN_IPS || ""
const IP_ALLOWLIST = RAW_IPS.split(",").map(s => s.trim()).filter(Boolean)
const ADMIN_TOKEN = process.env.ADMIN_UI_TOKEN || ""

export function middleware(req: NextRequest) {
  const { pathname } = req.nextUrl

  // Fast-path: ignore all non-admin paths
  const isProtected = ADMIN_MATCHERS.some(rx => rx.test(pathname))
  if (!isProtected) return NextResponse.next()

  // ── IP allowlist (best-effort; uses x-forwarded-for on proxies)
  // Prefer first value in x-forwarded-for; fallback to req.ip if available
  const forwardedFor = req.headers.get("x-forwarded-for") || ""
  const clientIp = forwardedFor.split(",")[0]?.trim() || (req as any).ip || ""
  if (IP_ALLOWLIST.length > 0 && !IP_ALLOWLIST.includes(clientIp)) {
    return new NextResponse("Forbidden (IP)", { status: 403 })
  }

  // ── Bearer token check
  // Require exact match with ADMIN_UI_TOKEN; prompt via WWW-Authenticate
  const auth = req.headers.get("authorization") || ""
  const bearer = auth.startsWith("Bearer ") ? auth.slice(7) : ""
  if (!ADMIN_TOKEN || bearer !== ADMIN_TOKEN) {
    return new NextResponse("Unauthorized", {
      status: 401,
      headers: { "WWW-Authenticate": "Bearer" },
    })
  }

  // Allow request to proceed to page/API route
  return NextResponse.next()
}

// -- Match only exact admin Ask routes (and subpaths)
export const config = {
  matcher: ["/admin/ask/:path*", "/status/ask/:path*"],
}
//#endregion

