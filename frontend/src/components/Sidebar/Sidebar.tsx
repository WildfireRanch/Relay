// File: src/components/Sidebar/Sidebar.tsx
"use client";



import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";

const links = [
  { href: "/ask", label: "Ask Echo", icon: "/Hoody.png" },
  { href: "/codex", label: "Codex", icon: "/PlannerCop.png" },
  { href: "/docs", label: "Docs", icon: "/PigTails.png" },
  { href: "/logs", label: "Logs", icon: "/echo.png" }, // Pick a fun icon!
  { href: "/control", label: "Control", icon: "/Echo.png" },
  { href: "/planner", label: "Planner", icon: "/ballcap beard.png" },
  { href: "/email", label: "Email", icon: "/blackbeard earing.png" },
  { href: "/action-queue", label: "ActionQueue", icon: "/beanie and smoke.png" },
  { href: "/janitor", label: "Janitor", icon: "/sunglass shadow.png" },
    { href: "/status", label: "Status", icon: "/globe.svg" },
  { href: "/admin/github", label: "GitHub", icon: "/file.svg" },


];

export default function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="w-48 bg-white border-r p-3 space-y-2">
      <h2 className="text-lg font-bold flex items-center gap-2">
        <Image src="/WildfireMang.png" alt="logo" width={24} height={24} />
        Wildfire Ranch
      </h2>
      <nav className="mt-4 space-y-2 text-sm">
        {links.map(({ href, label, icon }) => (
          <Link
            key={href}
            href={href}
            className={`flex items-center gap-2 px-2 py-1 rounded hover:bg-gray-100 ${
              pathname === href ? "bg-blue-100 font-semibold" : ""
            }`}
          >
            <Image src={icon} alt={label} width={24} height={24} />
            <span>{label}</span>
          </Link>
        ))}
      </nav>
    </aside>
  );
}
