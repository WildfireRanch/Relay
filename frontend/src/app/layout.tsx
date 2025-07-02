// File: src/app/layout.tsx
// Purpose: Global layout for Wildfire Ranch Command Center — includes pixel-art sidebar and full-page content rendering

import './globals.css'
import { ReactNode } from 'react'
import Sidebar from '@/components/Sidebar/Sidebar'

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body className="flex min-h-screen font-sans bg-background text-foreground">
        {/* Sidebar (persistent on all pages) */}
        <Sidebar />

        {/* Main page content */}
        <main className="flex-1 p-6 overflow-auto bg-gray-50">
          {children}
        </main>
      </body>
    </html>
  )
}