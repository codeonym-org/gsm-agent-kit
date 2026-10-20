import { PlusIcon, RefreshCwIcon } from "lucide-react";
import { lazy, Suspense } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import type { Device } from "@/api/client";
import { Badge, Feedback } from "@/components/shared";
import { ManualSubmission, SubmissionLookup } from "@/components/submission";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { useAssistant, useDeviceStatus } from "@/queries/devices";
import { useWorkspace } from "@/stores/workspace";
import { WorkspaceContext } from "./workspace-context";

export function DeviceWorkspace({ device, refresh }: { device: Device; refresh: () => void }) {
  const status = useDeviceStatus(
    device.device_id,
    device.adapter.capabilities.includes("device.status.read"),
  );
  const assistant = useAssistant(device.device_id);
  const composeOpen = useWorkspace((state) => state.composeOpen);
  const setComposeOpen = useWorkspace((state) => state.setComposeOpen);
  const selectedRequest = useWorkspace((state) => state.selectedRequest);
  const selectRequest = useWorkspace((state) => state.selectRequest);
  const access = status.error
    ? "unreachable"
    : status.data?.availability || device.observation?.availability || "unknown";
  return (
    <WorkspaceContext.Provider value={{ device, status, assistant, refresh }}>
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="space-y-2">
          <div className="flex flex-wrap items-center gap-3">
            <h1 className="text-2xl font-semibold tracking-tight">{device.adapter.model}</h1>
            <Badge tone={access === "ready" ? "success" : "warning"}>{access}</Badge>
          </div>
          <p className="text-sm text-muted-foreground">
            {device.adapter.manufacturer}
            <span className="mx-2 text-border">/</span>
            <span className="font-mono text-xs">{device.device_id}</span>
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" onClick={refresh}>
            <RefreshCwIcon />
            Refresh
          </Button>
          {device.adapter.capabilities.includes("sms.send") && (
            <Button onClick={() => setComposeOpen(true)}>
              <PlusIcon />
              Compose SMS
            </Button>
          )}
        </div>
      </div>
      <Feedback resource={status} />
      <Feedback resource={assistant} />
      <Suspense
        fallback={
          <p role="status" className="text-sm text-muted-foreground">
            Loading workspace…
          </p>
        }
      >
        <Routes>
          <Route path="/overview" element={<OverviewPage />} />
          <Route path="/inbox" element={<InboxPage />} />
          <Route path="/jobs" element={<JobsPage />} />
          <Route path="/device" element={<DevicePage />} />
          <Route path="*" element={<Navigate to="/overview" replace />} />
        </Routes>
      </Suspense>
      <Dialog open={composeOpen} onOpenChange={setComposeOpen}>
        <DialogContent className="max-h-[90dvh] overflow-y-auto sm:max-w-xl">
          <DialogHeader>
            <DialogTitle>Compose SMS</DialogTitle>
            <DialogDescription>Send a message through {device.adapter.model}.</DialogDescription>
          </DialogHeader>
          <ManualSubmission deviceId={device.device_id} onSubmitted={refresh} />
        </DialogContent>
      </Dialog>
      <Dialog
        open={!!selectedRequest}
        onOpenChange={(open) => {
          if (!open) selectRequest();
        }}
      >
        <DialogContent className="max-h-[90dvh] overflow-y-auto sm:max-w-2xl">
          <DialogHeader>
            <DialogTitle>Submission details</DialogTitle>
            <DialogDescription>Durable request progress from your server.</DialogDescription>
          </DialogHeader>
          {selectedRequest && (
            <SubmissionLookup
              key={selectedRequest}
              deviceId={device.device_id}
              requestId={selectedRequest}
              close={() => selectRequest()}
            />
          )}
        </DialogContent>
      </Dialog>
    </WorkspaceContext.Provider>
  );
}

const OverviewPage = lazy(() =>
  import("./overview/page").then((module) => ({ default: module.OverviewPage })),
);

const InboxPage = lazy(() =>
  import("./inbox/page").then((module) => ({ default: module.InboxPage })),
);

const JobsPage = lazy(() => import("./jobs/page").then((module) => ({ default: module.JobsPage })));

const DevicePage = lazy(() =>
  import("./device/page").then((module) => ({ default: module.DevicePage })),
);
