// Shared run shapes read by the shell, SpendRail, and the Simple index. These
// mirror the old App.tsx types — the backend contract is unchanged; Phase 5
// replaces these hand-written types with ones generated from OpenAPI.

export type RunData = {
	id: string;
	label: string;
	spec: string;
	template: string;
	mode: string;
	status: string;
	spent: number;
	verified_count: number;
	cost_per_verified: number | null;
	projected: number;
	ceiling: number;
	rail: { label: string; usd: number; color: string }[];
	cache_note: string;
	navfoot: { egress: string; agents: string; blocked: string };
};

export type RunsList = {
	current: string;
	runs: { id: string; name: string; status: string; mode: string; spent: number; current: boolean }[];
};
