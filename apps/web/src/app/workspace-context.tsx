import { createContext, useContext } from "react";
import type { Assistant, Device, Status } from "@/api/client";
import type { Resource } from "@/queries/devices";
export type WorkspaceContextValue = {
  device: Device;
  status: Resource<Status>;
  assistant: Resource<Assistant>;
  refresh: () => void;
};
export const WorkspaceContext = createContext<WorkspaceContextValue | null>(null);
export function useDeviceWorkspace() {
  const value = useContext(WorkspaceContext);
  if (!value) throw new Error("Device workspace is required");
  return value;
}
