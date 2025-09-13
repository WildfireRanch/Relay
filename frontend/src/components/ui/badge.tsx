// File: components/ui/badge.tsx
// Purpose: Unified, extensible Badge component for statuses and labels.
// Provides consistent variants and styling, easily expandable as the app grows.

import React from "react";
import clsx from "clsx";

type BadgeVariant =
  | "default"
  | "success"
  | "destructive"
  | "secondary"
  | "outline"     // transparent with border
  | "warning"     // for caution states
  | "info";       // for neutral/info states

const variantStyles: Record<BadgeVariant, string> = {
  default: "bg-gray-200 text-gray-700",
  success: "bg-green-100 text-green-800 border border-green-300",
  destructive: "bg-red-100 text-red-800 border border-red-300",
  secondary: "bg-blue-100 text-blue-800 border border-blue-300",
  outline: "bg-transparent text-gray-800 border border-gray-400",
  warning: "bg-yellow-100 text-yellow-800 border border-yellow-300",
  info: "bg-sky-100 text-sky-800 border border-sky-300",
};

export interface BadgeProps {
  children: React.ReactNode;
  variant?: BadgeVariant;
  className?: string;
}

export const Badge: React.FC<BadgeProps> = ({
  children,
  variant = "default",
  className = "",
}) => (
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
