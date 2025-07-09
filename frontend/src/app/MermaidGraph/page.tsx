import Head from 'next/head';// Update the import path below to the actual location of MermaidGraph, for example:
import MermaidGraph from '../../components/MermaidGraph';
export default function Home() {
  const code = `graph TD
    A[main] --> B[agent]
    A --> C[service]
    B --> D[critic]
    D --> E[test]`;

  return (
    <>
      <Head>
        <title>DevTools Dashboard</title>
      </Head>
      <main className="p-6">
        <h1 className="text-2xl font-bold mb-4">Relay DevTools Graph</h1>
        <MermaidGraph code={code} />
      </main>
    </>
  );
}
