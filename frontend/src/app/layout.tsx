// File: app/layout.tsx
import './globals.css'
import Image from 'next/image'
import { ReactNode } from 'react'

const sidebarLinks = [
  { href: '/ask', label: 'Ask Echo', icon: '/WildfireMang.png' },
  { href: '/codex', label: 'Codex', icon: '/PlannerCop.png' },
  { href: '/docs', label: 'Docs', icon: '/Hoody.png' },
  { href: '/control', label: 'Control', icon: '/PigTails.png' },
  { href: '/planner', label: 'Planner', icon: '/ballcap beard.png' },
  { href: '/email', label: 'Email', icon: '/blackbeard earing.png' },
  { href: '/critic', label: 'Critic', icon: '/beanie and smoke.png' },
  { href: '/janitor', label: 'Janitor', icon: '/sunglass shadow.png' }
]

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body className="flex min-h-screen">
        {/* Sidebar */}
        <aside className="w-48 bg-white border-r p-3 space-y-2">
          <h2 className="text-lg font-bold flex items-center gap-2">
            <Image src="/WildfireMang.png" alt="cowboy" width={24} height={24} />
            Wildfire Ranch
          </h2>
          <nav className="mt-4 space-y-2 text-sm">
            {sidebarLinks.map(({ href, label, icon }) => (
              <a
                key={href}
                href={href}
                className="flex items-center gap-2 px-2 py-1 rounded hover:bg-gray-100"
              >
                <Image src={icon} alt={label} width={24} height={24} />
                <span>/{label.toLowerCase()}</span>
              </a>
            ))}
          </nav>
        </aside>

        {/* Route content */}
        <main className="flex-1 p-4 bg-gray-50">{children}</main>
      </body>
    </html>
  )
}
