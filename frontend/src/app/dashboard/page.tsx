// File: frontend/src/app/dashboard/page.tsx

import Dashboard from "@/components/dashboard/Dashboard";
import Link from "next/link";

async function fetchDiag(): Promise<any> {
  try {
    const base = process.env.NEXT_PUBLIC_API_BASE || "";
    const res = await fetch(`${base}/integrations/github/diag`, { cache: "no-store" });
    if (!res.ok) return null;
    return await res.json();
  } catch {
    return null;
  }
}

export default async function DashboardPage() {
  const diag = await fetchDiag();
  const ok = !!diag?.ok;
  const missing = Object.entries(diag?.presence || {})
    .filter(([, v]) => !v)
    .map(([k]) => k);

  return (
    <div className="p-4 space-y-4">
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="border rounded p-4">
          <h3 className="font-semibold mb-2">GitHub Integration</h3>
          {ok ? (
            <p className="text-green-700">OK. Default branch: {diag?.default_branch || "—"}</p>
          ) : (
            <div className="text-red-700 text-sm">
              <p>Not configured.</p>
              {missing?.length ? <p className="mt-1">Missing: {missing.join(", ")}</p> : null}
              <p className="mt-2">
                <Link className="underline" href="/admin/github">
                  Open GitHub diagnostics
                </Link>
              </p>
            </div>
          )}
        </div>
      </div>
      <Dashboard />
    </div>
  );
}
