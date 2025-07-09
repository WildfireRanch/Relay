// File: src/lib/utils.ts
// Purpose: Utility functions for class name merging and other common tasks.

import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
