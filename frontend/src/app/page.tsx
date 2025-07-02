// File: src/app/page.tsx
// Purpose: Wildfire Ranch Command Center UI (Puck-free)

'use client'

import Image from 'next/image'

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

export default function HomePage() {
  const statusColors = ['red', 'green', 'orange', 'green']

  return (
    <div className="flex h-screen w-full">
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
              <span className="truncate">/{label.toLowerCase().replace(/ /g, '')}</span>
            </a>
          ))}
        </nav>
      </aside>

      {/* Main Area */}
      <main className="flex-1 grid grid-cols-4 grid-rows-2 gap-4 p-4 bg-gray-50">
        {/* Top Left Panel */}
        <div className="col-span-3 row-span-1 bg-white rounded-xl shadow p-4">
          <h3 className="font-semibold mb-2">Top Left Panel</h3>
          <p>Content goes here…</p>
        </div>

        {/* Agent Status */}
        <div className="col-span-1 row-span-1 bg-white rounded-xl shadow p-4">
          <h4 className="font-bold flex items-center gap-2 mb-2">
            <Image src="/PlannerCop.png" alt="agent" width={20} height={20} />
            Agent Status
          </h4>
          <ul className="text-sm space-y-1">
            {statusColors.map((color, i) => (
              <li key={i} className="flex items-center gap-2">
                <span className={`w-3 h-3 rounded-full bg-${color}-500`} />
                Service {i + 1}
              </li>
            ))}
          </ul>
        </div>

        {/* Bottom Left Panel */}
        <div className="col-span-3 row-span-1 bg-white rounded-xl shadow p-4">
          <h3 className="font-semibold mb-2">Bottom Left Panel</h3>
          <p>More content here…</p>
        </div>

        {/* Shack Status */}
        <div className="col-span-1 row-span-1 bg-white rounded-xl shadow p-4">
          <h4 className="font-bold flex items-center gap-2 mb-2">
            <Image src="/WildfireMang.png" alt="shack" width={20} height={20} />
            Shack Status
          </h4>
          <ul className="text-sm space-y-1">
            {statusColors.map((color, i) => (
              <li key={i} className="flex items-center gap-2">
                <span className={`w-3 h-3 rounded-full bg-${color}-500`} />
                Service {i + 1}
              </li>
            ))}
          </ul>
        </div>
      </main>
    </div>
  )
}
