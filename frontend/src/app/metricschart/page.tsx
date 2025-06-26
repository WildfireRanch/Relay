'use client'

import MetricsChart from '@/components/MetricsCharts/MetricsCharts'

export default function MetricsChartPage() {
  return (
    <main className="p-6 space-y-6">
      <h1 className="text-2xl font-bold">Metrics</h1>
      <MetricsChart />
    </main>
  )
}
