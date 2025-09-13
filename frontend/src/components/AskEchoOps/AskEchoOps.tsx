/* File: src/components/AskEchoOps/AskEchoOps.tsx
 * Purpose: Unified "Chat + Ops" console wireframe for Ask Echo.
 * Notes: Imports shadcn/ui, ReactFlow, and Recharts. Replace demo data with live hooks later.
 */
"use client";

import React, { useMemo } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { Badge } from "@/components/ui/badge";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { CircleDot, Cpu, FileText, Brain, Activity, SendHorizontal, Workflow } from "lucide-react";

import ReactFlow, { Background, Controls, MiniMap, Edge, Node } from "reactflow";
import "reactflow/dist/style.css";

import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip as RTooltip, ResponsiveContainer } from "recharts";

type Who = "user" | "echo" | "system";
interface DemoMsg { who: Who; text: string; time: string; }
interface TelemetryPoint { t: string; pv: number; load: number; soc: number; }

const DEMO_MESSAGES: DemoMsg[] = [
  { who: "system", text: "System primed with Ops profile and DocsViewer context.", time: "14:00" },
  { who: "user", text: "What is the Relay Command Center?", time: "14:01" },
  { who: "echo", text: "Relay is your AI-powered ops console for solar + mining. Want a diagram?", time: "14:01" },
  { who: "user", text: "Show me active agents and current PV/Load/SOC.", time: "14:02" },
];

const DEMO_TELEMETRY: TelemetryPoint[] = [
  { t: "14:00", pv: 2.1, load: 1.3, soc: 78 },
  { t: "14:05", pv: 2.4, load: 1.5, soc: 79 },
  { t: "14:10", pv: 2.0, load: 1.7, soc: 78 },
  { t: "14:15", pv: 2.6, load: 1.2, soc: 80 },
  { t: "14:20", pv: 2.9, load: 1.4, soc: 81 },
];

const DemoMessage = ({ who, text, time }: DemoMsg) => {
  const align = who === "user" ? "justify-end" : "justify-start";
  const tone =
    who === "user" ? "bg-primary text-primary-foreground" : who === "echo" ? "bg-muted" : "bg-secondary";
  return (
    <div className={`flex ${align}`}>
      <div className={`max-w-[80%] rounded-2xl px-3 py-2 shadow-sm ${tone}`}>
        <div className="text-sm leading-snug">{text}</div>
        <div className="mt-1 text-[10px] opacity-70">{time}</div>
      </div>
    </div>
  );
};

export default function AskEchoOpsConsole() {
  const flowNodes: Node[] = useMemo(
    () => [
      { id: "planner", position: { x: 50, y: 60 }, data: { label: "Planner" }, type: "input" },
      { id: "retriever", position: { x: 250, y: 60 }, data: { label: "Retriever" } },
      { id: "critics", position: { x: 450, y: 60 }, data: { label: "Critics" } },
      { id: "tools", position: { x: 650, y: 60 }, data: { label: "Tools" } },
      { id: "final", position: { x: 850, y: 60 }, data: { label: "Final Answer" }, type: "output" },
    ],
    []
  );

  const flowEdges: Edge[] = useMemo(
    () => [
      { id: "e1", source: "planner", target: "retriever", label: "ctx" },
      { id: "e2", source: "retriever", target: "critics", label: "docs" },
      { id: "e3", source: "critics", target: "tools", label: "approve" },
      { id: "e4", source: "tools", target: "final", label: "result" },
    ],
    []
  );

  return (
    <TooltipProvider>
      <div className="h-screen w-full bg-background p-4">
        <div className="grid h-full grid-cols-12 gap-4">
          {/* LEFT: Chat */}
          <Card className="col-span-12 flex h-[45vh] flex-col rounded-2xl shadow md:col-span-5 md:h-full">
            <CardHeader className="flex flex-row items-center justify-between pb-2">
              <div className="flex items-center gap-2">
                <CircleDot className="h-4 w-4" />
                <CardTitle className="text-lg">Ask Echo</CardTitle>
                <Badge variant="outline">live</Badge>
              </div>
              <div className="flex items-center gap-2">
                <Tooltip>
                  <TooltipTrigger asChild>
                    <Button size="sm" variant="ghost" aria-label="Thread artifacts">
                      <FileText className="h-4 w-4" />
                    </Button>
                  </TooltipTrigger>
                  <TooltipContent>Thread artifacts</TooltipContent>
                </Tooltip>
                <Tooltip>
                  <TooltipTrigger asChild>
                    <Button size="sm" variant="ghost" aria-label="Memory and context">
                      <Brain className="h-4 w-4" />
                    </Button>
                  </TooltipTrigger>
                  <TooltipContent>Memory / context</TooltipContent>
                </Tooltip>
              </div>
            </CardHeader>
            <Separator />
            <CardContent className="flex min-h-0 flex-1 flex-col p-0">
              <ScrollArea className="flex-1 p-4">
                <div className="space-y-3">
                  {DEMO_MESSAGES.map((m, i) => (
                    <DemoMessage key={`${m.time}-${i}`} {...m} />
                  ))}
                </div>
              </ScrollArea>
              <div className="border-t p-3">
                <div className="flex items-center gap-2">
                  <Input placeholder='Type a message, "/" to run a tool…' />
                  <Button aria-label="Send">
                    <SendHorizontal className="h-4 w-4" />
                  </Button>
                </div>
              </div>
            </CardContent>
          </Card>

          {/* RIGHT: Flow + Status/Context/Memory */}
          <div className="col-span-12 grid h-full grid-rows-2 gap-4 md:col-span-7">
            {/* Flow Monitor */}
            <Card className="row-span-1 rounded-2xl shadow">
              <CardHeader className="flex flex-row items-center justify-between pb-2">
                <div className="flex items-center gap-2">
                  <Workflow className="h-4 w-4" />
                  <CardTitle className="text-lg">Agentic Flow Monitor</CardTitle>
                </div>
                <div className="flex items-center gap-2 text-xs">
                  <Badge variant="secondary">corr: 8f1a…</Badge>
                  <Badge variant="outline">latency: 412ms</Badge>
                </div>
              </CardHeader>
              <Separator />
              <CardContent className="h-[calc(100%-60px)] p-0">
                <div className="h-full">
                  <ReactFlow nodes={flowNodes} edges={flowEdges} fitView>
                    <MiniMap zoomable pannable />
                    <Controls />
                    <Background />
                  </ReactFlow>
                </div>
              </CardContent>
            </Card>

            {/* Status / Context / Memory */}
            <Card className="row-span-1 rounded-2xl shadow">
              <CardHeader className="pb-2">
                <div className="flex items-center gap-2">
                  <Cpu className="h-4 w-4" />
                  <CardTitle className="text-lg">Status &amp; Context</CardTitle>
                </div>
              </CardHeader>
              <Separator />
              <CardContent className="p-0">
                <Tabs defaultValue="status" className="h-full">
                  <TabsList className="mx-3 mt-2">
                    <TabsTrigger value="status">Status</TabsTrigger>
                    <TabsTrigger value="context">Context</TabsTrigger>
                    <TabsTrigger value="memory">Memory</TabsTrigger>
                  </TabsList>

                  {/* Status */}
                  <TabsContent value="status" className="h-[calc(100%-48px)] p-4">
                    <div className="grid h-full grid-cols-1 gap-4 md:grid-cols-3">
                      <Card className="col-span-1">
                        <CardHeader className="pb-1">
                          <CardTitle className="flex items-center gap-2 text-sm">
                            <Activity className="h-4 w-4" />
                            PV vs Load
                          </CardTitle>
                        </CardHeader>
                        <CardContent>
                          <div className="h-36">
                            <ResponsiveContainer width="100%" height="100%">
                              <LineChart data={DEMO_TELEMETRY} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                                <CartesianGrid strokeDasharray="3 3" />
                                <XAxis dataKey="t" tick={{ fontSize: 10 }} />
                                <YAxis tick={{ fontSize: 10 }} />
                                <RTooltip />
                                <Line type="monotone" dataKey="pv" dot={false} />
                                <Line type="monotone" dataKey="load" dot={false} />
                              </LineChart>
                            </ResponsiveContainer>
                          </div>
                        </CardContent>
                      </Card>

                      <Card className="col-span-1">
                        <CardHeader className="pb-1">
                          <CardTitle className="text-sm">SOC (%)</CardTitle>
                        </CardHeader>
                        <CardContent>
                          <div className="h-36">
                            <ResponsiveContainer width="100%" height="100%">
                              <LineChart data={DEMO_TELEMETRY} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                                <CartesianGrid strokeDasharray="3 3" />
                                <XAxis dataKey="t" tick={{ fontSize: 10 }} />
                                <YAxis tick={{ fontSize: 10 }} />
                                <RTooltip />
                                <Line type="monotone" dataKey="soc" dot={false} />
                              </LineChart>
                            </ResponsiveContainer>
                          </div>
                        </CardContent>
                      </Card>

                      <Card className="col-span-1">
                        <CardHeader className="pb-1">
                          <CardTitle className="text-sm">Agents</CardTitle>
                        </CardHeader>
                        <CardContent>
                          <div className="grid grid-cols-2 gap-2 text-xs">
                            <Badge>Planner: ok</Badge>
                            <Badge variant="secondary">Critics: 3</Badge>
                            <Badge>Docs: sync</Badge>
                            <Badge variant="outline">Queue: 2</Badge>
                          </div>
                        </CardContent>
                      </Card>
                    </div>
                  </TabsContent>

                  {/* Context */}
                  <TabsContent value="context" className="h-[calc(100%-48px)] p-4">
                    <div className="grid h-full grid-cols-1 gap-4 md:grid-cols-2">
                      <Card>
                        <CardHeader className="pb-1">
                          <CardTitle className="text-sm">Active Context Packs</CardTitle>
                        </CardHeader>
                        <CardContent>
                          <ul className="list-disc pl-5 text-sm leading-6">
                            <li>Docs: Relay Command Center – Overview.md</li>
                            <li>API Schemas: /routes/mcp, /routes/ask</li>
                            <li>KB: Solar metrics glossary</li>
                          </ul>
                        </CardContent>
                      </Card>
                      <Card>
                        <CardHeader className="pb-1">
                          <CardTitle className="text-sm">Citations / Artifacts</CardTitle>
                        </CardHeader>
                        <CardContent>
                          <ul className="list-disc pl-5 text-sm leading-6">
                            <li>ask.log#corr=8f1a…</li>
                            <li>mcp.trace 2025-09-12</li>
                            <li>retriever hits: 5</li>
                          </ul>
                        </CardContent>
                      </Card>
                    </div>
                  </TabsContent>

                  {/* Memory */}
                  <TabsContent value="memory" className="h-[calc(100%-48px)] p-4">
                    <div className="grid h-full grid-cols-1 gap-4 md:grid-cols-2">
                      <Card>
                        <CardHeader className="pb-1">
                          <CardTitle className="text-sm">Thread Memory</CardTitle>
                        </CardHeader>
                        <CardContent>
                          <ul className="list-disc pl-5 text-sm leading-6">
                            <li>Goal: consolidate Ask Echo stability</li>
                            <li>Preference: concise output</li>
                            <li>Env: FastAPI + Next.js</li>
                          </ul>
                        </CardContent>
                      </Card>
                      <Card>
                        <CardHeader className="pb-1">
                          <CardTitle className="text-sm">User Notes</CardTitle>
                        </CardHeader>
                        <CardContent>
                          <ul className="list-disc pl-5 text-sm leading-6">
                            <li>Watch PV vs Load for Miner throttle</li>
                            <li>Add ReactFlow edges for critics</li>
                            <li>Wire Neo4j memory layer</li>
                          </ul>
                        </CardContent>
                      </Card>
                    </div>
                  </TabsContent>
                </Tabs>
              </CardContent>
            </Card>
          </div>
        </div>
      </div>
    </TooltipProvider>
  );
}
