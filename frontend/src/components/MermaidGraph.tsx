import React from 'react';
import mermaid from 'mermaid';
import { useEffect } from 'react';

export default function MermaidGraph({ code }: { code: string }) {
  useEffect(() => {
    mermaid.initialize({ startOnLoad: true });
    mermaid.contentLoaded();
  }, []);

  return (
    <div className="mermaid text-sm p-4 border rounded-md bg-white overflow-x-auto">
      {code}
    </div>
  );
}
