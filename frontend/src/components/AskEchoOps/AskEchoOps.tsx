"use client";

/**
 * File: src/components/AskEchoOps/AskEchoOps.tsx
 * Purpose: Unified "Chat + Ops" console with live /ask chat wiring.
 * Notes:
 *   - Streams tokens into the chat as they arrive.
 *   - Keeps right-side panels as-is (demo data for now).
 */

import React, { useEffect, useMemo, useRef, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { Badge } from "@/components/ui/badge";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { CircleDot, Cpu, FileText, Brain, Activity, SendHorizontal, Workflow, Play, RefreshCw, AlertCircle, CheckCircle, Clock, XCircle } from "lucide-react";
import ReactFlow, { Background, Controls, MiniMap, Edge, Node } from "reactflow";
import "reactflow/dist/style.css";
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip as RTooltip, ResponsiveContainer } from "recharts";
import { askStream, type AskMessage } from "@/lib/askClient";

/* ---------------------------------------
 * Types & small presentational
 * -------------------------------------*/
type Who = "user" | "echo" | "system";
interface TelemetryPoint { t: string; pv: number; load: number; soc: number; }

// Debug Flow Trace Types
interface FlowStep {
  step_name: string;
  status: "success" | "error" | "skipped" | "running";
  duration_ms: number;
  error?: string;
  data?: Record<string, any>;
}

interface FlowTraceResponse {
  success: boolean;
  corr_id: string;
  total_duration_ms: number;
  steps: FlowStep[];
  break_point?: string;
  recommendations: string[];
}

const DemoMessage = ({ who, text, time }: { who: Who; text: string; time: string }) => {
  const align = who === "user" ? "justify-end" : "justify-start";
  const tone =
    who === "user" ? "bg-primary text-primary-foreground" : who === "echo" ? "bg-muted" : "bg-secondary";
  return (
    <div className={`flex ${align}`}>
      <div className={`max-w-[80%] rounded-2xl px-3 py-2 shadow-sm ${tone}`}>
        <div className="text-sm leading-snug whitespace-pre-wrap">{text}</div>
        <div className="mt-1 text-[10px] opacity-70">{time}</div>
      </div>
    </div>
  );
};

/* ---------------------------------------
 * Demo data (right panels only)
 * -------------------------------------*/
const DEMO_TELEMETRY: TelemetryPoint[] = [
  { t: "14:00", pv: 2.1, load: 1.3, soc: 78 },
  { t: "14:05", pv: 2.4, load: 1.5, soc: 79 },
  { t: "14:10", pv: 2.0, load: 1.7, soc: 78 },
  { t: "14:15", pv: 2.6, load: 1.2, soc: 80 },
  { t: "14:20", pv: 2.9, load: 1.4, soc: 81 },
];

export default function AskEchoOpsConsole() {
  /* ---------------------------------------
   * Chat state
   * -------------------------------------*/
  const [messages, setMessages] = useState<AskMessage[]>([
    { role: "system", content: "System primed with Ops profile and DocsViewer context." },
  ]);
  const [input, setInput] = useState("");
  const [isSending, setIsSending] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  /* ---------------------------------------
   * Flow Trace state
   * -------------------------------------*/
  const [flowTrace, setFlowTrace] = useState<FlowTraceResponse | null>(null);
  const [isTracing, setIsTracing] = useState(false);
  const [autoTrace, setAutoTrace] = useState(false);

  // Auto-scroll chat on new messages
  useEffect(() => {
    scrollRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  /* ---------------------------------------
   * Flow Trace functions
   * -------------------------------------*/
  const runFlowTrace = async (query: string = "test flow trace") => {
    setIsTracing(true);
    try {
      const response = await fetch("/api/ops/debug/flow-trace", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          query,
          enable_deep_trace: true,
          test_mode: false
        })
      });

      if (response.ok) {
        const data: FlowTraceResponse = await response.json();
        setFlowTrace(data);
      } else {
        console.error("Flow trace failed:", response.statusText);
        setFlowTrace({
          success: false,
          corr_id: "error",
          total_duration_ms: 0,
          steps: [],
          recommendations: ["❌ Failed to connect to debug endpoint"]
        });
      }
    } catch (error) {
      console.error("Flow trace error:", error);
      setFlowTrace({
        success: false,
        corr_id: "error",
        total_duration_ms: 0,
        steps: [],
        recommendations: ["❌ Network error - check if backend is running"]
      });
    } finally {
      setIsTracing(false);
    }
  };

  // Auto-trace when messages are sent (if enabled)
  useEffect(() => {
    if (autoTrace && messages.length > 1 && messages[messages.length - 1].role === "user") {
      const userMessage = messages[messages.length - 1].content;
      runFlowTrace(userMessage);
    }
  }, [messages, autoTrace]);

  // Send message -> stream response
  const onSend = async () => {
    const prompt = input.trim();
    if (!prompt || isSending) return;

    // Append user message immediately
    setMessages((m) => [...m, { role: "user", content: prompt }]);
    setInput("");
    setIsSending(true);

    // Prepare a draft assistant message to stream into
    const draftIndex = messages.length + 1; // after push above, assistant will be at this index
    setMessages((m) => [...m, { role: "assistant", content: "" }]);

    try {
      // NOTE: add thread_id/context as needed
      for await (const chunk of askStream({ prompt })) {
        if (chunk.text) {
          setMessages((m) =>
            m.map((msg, i) =>
              i === draftIndex ? { ...msg, content: msg.content + chunk.text } : msg
            )
          );
        }
      }
    } catch (err: unknown) {
      setMessages((m) =>
        m.map((msg, i) => (i === draftIndex ? { ...msg, content: (msg.content || "") + "\n[ask failed]" } : msg))
      );
    } finally {
      setIsSending(false);
    }
  };

  // Enter to send (simple input)
  const onKeyDown: React.KeyboardEventHandler<HTMLInputElement> = (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      onSend();
    }
  };

  /* ---------------------------------------
   * Flow monitor utility functions
   * -------------------------------------*/
  const getStepIcon = (status: string) => {
    switch (status) {
      case "success": return CheckCircle;
      case "error": return XCircle;
      case "running": return Clock;
      default: return AlertCircle;
    }
  };

  const getStepColor = (status: string) => {
    switch (status) {
      case "success": return "#22c55e"; // green-500
      case "error": return "#ef4444"; // red-500
      case "running": return "#3b82f6"; // blue-500
      default: return "#6b7280"; // gray-500
    }
  };

  const getStepBorderColor = (status: string) => {
    switch (status) {
      case "success": return "#16a34a"; // green-600
      case "error": return "#dc2626"; // red-600
      case "running": return "#2563eb"; // blue-600
      default: return "#4b5563"; // gray-600
    }
  };

  /* ---------------------------------------
   * Dynamic Flow nodes based on trace data
   * -------------------------------------*/
  const flowNodes: Node[] = useMemo(() => {
    if (!flowTrace || !flowTrace.steps.length) {
      // Default nodes when no trace data
      return [
        { id: "ask_entry", position: { x: 50, y: 60 }, data: { label: "Ask Entry" }, type: "input" },
        { id: "mcp_agent", position: { x: 250, y: 60 }, data: { label: "MCP Agent" } },
        { id: "context_engine", position: { x: 450, y: 60 }, data: { label: "Context Engine" } },
        { id: "semantic_retriever", position: { x: 650, y: 60 }, data: { label: "Semantic Search" } },
        { id: "kb_service", position: { x: 850, y: 60 }, data: { label: "KB Service" } },
        { id: "integration", position: { x: 1050, y: 60 }, data: { label: "Integration" }, type: "output" },
      ];
    }

    // Create nodes from actual trace steps
    return flowTrace.steps.map((step, index) => {
      const stepName = step.step_name.replace(/^trace_/, '').replace(/_/g, ' ');
      const Icon = getStepIcon(step.status);

      return {
        id: step.step_name,
        position: { x: 50 + (index * 200), y: 60 },
        data: {
          label: (
            <div className="flex items-center gap-2 text-xs">
              <Icon className="h-3 w-3" style={{ color: getStepColor(step.status) }} />
              <span className="capitalize">{stepName}</span>
              {step.duration_ms > 0 && (
                <span className="text-[10px] opacity-70">{Math.round(step.duration_ms)}ms</span>
              )}
            </div>
          )
        },
        type: index === 0 ? "input" : index === flowTrace.steps.length - 1 ? "output" : "default",
        style: {
          border: `2px solid ${getStepBorderColor(step.status)}`,
          backgroundColor: step.status === "error" ? "#fef2f2" : step.status === "success" ? "#f0fdf4" : "#ffffff",
        }
      };
    });
  }, [flowTrace]);

  const flowEdges: Edge[] = useMemo(() => {
    if (!flowTrace || flowTrace.steps.length < 2) {
      // Default edges
      return [
        { id: "e1", source: "ask_entry", target: "mcp_agent", label: "invoke" },
        { id: "e2", source: "mcp_agent", target: "context_engine", label: "build" },
        { id: "e3", source: "context_engine", target: "semantic_retriever", label: "search" },
        { id: "e4", source: "semantic_retriever", target: "kb_service", label: "query" },
        { id: "e5", source: "kb_service", target: "integration", label: "result" },
      ];
    }

    // Create edges from trace steps
    return flowTrace.steps.slice(0, -1).map((step, index) => {
      const nextStep = flowTrace.steps[index + 1];
      const edgeColor = step.status === "error" ? "#ef4444" : "#6b7280";

      return {
        id: `e${index + 1}`,
        source: step.step_name,
        target: nextStep.step_name,
        label: step.status === "success" ? "ok" : step.status === "error" ? "fail" : "",
        style: { stroke: edgeColor },
        labelStyle: { fill: edgeColor, fontSize: 10 }
      };
    });
  }, [flowTrace]);

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
                  {messages.map((m, i) => (
                    <DemoMessage
                      key={i}
                      who={m.role === "assistant" ? "echo" : (m.role as Who)}
                      text={m.content}
                      time={new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                    />
                  ))}
                  <div ref={scrollRef} />
                </div>
              </ScrollArea>
              <div className="border-t p-3">
                <div className="flex items-center gap-2">
                  <Input
                    placeholder='Type a message, "/" to run a tool…'
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    onKeyDown={onKeyDown}
                    disabled={isSending}
                  />
                  <Button onClick={onSend} isLoading={isSending} aria-label="Send">
                    {!isSending && <SendHorizontal className="h-4 w-4" />}
                    {isSending ? "Sending…" : null}
                  </Button>
                </div>
              </div>
            </CardContent>
          </Card>

          {/* RIGHT: Flow + Status/Context/Memory (unchanged demo) */}
          <div className="col-span-12 grid h-full grid-rows-2 gap-4 md:col-span-7">
            <Card className="row-span-1 rounded-2xl shadow">
              <CardHeader className="flex flex-row items-center justify-between pb-2">
                <div className="flex items-center gap-2">
                  <Workflow className="h-4 w-4" />
                  <CardTitle className="text-lg">Agentic Flow Monitor</CardTitle>
                  {flowTrace?.break_point && (
                    <Badge variant="destructive" className="text-xs">
                      Break: {flowTrace.break_point.replace(/^trace_/, '').replace(/_/g, ' ')}
                    </Badge>
                  )}
                </div>
                <div className="flex items-center gap-2 text-xs">
                  {flowTrace?.corr_id && (
                    <Badge variant="secondary">corr: {flowTrace.corr_id.slice(0, 8)}…</Badge>
                  )}
                  {flowTrace?.total_duration_ms && (
                    <Badge variant="outline">
                      latency: {Math.round(flowTrace.total_duration_ms)}ms
                    </Badge>
                  )}
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <Button
                        size="sm"
                        variant={isTracing ? "secondary" : "outline"}
                        onClick={() => runFlowTrace()}
                        disabled={isTracing}
                        aria-label="Run flow trace"
                        className="border-blue-200 hover:bg-blue-50"
                      >
                        {isTracing ? (
                          <RefreshCw className="h-4 w-4 animate-spin" />
                        ) : (
                          <Play className="h-4 w-4" />
                        )}
                      </Button>
                    </TooltipTrigger>
                    <TooltipContent>Run pipeline trace</TooltipContent>
                  </Tooltip>
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <Button
                        size="sm"
                        variant={autoTrace ? "default" : "outline"}
                        onClick={() => setAutoTrace(!autoTrace)}
                        aria-label="Toggle auto-trace"
                        className={autoTrace ? "bg-green-600 hover:bg-green-700" : "border-green-200 hover:bg-green-50"}
                      >
                        <Activity className="h-4 w-4" />
                      </Button>
                    </TooltipTrigger>
                    <TooltipContent>
                      {autoTrace ? "Disable auto-trace" : "Enable auto-trace on chat"}
                    </TooltipContent>
                  </Tooltip>
                </div>
              </CardHeader>
              <Separator />
              <CardContent className="h-[calc(100%-80px)] p-0 relative">
                <div className="h-full w-full">
                  <ReactFlow nodes={flowNodes} edges={flowEdges} fitView>
                    <MiniMap zoomable pannable />
                    <Controls />
                    <Background />
                  </ReactFlow>
                </div>
                {/* Compact Flow Status Summary */}
                {flowTrace && (
                  <div className="absolute bottom-1 left-1 bg-white/95 backdrop-blur-sm rounded-md px-2 py-1 text-[10px] border shadow-sm max-w-xs">
                    <div className="flex items-center gap-2">
                      <span className={`flex items-center gap-1 ${flowTrace.success ? 'text-green-600' : 'text-red-600'}`}>
                        {flowTrace.success ? <CheckCircle className="h-2 w-2" /> : <XCircle className="h-2 w-2" />}
                        {flowTrace.success ? 'OK' : 'FAIL'}
                      </span>
                      <span className="text-gray-600">
                        {flowTrace.steps.filter(s => s.status === 'success').length}/{flowTrace.steps.length}
                      </span>
                      {!flowTrace.success && flowTrace.break_point && (
                        <span className="text-red-600 font-medium truncate">
                          {flowTrace.break_point.replace(/^trace_/, '').replace(/_/g, ' ')}
                        </span>
                      )}
                    </div>
                  </div>
                )}
              </CardContent>
            </Card>

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
                  <TabsContent value="status" className="h-[calc(100%-48px)] p-4">
                    <div className="grid h-full grid-cols-1 gap-4 md:grid-cols-2">
                      <Card className="col-span-1">
                        <CardHeader className="pb-1">
                          <CardTitle className="flex items-center gap-2 text-sm">
                            <Activity className="h-4 w-4" />
                            Pipeline Steps
                          </CardTitle>
                        </CardHeader>
                        <CardContent>
                          <ScrollArea className="h-32">
                            {flowTrace?.steps.length ? (
                              <div className="space-y-2">
                                {flowTrace.steps.map((step) => {
                                  const Icon = getStepIcon(step.status);
                                  return (
                                    <div key={step.step_name} className="flex items-center gap-2 text-xs">
                                      <Icon
                                        className="h-3 w-3 flex-shrink-0"
                                        style={{ color: getStepColor(step.status) }}
                                      />
                                      <span className="flex-1 capitalize">
                                        {step.step_name.replace(/^trace_/, '').replace(/_/g, ' ')}
                                      </span>
                                      <span className="text-gray-500">
                                        {Math.round(step.duration_ms)}ms
                                      </span>
                                    </div>
                                  );
                                })}
                              </div>
                            ) : (
                              <div className="text-xs text-gray-500 text-center py-4">
                                No trace data available.<br />
                                Click the Play button to run a trace.
                              </div>
                            )}
                          </ScrollArea>
                        </CardContent>
                      </Card>
                      <Card className="col-span-1">
                        <CardHeader className="pb-1">
                          <CardTitle className="text-sm">Recommendations</CardTitle>
                        </CardHeader>
                        <CardContent>
                          <ScrollArea className="h-32">
                            {flowTrace?.recommendations.length ? (
                              <div className="space-y-1">
                                {flowTrace.recommendations.slice(0, 5).map((rec, index) => (
                                  <div key={index} className="text-xs leading-4 text-gray-700">
                                    {rec}
                                  </div>
                                ))}
                                {flowTrace.recommendations.length > 5 && (
                                  <div className="text-xs text-gray-500 italic">
                                    +{flowTrace.recommendations.length - 5} more recommendations...
                                  </div>
                                )}
                              </div>
                            ) : (
                              <div className="text-xs text-gray-500 text-center py-4">
                                No recommendations available.
                              </div>
                            )}
                          </ScrollArea>
                        </CardContent>
                      </Card>
                    </div>
                  </TabsContent>

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
