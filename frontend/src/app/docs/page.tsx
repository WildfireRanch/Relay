// File: frontend/src/app/docs/page.tsx

import DocsViewer from "../../components/DocsViewer/DocsViewer"

export default function DocsPage() {
  return (
    <main className="p-6 space-y-4">
      <h1 className="text-2xl font-bold">📚 Synced Documentation</h1>
      <DocsViewer />
    </main>
  )
}