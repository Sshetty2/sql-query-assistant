import { useState, useCallback } from "react";
import { Badge } from "@/components/ui/badge";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogTrigger,
} from "@/components/ui/dialog";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { FileText, Copy, Check, ChevronDown, ChevronRight } from "lucide-react";
import type { PromptContext } from "@/api/types";

interface PromptViewerProps {
  promptContext: PromptContext;
  nodeName: string;
}

function formatCharCount(n: number): string {
  if (n >= 1000) return `${(n / 1000).toFixed(1)}k chars`;
  return `${n} chars`;
}

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = useCallback(() => {
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  }, [text]);

  return (
    <button
      onClick={handleCopy}
      className="inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
      title="Copy to clipboard"
    >
      {copied ? (
        <Check className="h-3 w-3 text-green-500" />
      ) : (
        <Copy className="h-3 w-3" />
      )}
      {copied ? "Copied" : "Copy"}
    </button>
  );
}

function MessageSection({
  role,
  content,
  defaultOpen,
}: {
  role: string;
  content: string;
  defaultOpen: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  const label = role === "system" ? "System Prompt" : "User Prompt";

  return (
    <Collapsible open={open} onOpenChange={setOpen}>
      <CollapsibleTrigger className="flex items-center gap-2 w-full text-left group py-1">
        {open ? (
          <ChevronDown className="h-3.5 w-3.5 text-muted-foreground flex-shrink-0" />
        ) : (
          <ChevronRight className="h-3.5 w-3.5 text-muted-foreground flex-shrink-0" />
        )}
        <span className="text-xs font-medium">{label}</span>
        <Badge variant="outline" className="text-[10px] px-1.5 py-0">
          {formatCharCount(content.length)}
        </Badge>
        <div className="flex-1" />
        <div onClick={(e) => e.stopPropagation()}>
          <CopyButton text={content} />
        </div>
      </CollapsibleTrigger>
      <CollapsibleContent>
        <pre className="mt-1 text-[11px] text-muted-foreground bg-muted/50 rounded-md p-3 overflow-auto whitespace-pre-wrap font-mono leading-relaxed max-h-[50vh] border">
          {content}
        </pre>
      </CollapsibleContent>
    </Collapsible>
  );
}

export function PromptViewer({ promptContext, nodeName }: PromptViewerProps) {
  return (
    <Dialog>
      <DialogTrigger asChild>
        <button
          className="inline-flex items-center justify-center rounded p-0.5 text-blue-400 dark:text-blue-400 hover:text-blue-600 dark:hover:text-blue-300 hover:bg-blue-50 dark:hover:bg-blue-950/30 transition-colors"
          title="View LLM prompt"
          onClick={(e) => e.stopPropagation()}
        >
          <FileText className="h-3.5 w-3.5" />
        </button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-3xl max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-base">
            LLM Prompt
            <Badge variant="outline" className="text-xs font-normal">
              {promptContext.model}
            </Badge>
          </DialogTitle>
          <DialogDescription>
            Prompt sent to the LLM during the "{nodeName}" step
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-2">
          {promptContext.messages.map((msg, i) => (
            <MessageSection
              key={i}
              role={msg.role}
              content={msg.content}
              defaultOpen={i === promptContext.messages.length - 1}
            />
          ))}
        </div>
      </DialogContent>
    </Dialog>
  );
}
