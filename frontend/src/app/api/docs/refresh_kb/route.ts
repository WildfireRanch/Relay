import { NextRequest, NextResponse } from "next/server";

function adminKey(): string | undefined {
  return process.env.ADMIN_API_KEY || process.env.RELAY_API_KEY || process.env.API_KEY || undefined;
}

export async function POST(_req: NextRequest) {
  const upstream = `${process.env.NEXT_PUBLIC_API_URL}/docs/refresh_kb`;
  const headers: HeadersInit = { "content-type": "application/json" };
  const key = adminKey();
  if (key) headers["X-Api-Key"] = key;

  const res = await fetch(upstream, { method: "POST", headers });
  const body = await res.text();
  return new NextResponse(body, {
    status: res.status,
    headers: { "content-type": res.headers.get("content-type") || "application/json" },
  });
}

