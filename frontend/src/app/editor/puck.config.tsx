import type { Config } from '@measured/puck'

// 🧩 Full Panel Components
import ActionQueue from '../../components/ActionQueue/ActionQueuePanel'
import AskAgent from '../../components/AskAgent/AskAgent'
import DocsSyncPanel from '../../components/DocsSyncPanel'
import DocsViewer from '../../components/DocsViewer/DocsViewer'
import LogsPanel from '../../components/LogsPanel/LogsPanel'
import MemoryPanel from '../../components/MemoryPanel'
import Navbar from '../../components/Navbar/Navbar'
import SearchPanel from '../../components/SearchPanel'
import Sidebar from '../../components/Sidebar/Sidebar'
import StatusPanel from '../../components/StatusPanel'
import MetricsChart from '../../components/MetricsCharts/MetricsCharts'

// 🪄 UI Primitives (shadcn)
import { Badge } from '../../components/ui/badge'
import { Button } from '../../components/ui/button'
import { Card } from '../../components/ui/card'
import { Input } from '../../components/ui/input'
import { Label } from '../../components/ui/label'
import { Progress } from '../../components/ui/progress'
import { Textarea } from '../../components/ui/textarea'

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

    // 🧩 UI Elements
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
}
export default config 
