'use client'

import Image from 'next/image'

export default function HomePage() {
  return (
    <div className="flex h-screen w-full">
      
      {/* Sidebar */}
      <aside className="w-48 bg-white border-r p-3 space-y-2">
        <h2 className="text-lg font-bold flex items-center gap-2">
          <Image src="/cowboy.png" alt="cowboy" width={24} height={24} />
          Wildfire Ranch
        </h2>
        <nav className="mt-4 space-y-2 text-sm">
          {[
            ['ask echo', 'cowboy1.png'],
            ['codex', 'coder.png'],
            ['docs', 'blonde.png'],
            ['control', 'cop.png'],
            ['planner', 'pigtails.png'],
            ['email', 'dude.png'],
            ['critic', 'spiky.png'],
            ['janitor', 'janitor.png'],
          ].map(([label, img]) => (
            <a key={label} href={`/${label.replace(' ', '')}`} className="flex items-center gap-2 px-2 py-1 rounded hover:bg-gray-100">
              <Image src={`/${img}`} alt={label} width={24} height={24} />
              /{label}
            </a>
          ))}
        </nav>
      </aside>

      {/* Main Content Area */}
      <main className="flex-1 grid grid-cols-4 grid-rows-2 gap-4 p-4 bg-gray-50">
        
        {/* Top Left Box */}
        <div className="col-span-3 row-span-1 bg-white rounded-xl shadow p-4">
          <h3 className="font-semibold mb-2">Top Left Panel</h3>
          <p>Content goes here...</p>
        </div>

        {/* Agent Status */}
        <div className="col-span-1 row-span-1 bg-white rounded-xl shadow p-4">
          <h4 className="font-bold flex items-center gap-2">
            <Image src="/cop.png" alt="agent" width={20} height={20} />
            Agent Status
          </h4>
          <ul className="mt-2 text-sm space-y-1">
            {['red', 'green', 'orange', 'green'].map((color, i) => (
              <li key={i} className="flex items-center gap-2">
                <span className={`w-3 h-3 rounded-full bg-${color}-500`} />
                Service {i + 1}
              </li>
            ))}
          </ul>
        </div>

        {/* Bottom Left Box */}
        <div className="col-span-3 row-span-1 bg-white rounded-xl shadow p-4">
          <h3 className="font-semibold mb-2">Bottom Left Panel</h3>
          <p>More content here...</p>
        </div>

        {/* Shack Status */}
        <div className="col-span-1 row-span-1 bg-white rounded-xl shadow p-4">
          <h4 className="font-bold flex items-center gap-2">
            <Image src="/cowboy.png" alt="shack" width={20} height={20} />
            Shack Status
          </h4>
          <ul className="mt-2 text-sm space-y-1">
            {['red', 'green', 'orange', 'green'].map((color, i) => (
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
