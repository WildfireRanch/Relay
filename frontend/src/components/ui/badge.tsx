// File: components/ui/badge.tsx
// Simple, styleable Badge component for statuses/labels

import React from "react";
import clsx from "clsx";

type BadgeVariant = "default" | "success" | "destructive" | "secondary";

const variantStyles: Record<BadgeVariant, string> = {
  default: "bg-gray-200 text-gray-700",
  success: "bg-green-100 text-green-800 border border-green-300",
  destructive: "bg-red-100 text-red-800 border border-red-300",
  secondary: "bg-blue-100 text-blue-800 border border-blue-300",
};

export const Badge: React.FC<{
  children: React.ReactNode;
  variant?: BadgeVariant;
  className?: string;
}> = ({ children, variant = "default", className = "" }) => (
  <span
    className={clsx(
      "inline-block rounded px-2 py-0.5 text-xs font-semibold",
      variantStyles[variant],
      className
    )}
  >
    {children}
  </span>
);

export default Badge;
