import { NextResponse } from "next/server"

export async function GET() {
  const res = await fetch(`${process.env.API_URL}/docs/list`)
  const data = await res.json()
  return NextResponse.json(data)
}
