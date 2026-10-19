import { create } from "zustand";

type Draft = { destination: string; text: string; requestId?: string };
const empty: Draft = { destination: "", text: "" };
export const useDrafts = create<{
  drafts: Record<string, Draft>;
  update: (id: string, patch: Partial<Draft>) => void;
  clear: (id: string) => void;
}>((set) => ({
  drafts: {},
  update: (id, patch) =>
    set((state) => ({
      drafts: { ...state.drafts, [id]: { ...(state.drafts[id] || empty), ...patch } },
    })),
  clear: (id) => set((state) => ({ drafts: { ...state.drafts, [id]: { ...empty } } })),
}));
export const emptyDraft = empty;
