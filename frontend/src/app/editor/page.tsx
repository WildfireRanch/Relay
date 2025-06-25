// File: src/app/editor/page.tsx

'use client'

import { useEffect, useState } from 'react'
import { Puck } from '@measured/puck'
import '@measured/puck/puck.css'
import config from './puck.config'

export default function EditorPage() {
  const [initialData, setInitialData] = useState({})

  useEffect(() => {
    fetch('/layout.json')
      .then(res => res.json())
      .then(data => setInitialData(data))
      .catch(() => {
        console.warn('No layout.json found — starting fresh')
      })
  }, [])

  return (
    <div className="p-4">
      <Puck
        config={config}
        data={initialData}
        onPublish={(data) => {
          fetch('/api/layout', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data),
          })
            .then((res) => {
              if (!res.ok) throw new Error('Failed to save layout')
              console.log('✅ Layout saved via API')
            })
            .catch((err) => {
              console.error('❌ Save error:', err)
            })
        }}
      />
    </div>
  )
}
