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
import { CircleDot, Cpu, FileText, Brain, Activity, SendHorizontal, Workflow } from "lucide-react";
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip as RTooltip, ResponsiveContainer } from "recharts";
import { askStream, type AskMessage } from "@/lib/askClient";

/* ---------------------------------------
 * Types & small presentational
 * -------------------------------------*/
type Who = "user" | "echo" | "system";
interface TelemetryPoint { t: string; pv: number; load: number; soc: number; }


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


  // Auto-scroll chat on new messages
  useEffect(() => {
    scrollRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);


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

          {/* RIGHT: Quick Flow Status + Status/Context/Memory */}
          <div className="col-span-12 grid h-full grid-rows-2 gap-4 md:col-span-7">
            <Card className="row-span-1 rounded-2xl shadow">
              <CardHeader className="flex flex-row items-center justify-between pb-2">
                <div className="flex items-center gap-2">
                  <Workflow className="h-4 w-4" />
                  <CardTitle className="text-lg">Pipeline Status</CardTitle>
                  <Badge variant="outline" className="text-xs">
                    <a href="/flow-monitor" className="hover:underline">View Full Monitor →</a>
                  </Badge>
                </div>
              </CardHeader>
              <Separator />
              <CardContent className="h-[calc(100%-60px)] p-4">
                <div className="text-center py-8">
                  <Workflow className="h-12 w-12 mx-auto mb-4 text-gray-400" />
                  <p className="text-gray-600 mb-4">Flow monitoring moved to dedicated page</p>
                  <Button asChild variant="outline">
                    <a href="/flow-monitor">Open Flow Monitor</a>
                  </Button>
                </div>
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
