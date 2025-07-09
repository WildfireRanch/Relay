// app/MermaidGraph/page.tsx
import MermaidGraph from '@/components/MermaidGraph';

export default function MermaidPage() {
  const code = `graph TD
    main --> agents
    agents --> critics
    critics --> tests
    services --> agents
  `;

  return (
    <div className="p-6">
      <h1 className="text-2xl font-bold mb-4">Relay Graph</h1>
      <MermaidGraph code={code} />
    </div>
  );
}

