"use client";

import React from "react";

type Diag = {
  ok: boolean;
  presence: Record<string, boolean>;
  lengths: Record<string, number>;
  default_branch?: string | null;
};

export default function GithubDiagPage() {
  const [data, setData] = React.useState<Diag | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [loading, setLoading] = React.useState(true);

  React.useEffect(() => {
    const run = async () => {
      try {
        setLoading(true);
        const res = await fetch("/integrations/github/diag", { cache: "no-store" });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const body = await res.json();
        setData(body as Diag);
        setError(null);
      } catch (e: any) {
        setError(e?.message || String(e));
      } finally {
        setLoading(false);
      }
    };
    run();
  }, []);

  return (
    <div style={{ padding: 16 }}>
      <h1>GitHub Integration Diagnostics</h1>
      {loading && <p>Loading…</p>}
      {error && <p style={{ color: "crimson" }}>Error: {error}</p>}
      {data && (
        <div style={{ marginTop: 12 }}>
          <p>OK: {String(data.ok)}</p>
          <p>Default branch: {data.default_branch || "—"}</p>
          <h2>Env Presence</h2>
          <ul>
            {Object.entries(data.presence || {}).map(([k, v]) => (
              <li key={k}>
                {k}: {String(v)} ({data.lengths?.[k] || 0} chars)
              </li>
            ))}
          </ul>
        </div>
      )}
      <p style={{ marginTop: 16, opacity: 0.8 }}>
        This reads /integrations/github/diag from the API. Configure your GitHub App envs to pass.
      </p>
    </div>
  );
}

