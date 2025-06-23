"use client";

import { useTheme } from "next-themes";
import { Button } from "@/components/ui/button";

export default function Navbar() {
  const { theme, setTheme } = useTheme();

  return (
    <div className="flex justify-between items-center px-4 py-2 border-b bg-white dark:bg-gray-900 sticky top-0 z-50">
      <h1 className="font-bold text-lg">🚀 Relay</h1>
      <div className="space-x-2">
        <Button size="sm" onClick={() => setTheme(theme === "light" ? "dark" : "light")}>
          {theme === "light" ? "🌙 Dark" : "☀️ Light"}
        </Button>
      </div>
    </div>
  );
}
