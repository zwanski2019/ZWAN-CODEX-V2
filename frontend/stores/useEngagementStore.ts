import { create } from "zustand";
import type { Engagement } from "@/lib/api";

interface EngagementStore {
  activeId: string | null;
  setActiveId: (id: string | null) => void;
  engagements: Engagement[];
  setEngagements: (e: Engagement[]) => void;
}

export const useEngagementStore = create<EngagementStore>((set) => ({
  activeId: null,
  setActiveId: (id) => set({ activeId: id }),
  engagements: [],
  setEngagements: (engagements) => set({ engagements }),
}));
