import { InboxIcon, LoaderCircleIcon } from "lucide-react";
import type { ReactNode } from "react";
import { cn } from "@/lib/utils";
import type { Resource } from "@/queries/devices";
import { Alert, AlertDescription } from "./ui/alert";
import { Badge as UiBadge } from "./ui/badge";

export function Badge({ children, tone = "neutral" }: { children: ReactNode; tone?: string }) {
  return (
    <UiBadge
      variant="outline"
      className={cn(
        "badge shrink-0 gap-1.5 font-normal",
        tone === "success" && "border-emerald-600/20 text-emerald-700 dark:text-emerald-400",
        tone === "warning" && "border-amber-600/20 text-amber-700 dark:text-amber-400",
      )}
    >
      {children}
    </UiBadge>
  );
}
export function Feedback({ resource }: { resource: Resource<unknown> }) {
  if (resource.loading && !resource.data)
    return (
      <p role="status" className="flex items-center gap-2 py-3 text-sm text-muted-foreground">
        <LoaderCircleIcon className="size-4 animate-spin" />
        Loading…
      </p>
    );
  if (resource.error)
    return (
      <Alert variant="destructive">
        <AlertDescription>
          {resource.error.message}
          {resource.data ? " Showing the last observation." : ""}
        </AlertDescription>
      </Alert>
    );
  return null;
}
export function Empty({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="flex min-h-60 flex-col items-center justify-center gap-3 p-8 text-center">
      <div className="flex size-12 items-center justify-center rounded-xl border bg-muted/40">
        <InboxIcon className="size-5 text-muted-foreground" />
      </div>
      <div className="space-y-1.5">
        <h3 className="text-sm font-medium">{title}</h3>
        <p className="max-w-sm text-sm text-muted-foreground">{children}</p>
      </div>
    </div>
  );
}
export function time(value: string | undefined | null) {
  if (!value) return "Not observed";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}
export const labels: Record<string, string> = {
  queued: "Queued",
  generating: "Generating reply",
  prepared: "Reply prepared",
  submitting: "Submitting",
  completed: "Submission accepted",
  ignored: "Ignored",
  dry_run: "Dry-run preview",
  failed: "Failed",
  interrupted: "Interrupted",
  pending: "Pending",
  in_progress: "In progress",
  not_submitted: "Not submitted",
  accepted: "Accepted",
  rejected: "Rejected",
  unknown: "Unknown outcome",
};
export function outcomeTone(state: string) {
  return state === "accepted" || state === "completed"
    ? "success"
    : ["unknown", "in_progress", "interrupted", "failed", "rejected"].includes(state)
      ? "warning"
      : "neutral";
}
