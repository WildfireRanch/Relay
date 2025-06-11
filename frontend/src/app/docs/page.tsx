// File: frontend/src/app/docs/page.tsx

import DocsViewer from "@/components/DocsViewer/DocsViewer";

export default function DocsPage() {
  return (
    <main className="p-6">
      <h1 className="text-2xl font-bold mb-4">📚 Docs</h1>
      <DocsViewer />
    </main>
  );
}
