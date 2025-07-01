import type { Config } from '@measured/puck'

import ActionQueue from '../../components/ActionQueue/ActionQueuePanel'
import AskAgent from '../../components/AskAgent/ChatWindow'
import DocsSyncPanel from '../../components/DocsSyncPanel'
import DocsViewer from '../../components/DocsViewer/DocsViewer'
import LogsPanel from '../../components/LogsPanel/LogsPanel'
import MemoryPanel from '../../components/MemoryPanel'
import Navbar from '../../components/Navbar/Navbar'
import SearchPanel from '../../components/SearchPanel'
import Sidebar from '../../components/Sidebar/Sidebar'
import StatusPanel from '../../components/StatusPanel'
import MetricsChart from '../../components/MetricsCharts/MetricsCharts'

import { Badge } from '../../components/ui/badge'
import { Button } from '../../components/ui/button'
import { Card } from '../../components/ui/card'
import { Input } from '../../components/ui/input'
import { Label } from '../../components/ui/label'
import { Progress } from '../../components/ui/progress'
import { Textarea } from '../../components/ui/textarea'

import SafeMarkdown from "@/components/SafeMarkdown";
import { useRef } from "react";

// Helper for markdown rendering
function toMDString(val: any): string {
  if (val == null) return "";
  if (typeof val === "string") return val;
  try { return "```json\n" + JSON.stringify(val, null, 2) + "\n```"; }
  catch { return String(val); }
}

type Props = {
  AskAgent: object
  LogsPanel: object
  DocsViewer: object
  ActionQueue: object
  Navbar: object
  Sidebar: object
  MemoryPanel: object
  StatusPanel: object
  SearchPanel: object
  DocsSyncPanel: object
  MetricsChart: object

  Badge: { text: string; color?: string }
  Button: { label: string }
  Card: { children?: string }
  Input: { placeholder?: string }
  Label: { text: string }
  Progress: { value: number }
  Textarea: { placeholder?: string }

  Markdown: {
    title?: string
    content: string
    imageUrl?: string
  }
}

const config: Config<Props> = {
  components: {
    AskAgent: { fields: {}, render: () => <AskAgent /> },
    LogsPanel: { fields: {}, render: () => <LogsPanel /> },
    DocsViewer: { fields: {}, render: () => <DocsViewer /> },
    ActionQueue: { fields: {}, render: () => <ActionQueue /> },
    Navbar: { fields: {}, render: () => <Navbar /> },
    Sidebar: { fields: {}, render: () => <Sidebar /> },
    MemoryPanel: { fields: {}, render: () => <MemoryPanel /> },
    StatusPanel: { fields: {}, render: () => <StatusPanel /> },
    SearchPanel: { fields: {}, render: () => <SearchPanel /> },
    DocsSyncPanel: { fields: {}, render: () => <DocsSyncPanel /> },
    MetricsChart: { fields: {}, render: () => <MetricsChart /> },

    // --- ADVANCED MARKDOWN BLOCK ---
    Markdown: {
      label: "Markdown/Content Block",
      fields: {
        title: { type: "text", label: "Title (optional)" },
        content: { type: "textarea", label: "Markdown content" },
        imageUrl: { type: "text", label: "Image URL (optional)" }
      },
      render: ({ title, content, imageUrl }) => {
        // Optional image uploader (for markdown paste-ins)
        const fileInput = useRef<HTMLInputElement>(null);
        const handleImageUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
          const file = e.target.files?.[0];
          if (!file) return;
          // For real app, you'd POST to your backend or S3, then paste URL into markdown.
          alert("You selected: " + file.name + "\nUpload handler is not implemented in this block.");
        };
        return (
          <div className="prose prose-neutral dark:prose-invert max-w-none border rounded-xl p-4 bg-background shadow mb-4">
            {title && <h2>{title}</h2>}
            {imageUrl && (
              <img
                src={imageUrl}
                alt={title || "Markdown image"}
                className="rounded-lg my-4 max-w-full"
                style={{ maxHeight: "320px", objectFit: "contain" }}
              />
            )}
            <SafeMarkdown>{toMDString(content)}</SafeMarkdown>
            {/* Example image upload button, not wired to real backend */}
            <div className="not-prose mt-4">
              <input
                type="file"
                accept="image/*"
                ref={fileInput}
                style={{ display: "none" }}
                onChange={handleImageUpload}
              />
              <button
                className="border px-3 py-1 rounded text-xs bg-muted hover:bg-accent"
                onClick={() => fileInput.current?.click()}
                type="button"
              >
                Upload Image (not yet wired)
              </button>
              <span className="ml-2 text-gray-400 text-xs">(Paste uploaded image URL in Image URL field)</span>
            </div>
          </div>
        );
      }
    },

    // --- UI Primitives ---
    Badge: {
      fields: {
        text: { type: 'text', label: 'Text' },
        color: { type: 'text', label: 'Tailwind color class' },
      },
      render: ({ text, color }) => (
        <Badge className={color}>{text}</Badge>
      ),
    },

    Button: {
      fields: {
        label: { type: 'text', label: 'Label' },
      },
      render: ({ label }) => <Button>{label}</Button>,
    },

    Card: {
      fields: {
        children: { type: 'text', label: 'Content' },
      },
      render: ({ children }) => (
        <Card className="p-4">{children}</Card>
      ),
    },

    Input: {
      fields: {
        placeholder: { type: 'text', label: 'Placeholder' },
      },
      render: ({ placeholder }) => (
        <Input placeholder={placeholder} />
      ),
    },

    Label: {
      fields: {
        text: { type: 'text', label: 'Label' },
      },
      render: ({ text }) => <Label>{text}</Label>,
    },

    Progress: {
      fields: {
        value: { type: 'number', label: 'Progress (%)' },
      },
      render: ({ value }) => <Progress value={value} />,
    },

    Textarea: {
      fields: {
        placeholder: { type: 'text', label: 'Placeholder' },
      },
      render: ({ placeholder }) => (
        <Textarea placeholder={placeholder} />
      ),
    },
  },
};

export default config;
