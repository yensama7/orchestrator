import { create } from "zustand";

// Which run the views are scoped to. null = follow the server's current run; a
// uuid = pin that specific run. This is the old App.tsx `selectedRun` state,
// lifted into a store so the Sidebar switcher and every view agree without prop
// drilling. (The resolved run *id* still comes from the `run` query, deduped by
// react-query across the shell + views — see useRun.)
type RunState = {
	selectedRun: string | null;
	setSelectedRun: (id: string | null) => void;
};

export const useRunStore = create<RunState>((set) => ({
	selectedRun: null,
	setSelectedRun: (selectedRun) => set({ selectedRun }),
}));
