"use client";

/**
 * File: src/components/AgenticFlowMonitor/AgenticFlowMonitor.tsx
 * Purpose: Standalone Agentic Flow Monitor with debug flow trace integration
 * Features:
 *   - Real-time pipeline visualization using ReactFlow
 *   - Debug flow trace API integration (/debug/flow-trace)
 *   - Visual step indicators with status, timing, and error details
 *   - Interactive controls for manual/auto tracing
 *   - Recommendations and break point analysis
 */

import React, { useEffect, useMemo, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { Badge } from "@/components/ui/badge";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { Input } from "@/components/ui/input";
import {
  Workflow,
  Play,
  RefreshCw,
  AlertCircle,
  CheckCircle,
  Clock,
  XCircle,
  Activity,
  Settings,
  FileText,
  Zap
} from "lucide-react";
import ReactFlow, { Background, Controls, MiniMap, Edge, Node } from "reactflow";
import "reactflow/dist/style.css";

/* ---------------------------------------
 * Types
 * -------------------------------------*/
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

/* ---------------------------------------
 * Utility Functions
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

export default function AgenticFlowMonitor() {
  /* ---------------------------------------
   * State Management
   * -------------------------------------*/
  const [flowTrace, setFlowTrace] = useState<FlowTraceResponse | null>(null);
  const [isTracing, setIsTracing] = useState(false);
  const [autoTrace, setAutoTrace] = useState(false);
  const [testQuery, setTestQuery] = useState("test pipeline flow");
  const [showAdvanced, setShowAdvanced] = useState(false);

  /* ---------------------------------------
   * Flow Trace API Functions
   * -------------------------------------*/
  const runFlowTrace = async (query: string = testQuery) => {
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

  const runEnvironmentCheck = async () => {
    try {
      const response = await fetch("/api/ops/debug/env-config", {
        method: "GET",
        headers: {
          "Content-Type": "application/json",
        }
      });

      if (response.ok) {
        const data = await response.json();
        console.log("Environment check:", data);
        // Could add environment status to UI in future
      }
    } catch (error) {
      console.error("Environment check failed:", error);
    }
  };

  // Auto-run initial trace on component mount
  useEffect(() => {
    runFlowTrace();
    runEnvironmentCheck();
  }, []);

  /* ---------------------------------------
   * Dynamic Flow Visualization
   * -------------------------------------*/
  const flowNodes: Node[] = useMemo(() => {
    if (!flowTrace || !flowTrace.steps.length) {
      // Default nodes when no trace data
      return [
        { id: "ask_entry", position: { x: 100, y: 100 }, data: { label: "Ask Entry" }, type: "input" },
        { id: "mcp_agent", position: { x: 350, y: 100 }, data: { label: "MCP Agent" } },
        { id: "context_engine", position: { x: 600, y: 100 }, data: { label: "Context Engine" } },
        { id: "semantic_retriever", position: { x: 850, y: 100 }, data: { label: "Semantic Search" } },
        { id: "kb_service", position: { x: 1100, y: 100 }, data: { label: "KB Service" } },
        { id: "integration", position: { x: 1350, y: 100 }, data: { label: "Integration" }, type: "output" },
      ];
    }

    // Create nodes from actual trace steps
    return flowTrace.steps.map((step, index) => {
      const stepName = step.step_name.replace(/^trace_/, '').replace(/_/g, ' ');
      const Icon = getStepIcon(step.status);

      return {
        id: step.step_name,
        position: { x: 100 + (index * 250), y: 100 },
        data: {
          label: (
            <div className="flex flex-col items-center gap-1 text-xs p-2">
              <Icon className="h-4 w-4" style={{ color: getStepColor(step.status) }} />
              <span className="capitalize font-medium">{stepName}</span>
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
          borderRadius: "12px",
          minWidth: "120px",
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
      const edgeColor = step.status === "error" ? "#ef4444" : step.status === "success" ? "#22c55e" : "#6b7280";

      return {
        id: `e${index + 1}`,
        source: step.step_name,
        target: nextStep.step_name,
        label: step.status === "success" ? "✓" : step.status === "error" ? "✗" : "→",
        style: { stroke: edgeColor, strokeWidth: 2 },
        labelStyle: { fill: edgeColor, fontSize: 12, fontWeight: "bold" }
      };
    });
  }, [flowTrace]);

  return (
    <TooltipProvider>
      <div className="h-screen w-full bg-background p-6">
        <div className="h-full flex flex-col gap-6">

          {/* Header */}
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <Workflow className="h-8 w-8 text-blue-600" />
              <div>
                <h1 className="text-3xl font-bold">Agentic Flow Monitor</h1>
                <p className="text-sm text-muted-foreground">
                  Real-time pipeline visualization and debugging
                </p>
              </div>
            </div>

            <div className="flex items-center gap-3">
              {flowTrace && (
                <>
                  <Badge variant="secondary">
                    corr: {flowTrace.corr_id.slice(0, 8)}…
                  </Badge>
                  <Badge variant="outline">
                    {Math.round(flowTrace.total_duration_ms)}ms
                  </Badge>
                  {flowTrace.break_point && (
                    <Badge variant="destructive">
                      Break: {flowTrace.break_point.replace(/^trace_/, '').replace(/_/g, ' ')}
                    </Badge>
                  )}
                </>
              )}
            </div>
          </div>

          {/* Controls */}
          <Card>
            <CardHeader className="pb-3">
              <div className="flex items-center justify-between">
                <CardTitle className="text-lg">Pipeline Controls</CardTitle>
                <div className="flex items-center gap-2">
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <Button
                        size="sm"
                        variant={showAdvanced ? "default" : "outline"}
                        onClick={() => setShowAdvanced(!showAdvanced)}
                      >
                        <Settings className="h-4 w-4" />
                      </Button>
                    </TooltipTrigger>
                    <TooltipContent>Advanced settings</TooltipContent>
                  </Tooltip>
                </div>
              </div>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex items-center gap-3">
                <div className="flex-1">
                  <Input
                    placeholder="Test query for pipeline trace..."
                    value={testQuery}
                    onChange={(e) => setTestQuery(e.target.value)}
                    disabled={isTracing}
                  />
                </div>
                <Tooltip>
                  <TooltipTrigger asChild>
                    <Button
                      variant={isTracing ? "secondary" : "default"}
                      onClick={() => runFlowTrace()}
                      disabled={isTracing}
                      className="px-6"
                    >
                      {isTracing ? (
                        <RefreshCw className="h-4 w-4 animate-spin mr-2" />
                      ) : (
                        <Play className="h-4 w-4 mr-2" />
                      )}
                      {isTracing ? "Tracing..." : "Run Trace"}
                    </Button>
                  </TooltipTrigger>
                  <TooltipContent>Execute pipeline trace</TooltipContent>
                </Tooltip>
                <Tooltip>
                  <TooltipTrigger asChild>
                    <Button
                      variant={autoTrace ? "default" : "outline"}
                      onClick={() => setAutoTrace(!autoTrace)}
                      className={autoTrace ? "bg-green-600 hover:bg-green-700" : ""}
                    >
                      <Activity className="h-4 w-4" />
                    </Button>
                  </TooltipTrigger>
                  <TooltipContent>
                    {autoTrace ? "Disable auto-trace" : "Enable auto-trace"}
                  </TooltipContent>
                </Tooltip>
              </div>

              {showAdvanced && (
                <div className="border-t pt-4">
                  <div className="grid grid-cols-3 gap-4 text-sm">
                    <div className="flex items-center gap-2">
                      <Zap className="h-4 w-4 text-blue-500" />
                      <span>Deep trace enabled</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <FileText className="h-4 w-4 text-green-500" />
                      <span>Production mode</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <Activity className="h-4 w-4 text-orange-500" />
                      <span>Live monitoring</span>
                    </div>
                  </div>
                </div>
              )}
            </CardContent>
          </Card>

          {/* Flow Visualization */}
          <div className="flex-1 grid grid-cols-1 lg:grid-cols-3 gap-6">

            {/* Main Flow Chart */}
            <Card className="lg:col-span-2">
              <CardHeader className="pb-3">
                <CardTitle className="flex items-center gap-2">
                  <Workflow className="h-5 w-5" />
                  Pipeline Flow
                </CardTitle>
              </CardHeader>
              <CardContent className="h-[500px] p-0 relative">
                <div className="h-full w-full">
                  <ReactFlow
                    nodes={flowNodes}
                    edges={flowEdges}
                    fitView
                    attributionPosition="bottom-left"
                  >
                    <MiniMap zoomable pannable position="top-right" />
                    <Controls position="bottom-right" />
                    <Background />
                  </ReactFlow>
                </div>

                {/* Status Overlay */}
                {flowTrace && (
                  <div className="absolute bottom-2 left-2 bg-white/95 backdrop-blur-sm rounded-lg px-3 py-2 text-sm border shadow-lg">
                    <div className="flex items-center gap-3">
                      <span className={`flex items-center gap-1 ${flowTrace.success ? 'text-green-600' : 'text-red-600'}`}>
                        {flowTrace.success ? <CheckCircle className="h-4 w-4" /> : <XCircle className="h-4 w-4" />}
                        {flowTrace.success ? 'Pipeline OK' : 'Pipeline Failed'}
                      </span>
                      <span className="text-gray-600">
                        {flowTrace.steps.filter(s => s.status === 'success').length}/{flowTrace.steps.length} steps
                      </span>
                    </div>
                  </div>
                )}
              </CardContent>
            </Card>

            {/* Details Panel */}
            <Card>
              <CardHeader className="pb-3">
                <CardTitle>Pipeline Details</CardTitle>
              </CardHeader>
              <CardContent className="p-0">
                <Tabs defaultValue="steps" className="h-full">
                  <TabsList className="mx-3 mb-2">
                    <TabsTrigger value="steps">Steps</TabsTrigger>
                    <TabsTrigger value="recommendations">Tips</TabsTrigger>
                    <TabsTrigger value="data">Data</TabsTrigger>
                  </TabsList>

                  <TabsContent value="steps" className="h-[440px] p-4">
                    <ScrollArea className="h-full">
                      {flowTrace?.steps.length ? (
                        <div className="space-y-3">
                          {flowTrace.steps.map((step) => {
                            const Icon = getStepIcon(step.status);
                            return (
                              <div key={step.step_name} className="border rounded-lg p-3">
                                <div className="flex items-center gap-2 mb-2">
                                  <Icon
                                    className="h-4 w-4 flex-shrink-0"
                                    style={{ color: getStepColor(step.status) }}
                                  />
                                  <span className="font-medium capitalize">
                                    {step.step_name.replace(/^trace_/, '').replace(/_/g, ' ')}
                                  </span>
                                  <Badge variant="outline" className="ml-auto">
                                    {Math.round(step.duration_ms)}ms
                                  </Badge>
                                </div>
                                {step.error && (
                                  <div className="text-xs text-red-600 bg-red-50 rounded p-2 mt-1">
                                    {step.error}
                                  </div>
                                )}
                                {step.data && Object.keys(step.data).length > 0 && (
                                  <div className="text-xs text-gray-600 mt-1">
                                    {Object.entries(step.data).slice(0, 2).map(([key, value]) => (
                                      <div key={key}>
                                        <strong>{key}:</strong> {String(value).slice(0, 50)}...
                                      </div>
                                    ))}
                                  </div>
                                )}
                              </div>
                            );
                          })}
                        </div>
                      ) : (
                        <div className="text-center text-gray-500 py-8">
                          No trace data available.<br />
                          Click "Run Trace" to analyze the pipeline.
                        </div>
                      )}
                    </ScrollArea>
                  </TabsContent>

                  <TabsContent value="recommendations" className="h-[440px] p-4">
                    <ScrollArea className="h-full">
                      {flowTrace?.recommendations.length ? (
                        <div className="space-y-2">
                          {flowTrace.recommendations.map((rec, index) => (
                            <div key={index} className="text-sm p-3 bg-blue-50 rounded-lg border-l-4 border-blue-400">
                              {rec}
                            </div>
                          ))}
                        </div>
                      ) : (
                        <div className="text-center text-gray-500 py-8">
                          No recommendations available.
                        </div>
                      )}
                    </ScrollArea>
                  </TabsContent>

                  <TabsContent value="data" className="h-[440px] p-4">
                    <ScrollArea className="h-full">
                      {flowTrace ? (
                        <div className="space-y-4">
                          <div className="text-sm space-y-2">
                            <div><strong>Correlation ID:</strong> {flowTrace.corr_id}</div>
                            <div><strong>Total Duration:</strong> {Math.round(flowTrace.total_duration_ms)}ms</div>
                            <div><strong>Success:</strong> {flowTrace.success ? "✅ Yes" : "❌ No"}</div>
                            <div><strong>Steps:</strong> {flowTrace.steps.length}</div>
                            {flowTrace.break_point && (
                              <div><strong>Break Point:</strong> {flowTrace.break_point}</div>
                            )}
                          </div>
                          <Separator />
                          <div className="text-xs font-mono bg-gray-50 rounded p-3 overflow-auto">
                            <pre>{JSON.stringify(flowTrace, null, 2)}</pre>
                          </div>
                        </div>
                      ) : (
                        <div className="text-center text-gray-500 py-8">
                          No data available.
                        </div>
                      )}
                    </ScrollArea>
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