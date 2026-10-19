import { BotIcon, RadioIcon, SignalIcon, WorkflowIcon } from "lucide-react";
import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { AssistantPolicy } from "../_components/assistant-policy";
import { BalancePanel } from "../_components/balance-panel";
import { MessageList } from "../inbox/message-list";
import { useDeviceWorkspace } from "../workspace-context";
export function OverviewPage() {
  const { device, status, assistant } = useDeviceWorkspace();
  const jobCount = Object.values(assistant.data?.jobs || {}).reduce(
    (total, value) => total + value,
    0,
  );
  const metrics = [
    {
      title: "Network",
      value: status.data?.network_type || "—",
      detail: status.data?.network_provider || "Carrier not observed",
      icon: RadioIcon,
    },
    {
      title: "Signal strength",
      value: status.data?.signal_percent == null ? "—" : `${status.data.signal_percent}%`,
      detail: "Latest device observation",
      icon: SignalIcon,
    },
    {
      title: "Automatic replies",
      value: assistant.data ? (assistant.data.auto_reply ? "Enabled" : "Disabled") : "—",
      detail: assistant.data?.dry_run ? "Dry run · no automatic SMS" : "Live submission mode",
      icon: BotIcon,
    },
    {
      title: "Reply jobs",
      value: assistant.data ? String(jobCount) : "—",
      detail: `${assistant.data?.jobs.completed || 0} accepted · ${assistant.data?.jobs.interrupted || 0} interrupted`,
      icon: WorkflowIcon,
    },
  ];
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 gap-4 xl:grid-cols-4">
        {metrics.map(({ title, value, detail, icon: Icon }) => (
          <Card key={title} className="gap-3">
            <CardHeader className="flex flex-row items-center justify-between gap-2">
              <CardDescription>{title}</CardDescription>
              <Icon className="size-4 text-muted-foreground" />
            </CardHeader>
            <CardContent className="space-y-2">
              <div className="text-2xl font-semibold tracking-tight">{value}</div>
              {title === "Signal strength" && status.data?.signal_percent != null && (
                <Progress value={status.data.signal_percent} className="h-1" />
              )}
              <p className="text-xs text-muted-foreground">{detail}</p>
            </CardContent>
          </Card>
        ))}
      </div>
      <div className="grid items-start gap-6 xl:grid-cols-[minmax(0,1fr)_22rem]">
        <div className="space-y-6">
          <MessageList preview />
          <Card>
            <CardHeader>
              <CardTitle role="heading" aria-level={2}>
                {device.adapter.adapter_id}
              </CardTitle>
              <CardDescription>
                {device.adapter.manufacturer} · Adapter v{device.adapter.version} ·{" "}
                {device.adapter.capabilities.length} capabilities
              </CardDescription>
            </CardHeader>
            <CardContent>
              <Button asChild variant="outline" size="sm">
                <Link to="/device">Device details</Link>
              </Button>
            </CardContent>
          </Card>
        </div>
        <div className="space-y-6">
          <AssistantPolicy assistant={assistant.data} />
          <BalancePanel
            deviceId={device.device_id}
            supported={device.adapter.capabilities.includes("carrier.balance.read")}
          />
          <p className="px-1 text-xs leading-relaxed text-muted-foreground">
            Submission acceptance confirms the device took the message. It does not confirm
            recipient delivery.
          </p>
        </div>
      </div>
    </div>
  );
}
