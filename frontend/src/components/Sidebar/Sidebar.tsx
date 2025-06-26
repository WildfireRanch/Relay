// File: frontend/src/components/Sidebar/Sidebar.tsx

"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const sections = [
  {
    title: "Core",
    links: [
      { href: "/", label: "Home", icon: "🏠" },
      { href: "/dashboard", label: "Dashboard", icon: "🧭" },
      { href: "/ask", label: "Ask Echo", icon: "💬" },
      { href: "/docs", label: "Docs", icon: "📚" },
      { href: "/status", label: "Status", icon: "📊" },
      { href: "/metricschart", label: "Metrics", icon: "📈" },
      { href: "/editor", label: "Sandbox", icon: "🧩" }, // ← Added here
    ],
  },
  {
    title: "Ops",
    links: [
      { href: "/action-queue", label: "Action Queue", icon: "📋" },
      { href: "/audit", label: "Audit Log", icon: "🛡️" },
      { href: "/control", label: "Control Center", icon: "🧠" },
    ],
  },
  {
    title: "Admin",
    links: [
      { href: "/gmail-ops", label: "Email Ops", icon: "✉️" },
      { href: "/settings", label: "Settings", icon: "⚙️" },
    ],
  },
];

export default function Sidebar() {
  const pathname = usePathname();

  function renderLinks(links: { href: string; label: string; icon: string }[]) {
    return links.map(link => (
      <Link
        key={link.href}
        href={link.href}
        className={`flex items-center gap-2 rounded px-3 py-2 hover:bg-blue-100 text-sm font-medium
          ${pathname === link.href ? "bg-blue-200 text-blue-900" : "text-gray-700"}`}
      >
        <span className="text-lg">{link.icon}</span>
        <span>{link.label}</span>
      </Link>
    ));
  }

  return (
    <aside className="bg-white border-r w-56 min-h-screen p-4 flex flex-col gap-2">
      <div className="text-2xl font-bold mb-6">Relay Ops</div>

      {sections.map((section, i) => (
        <div key={section.title}>
          <div className="text-xs text-gray-500 uppercase mb-2 mt-1">
            {section.title}
          </div>
          <nav className="flex flex-col gap-1 mb-3">
            {renderLinks(section.links)}
          </nav>
          {i < sections.length - 1 && <hr className="my-2" />}
        </div>
      ))}
    </aside>
  );
}
