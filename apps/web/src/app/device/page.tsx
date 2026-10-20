import { CheckIcon } from "lucide-react";
import { Badge } from "@/components/shared";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { AssistantPolicy } from "../_components/assistant-policy";
import { BalancePanel } from "../_components/balance-panel";
import { useDeviceWorkspace } from "../workspace-context";

const capabilities: Record<string, string> = {
  "device.status.read": "Device status",
  "sms.inbox.read": "SMS inbox",
  "sms.send": "SMS submission",
  "carrier.balance.read": "Carrier balance",
};
export function DevicePage() {
  const { device, assistant } = useDeviceWorkspace();
  const variant = device.observation?.variant;
  const facts = [
    ["Logical device", device.device_id],
    ["Manufacturer", device.adapter.manufacturer],
    ["Adapter", device.adapter.adapter_id],
    ["Build version", `v${device.adapter.version}`],
    ...(variant
      ? [
          ["Firmware", variant.firmware || "Unknown"],
          ["Hardware revision", variant.hardware_revision || "Unknown"],
          ["Operating mode", variant.operating_mode || "Unknown"],
        ]
      : []),
  ];
  return (
    <div className="grid items-start gap-6 xl:grid-cols-[minmax(0,1fr)_22rem]">
      <Card>
        <CardHeader>
          <CardTitle role="heading" aria-level={2}>
            Device details
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-6">
          <dl className="divide-y">
            {facts.map(([label, value]) => (
              <div key={label} className="flex flex-wrap justify-between gap-2 py-3 text-sm">
                <dt className="text-muted-foreground">{label}</dt>
                <dd className="max-w-full break-all font-medium">{value}</dd>
              </div>
            ))}
          </dl>
          <div className="space-y-3">
            <h3 className="text-sm font-medium">Supported capabilities</h3>
            <div className="flex flex-wrap gap-2">
              {device.adapter.capabilities.map((capability) => (
                <Badge key={capability}>
                  <CheckIcon className="size-3" />
                  {capabilities[capability] || capability}
                </Badge>
              ))}
            </div>
            <p className="text-sm text-muted-foreground">
              Support describes the adapter contract. Current availability is observed separately.
            </p>
          </div>
          <div className="flex items-center gap-2 border-t pt-4 text-sm">
            <span className="text-muted-foreground">Verification</span>
            <Badge>{device.observation?.compatibility || "No hardware verification"}</Badge>
          </div>
        </CardContent>
      </Card>
      <div className="space-y-6">
        <AssistantPolicy assistant={assistant.data} />
        <BalancePanel
          deviceId={device.device_id}
          supported={device.adapter.capabilities.includes("carrier.balance.read")}
        />
      </div>
    </div>
  );
}
