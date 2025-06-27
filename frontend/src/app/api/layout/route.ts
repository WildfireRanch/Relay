// File: src/app/api/layout/route.ts
import { promises as fs } from 'fs'
import path from 'path'
import { NextResponse } from 'next/server'

export async function POST(request: Request) {
  try {
    const layout = await request.json()

    const filePath = path.join(process.cwd(), 'public', 'layout.json')
    await fs.writeFile(filePath, JSON.stringify(layout, null, 2), 'utf-8')

    return NextResponse.json({ success: true })
  } catch (error) {
    console.error('❌ Error saving layout:', error)
    return NextResponse.json({ success: false, error: String(error) }, { status: 500 })
  }
}
