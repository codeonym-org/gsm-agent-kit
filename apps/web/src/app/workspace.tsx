import { useQueryClient } from "@tanstack/react-query";
import { Settings2Icon } from "lucide-react";
import { useCallback, useState } from "react";
import { RealtimeProvider } from "@/components/providers/realtime-provider";
import { Empty, Feedback } from "@/components/shared";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select";
import { Separator } from "@/components/ui/separator";
import { SidebarInset, SidebarProvider, SidebarTrigger } from "@/components/ui/sidebar";
import { useDevices } from "@/queries/devices";
import { useWorkspace } from "@/stores/workspace";
import { ApiConnection } from "./_components/api-connection";
import { AppSidebar } from "./_components/app-sidebar";
import { LiveStatus } from "./_components/live-status";
import { DeviceWorkspace } from "./device-workspace";

export function Workspace({ token, connect }: { token: string; connect: (token: string) => void }) {
  const [settingsOpen, setSettingsOpen] = useState(false);
  const queries = useQueryClient();
  const devices = useDevices();
  const selected = useWorkspace((state) => state.selectedDevice);
  const selectDevice = useWorkspace((state) => state.selectDevice);
  const device = devices.data?.find((item) => item.device_id === selected) || devices.data?.[0];
  const authRequired = devices.error?.status === 401;
  const refresh = useCallback(() => {
    void queries.invalidateQueries();
  }, [queries]);
  return (
    <RealtimeProvider token={token} enabled={!!devices.data && !authRequired}>
      <SidebarProvider>
        <AppSidebar onConnection={() => setSettingsOpen(true)} />
        <SidebarInset className="min-w-0">
          <header className="flex h-14 shrink-0 items-center gap-3 border-b px-4">
            <SidebarTrigger aria-label="Open navigation" />
            <Separator orientation="vertical" className="h-4!" />
            <span className="hidden text-sm text-muted-foreground lg:block">Workspace</span>
            <div className="ms-auto flex min-w-0 items-center gap-3">
              <NativeSelect
                aria-label="Cellular device"
                value={device?.device_id || ""}
                onChange={(event) => selectDevice(event.target.value)}
                disabled={!devices.data?.length}
                className="w-40 sm:w-52"
              >
                <NativeSelectOption value="" disabled>
                  Choose a device
                </NativeSelectOption>
                {devices.data?.map((item) => (
                  <NativeSelectOption key={item.device_id} value={item.device_id}>
                    {item.device_id} · {item.adapter.model}
                  </NativeSelectOption>
                ))}
              </NativeSelect>
              <LiveStatus />
              <Button
                variant="ghost"
                size="icon"
                aria-label="API connection"
                onClick={() => setSettingsOpen(true)}
                className="hidden sm:flex"
              >
                <Settings2Icon />
              </Button>
            </div>
          </header>
          <main className="flex min-w-0 flex-1 flex-col gap-6 p-4 md:p-6 lg:p-8">
            <Feedback resource={devices} />
            {devices.error && !devices.data && !authRequired && (
              <Card>
                <CardContent>
                  <Empty
                    title={
                      devices.error.status === 0 ? "Server is offline" : "Unable to load devices"
                    }
                  >
                    Check the backend connection, then retry.
                  </Empty>
                  <Button variant="outline" onClick={refresh}>
                    Retry connection
                  </Button>
                </CardContent>
              </Card>
            )}
            {devices.data?.length === 0 && (
              <Card>
                <CardContent>
                  <Empty title="No configured devices">
                    Add a cellular device to the server configuration to start.
                  </Empty>
                </CardContent>
              </Card>
            )}
            {device && <DeviceWorkspace key={device.device_id} device={device} refresh={refresh} />}
          </main>
        </SidebarInset>
      </SidebarProvider>
      <ApiConnection
        open={settingsOpen || authRequired}
        onOpenChange={setSettingsOpen}
        connected={!!token}
        connect={(value) => {
          setSettingsOpen(false);
          connect(value);
        }}
        disconnect={() => connect("")}
      />
    </RealtimeProvider>
  );
}
