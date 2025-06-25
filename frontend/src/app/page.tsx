// File: src/app/page.tsx
// Purpose: Homepage + dynamic layout rendering from saved file (layout.json)

'use client'

import { useEffect, useState } from 'react'
import { Render } from '@measured/puck'
import '@measured/puck/puck.css'

import config from './editor/puck.config'
import { API_ROOT } from '@/lib/api'

export default function Home() {
  const [layout, setLayout] = useState({})

  useEffect(() => {
    fetch('/layout.json')
      .then(res => res.json())
      .then(data => setLayout(data))
      .catch(() => console.warn('⚠️ No layout.json found, rendering empty layout'))
  }, [])

  return (
    <main className="p-6 space-y-6 relative">
      {/* Echo - Strategist (top-right corner) */}
      <div className="absolute top-4 right-4 bg-black/90 text-white rounded-xl shadow-2xl p-4 max-w-xs z-50 backdrop-blur-sm">
        <div className="flex items-center gap-4">
          <img
            src="/Echo.png"
            alt="Echo"
            className="w-12 h-12 rounded-md border border-white shadow-md"
          />
          <div className="text-sm leading-snug">
            <p className="font-semibold">Echo</p>
            <p className="italic text-gray-300">
              The daemon sees, the daemon knows,<br />
              He watches where the process goes.<br />
              He patches code while systems sleep,<br />
              And keeps the ranch, in silence, deep.
            </p>
          </div>
        </div>
      </div>

      {/* Page Header */}
      <h1 className="text-3xl font-bold">WildfireRanch Command Center</h1>
      <p className="text-muted-foreground">Relay is ready for action.</p>

      {/* Dynamic layout from Puck */}
      <Render config={config} data={layout} />

      {/* API root in footer for debugging */}
      <div className="text-xs text-gray-400 text-center mt-6">
        API root: <span className="font-mono">{API_ROOT}</span>
      </div>
    </main>
  )
}
