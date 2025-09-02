// File: components/common/MetaBadges.tsx
"use client";

import React, { useMemo } from "react";

type MetaBadgesProps = {
  meta?: Record<string, any> | null | undefined;
  keys?: string[];
};

export default function MetaBadges({ meta, keys = ["ttfb", "total", "plan", "route", "latency"] }: MetaBadgesProps) {
  if (!meta) return null;

  const origin = meta?.origin as string | undefined;
  const requestId = meta?.request_id as string | undefined;
  const timings = meta?.timings_ms as Record<string, number> | undefined;

  const pairs = useMemo(() => {
    if (!timings) return [];
    const out: Array<[string, number]> = [];
    for (const k of keys) {
      if (typeof timings[k] === "number") out.push([k, timings[k]]);
    }
    if (out.length === 0) {
      for (const [k, v] of Object.entries(timings).slice(0, 3)) {
        if (typeof v === "number") out.push([k, v]);
      }
    }
    return out;
  }, [timings, keys]);

  return (
    <div className="mt-2 flex flex-wrap items-center gap-2">
      {origin && (
        <span className="rounded border bg-muted px-2 py-0.5 text-xs font-mono">origin: {origin}</span>
      )}
      {requestId && (
        <span className="rounded border bg-muted px-2 py-0.5 text-xs font-mono" title={requestId}>
          req: {requestId.length > 10 ? `${requestId.slice(0, 10)}…` : requestId}
        </span>
      )}
      {pairs.map(([k, v]) => (
        <span key={k} className="rounded border bg-muted px-2 py-0.5 text-xs font-mono">
          {k}:{Math.round(v)}ms
        </span>
      ))}
    </div>
  );
}
