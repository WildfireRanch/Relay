'use client'

import { Puck } from "@measured/puck"
import "@measured/puck/puck.css"
import config from "@/puck.config"

export default function Editor() {
  const initialData = {}  // Load saved layout JSON here
  const handlePublish = (data: any) => {
    // Use fetch() or PostMessage to save JSON data
    console.log("📦 Published:", data)
  }

  return <Puck config={config} data={initialData} onPublish={handlePublish} />
}
