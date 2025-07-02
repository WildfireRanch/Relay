// File: src/app/page.tsx
// Purpose: Homepage — fully stripped layout with no Puck or layout dependencies

'use client'

import Image from 'next/image'
import { API_ROOT } from '@/lib/api'

export default function Home() {
  return (
    <main className="p-6 space-y-6 relative">
      <div className="absolute top-4 right-4 bg-black/90 text-white rounded-xl shadow-2xl p-4 max-w-xs z-50 backdrop-blur-sm">
        <div className="flex items-center gap-4">
          <Image
            src="/Echo.png"
            alt="Echo"
            width={48}
            height={48}
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

      <h1 className="text-3xl font-bold">WildfireRanch Command Center</h1>
      <p className="text-muted-foreground">Relay is ready for action.</p>

      <div className="border rounded-lg p-6 bg-white/70 dark:bg-zinc-900/60 shadow">
        <p className="text-sm text-gray-500 dark:text-gray-400">
          Select a section from the sidebar to get started.
        </p>
      </div>

      <div className="text-xs text-gray-400 text-center mt-6">
        API root: <span className="font-mono">{API_ROOT}</span>
      </div>
    </main>
  );
}
