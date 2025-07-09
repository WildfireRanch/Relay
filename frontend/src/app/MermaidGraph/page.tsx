'use client'
import MermaidGraph from '@/components/MermaidGraph';

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


