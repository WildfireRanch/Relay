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
import React from "react";
import { toMDString } from "@/lib/toMDString";

// use shared markdown helper

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

// --- Move the MarkdownBlock to a real React component ---
const MarkdownBlock: React.FC<{ title?: string, content: string, imageUrl?: string }> = ({ title, content, imageUrl }) => {
  // (Optionally, image upload UI - safe to omit if not implemented)
  // You could add upload support here with hooks if you need later.
  return (
    <div className="prose prose-neutral dark:prose-invert max-w-none border rounded-xl p-4 bg-background shadow mb-4">
      {title && <h2>{title}</h2>}
      {imageUrl && (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={imageUrl}
          alt={title || "Markdown image"}
          className="rounded-lg my-4 max-w-full"
          style={{ maxHeight: "320px", objectFit: "contain" }}
        />
      )}
      <div className="prose prose-neutral dark:prose-invert max-w-none">
        <SafeMarkdown>{toMDString(content)}</SafeMarkdown>
      </div>
    </div>
  );
};

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
      render: (props) => <MarkdownBlock {...props} />,
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
