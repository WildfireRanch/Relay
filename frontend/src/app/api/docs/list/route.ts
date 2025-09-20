import { NextRequest, NextResponse } from "next/server";

function adminKey(): string | undefined {
  return process.env.ADMIN_API_KEY || process.env.RELAY_API_KEY || process.env.API_KEY || undefined;
}

export async function GET(_req: NextRequest) {
  const upstream = `${process.env.NEXT_PUBLIC_API_URL}/docs/list`;
  const headers: HeadersInit = {};
  const key = adminKey();
  if (key) headers["X-Api-Key"] = key;

  const res = await fetch(upstream, { headers });
  const body = await res.text();
  return new NextResponse(body, {
    status: res.status,
    headers: { "content-type": res.headers.get("content-type") || "application/json" },
  });
}
