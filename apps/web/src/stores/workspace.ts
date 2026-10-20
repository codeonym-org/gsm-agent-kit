import { create } from "zustand";

// View state only. Query data belongs to TanStack; credentials stay in providers.
type Workspace = {
  selectedDevice: string;
  composeOpen: boolean;
  selectedRequest?: string;
  selectDevice: (id: string) => void;
  setComposeOpen: (open: boolean) => void;
  selectRequest: (id?: string) => void;
};
export const useWorkspace = create<Workspace>((set) => ({
  selectedDevice: "",
  composeOpen: false,
  selectDevice: (id) => set({ selectedDevice: id, composeOpen: false, selectedRequest: undefined }),
  setComposeOpen: (composeOpen) => set({ composeOpen }),
  selectRequest: (selectedRequest) => set({ selectedRequest }),
}));
