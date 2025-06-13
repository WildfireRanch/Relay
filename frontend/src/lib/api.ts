// File: lib/api.ts
// Directory: frontend/src/lib
// Purpose: Single source of truth for backend API config

export const API_ROOT =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8080";

export const API_KEY =
  process.env.NEXT_PUBLIC_API_KEY ?? "";  // ← new line
