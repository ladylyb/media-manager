import { useState } from "react";
import { cn } from "@/lib/utils";
import { ChevronDown, ChevronRight, Copy, Check } from "lucide-react";

interface JsonViewerProps {
  data: unknown;
  title?: string;
  collapsible?: boolean;
  className?: string;
  maxHeight?: string;
}

export function JsonViewer({ data, title, collapsible = true, className, maxHeight = "400px" }: JsonViewerProps) {
  const [collapsed, setCollapsed] = useState(false);
  const [copied, setCopied] = useState(false);
  const jsonStr = JSON.stringify(data, null, 2);

  const handleCopy = async () => {
    await navigator.clipboard.writeText(jsonStr);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className={cn("rounded-lg border bg-card", className)}>
      <div className="flex items-center justify-between px-3 py-2 border-b bg-muted/50">
        <button
          onClick={() => collapsible && setCollapsed(!collapsed)}
          className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground hover:text-foreground"
        >
          {collapsible && (collapsed ? <ChevronRight className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />)}
          {title || "Response"}
        </button>
        <button onClick={handleCopy} className="text-muted-foreground hover:text-foreground">
          {copied ? <Check className="h-3.5 w-3.5 text-success" /> : <Copy className="h-3.5 w-3.5" />}
        </button>
      </div>
      {!collapsed && (
        <pre
          className="p-3 text-xs font-mono overflow-auto scrollbar-thin whitespace-pre-wrap break-all"
          style={{ maxHeight }}
        >
          {jsonStr}
        </pre>
      )}
    </div>
  );
}
