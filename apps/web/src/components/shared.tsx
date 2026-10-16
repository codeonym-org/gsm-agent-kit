import type { ReactNode } from "react";
import type { Resource } from "../use-resource";

export function Badge({ children, tone = "neutral" }: { children: ReactNode; tone?: string }) {
  return <span className={`badge ${tone}`}>{children}</span>;
}

export function Feedback({ resource }: { resource: Resource<unknown> }) {
  if (resource.loading)
    return (
      <p role="status" className="notice">
        {resource.data ? "Refreshing…" : "Loading…"}
      </p>
    );
  if (resource.error)
    return (
      <p role="alert" className="notice error">
        {resource.error.message}
        {resource.data ? " Showing the last observation." : ""}
      </p>
    );
  return null;
}

export function Empty({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="empty">
      <span className="empty-mark" aria-hidden="true">
        ↳
      </span>
      <h3>{title}</h3>
      <p>{children}</p>
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
