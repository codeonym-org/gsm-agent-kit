import { useRealtime } from "@/components/providers/realtime-provider";
import { cn } from "@/lib/utils";
export function LiveStatus() {
  const { state } = useRealtime();
  const label =
    state === "live"
      ? "Live updates"
      : state === "connecting"
        ? "Connecting live…"
        : state === "unauthorized"
          ? "Live access denied"
          : "Reconnecting live…";
  return (
    <span role="status" className="flex shrink-0 items-center gap-2 text-xs text-muted-foreground">
      <span
        className={cn("size-1.5 rounded-full bg-amber-500", state === "live" && "bg-emerald-500")}
      />
      {label}
    </span>
  );
}
