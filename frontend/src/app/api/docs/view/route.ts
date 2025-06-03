import { NextRequest, NextResponse } from "next/server"

export async function GET(req: NextRequest) {
  const url = new URL(req.url)
  const path = url.searchParams.get("path")
  const res = await fetch(`${process.env.API_URL}/docs/view?path=${encodeURIComponent(path || "")}`)
  const data = await res.json()
  return NextResponse.json(data)
}
