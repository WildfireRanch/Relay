// File: src/components/Navbar/Navbar.tsx

"use client";
import { useTheme } from "next-themes";
import Image from "next/image";
import { Button } from "@/components/ui/button";

export default function Navbar() {
  const { theme, setTheme } = useTheme();

  return (
    <div className="flex justify-between items-center px-6 py-3 border-b bg-white dark:bg-gray-900 sticky top-0 z-50 shadow-sm">
      <div className="flex items-center gap-4">
        {/* Sized-up logo or project icon */}
        <Image
          src="/logo.png" // Use your logo path or default avatar
          alt="Relay Logo"
          width={48}
          height={48}
          className="rounded-lg border"
        />
        <span className="font-bold text-xl tracking-tight">Relay Command Center</span>
      </div>
      <div className="flex items-center gap-4">
        {/* Dark mode toggle */}
        <Button
          variant="outline"
          size="sm"
          onClick={() => setTheme(theme === "light" ? "dark" : "light")}
        >
          {theme === "light" ? "🌙" : "☀️"}
        </Button>
        {/* Profile menu or avatar */}
        <Image
          src="/avatar.png" // Or fetch from user profile
          alt="Profile"
          width={40}
          height={40}
          className="rounded-full border-2 border-gray-300"
        />
      </div>
    </div>
  );
}
