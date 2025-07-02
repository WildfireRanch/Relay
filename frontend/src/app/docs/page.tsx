// File: src/app/layout.tsx
// Purpose: Global layout using the styled pixel-art sidebar from the new frontend

import './globals.css'
import { ReactNode } from 'react'
import Sidebar from '@/components/Sidebar/Sidebar'

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body className="flex min-h-screen">
        {/* Sidebar: pixel-art menu */}
        <Sidebar />

        {/* Page content */}
        <main className="flex-1 grid grid-cols-4 grid-rows-2 gap-4 p-4 bg-gray-50">
          {children}
        </main>
      </body>
    </html>
  )
}
