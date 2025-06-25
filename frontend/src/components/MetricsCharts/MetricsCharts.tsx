// File: src/components/MetricsChart.tsx

'use client'

import { Card } from '../ui/card' 

import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
} from 'recharts'

const sampleData = [
  { name: 'Mon', value: 400 },
  { name: 'Tue', value: 300 },
  { name: 'Wed', value: 500 },
  { name: 'Thu', value: 200 },
  { name: 'Fri', value: 650 },
]

export default function MetricsChart() {
  return (
    <Card className="p-6">
      <h3 className="font-semibold text-lg mb-2">Metrics Over Time</h3>
      <ResponsiveContainer width="100%" height={200}>
        <LineChart data={sampleData}>
          <XAxis dataKey="name" />
          <YAxis />
          <Tooltip />
          <Line
            type="monotone"
            dataKey="value"
            stroke="#4F46E5"
            strokeWidth={2}
          />
        </LineChart>
      </ResponsiveContainer>
    </Card>
  )
}
