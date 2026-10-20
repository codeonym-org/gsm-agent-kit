import { BotIcon } from "lucide-react";
import type { Assistant } from "@/api/client";
import { Badge } from "@/components/shared";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
export function AssistantPolicy({ assistant }: { assistant?: Assistant }) {
  const mode = !assistant?.auto_reply
    ? "Auto-reply disabled"
    : assistant.dry_run
      ? "Dry run"
      : "Live replies";
  return (
    <Card>
      <CardHeader>
        <CardTitle
          role="heading"
          aria-level={2}
          className="flex items-center justify-between gap-3"
        >
          <span className="flex items-center gap-2">
            <BotIcon className="size-4 text-muted-foreground" />
            AI assistant
          </span>
          <Badge
            tone={assistant?.auto_reply ? (assistant.dry_run ? "warning" : "success") : "neutral"}
          >
            {mode}
          </Badge>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <p className="text-sm text-muted-foreground">
          {!assistant?.auto_reply
            ? "Automatic replies are disabled for this workspace."
            : assistant.dry_run
              ? "Replies are prepared for review without submitting SMS."
              : "Responding to eligible incoming messages automatically."}
        </p>
        <div className="rounded-lg border bg-muted/30 p-3 text-xs leading-relaxed text-muted-foreground">
          Reply mode and SMS budgets are managed by your server configuration.
        </div>
      </CardContent>
    </Card>
  );
}
