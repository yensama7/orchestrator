// Pure status→lane mapping for the live Kanban board (§P4). Mirrors the
// reference's session-presentation.ts, but our lanes come from our own domain
// facts (run status + mode + dissent presence), not Git sessions. No React, no
// fetch here — kept pure so the mapping is unit-testable (board-presentation.test.ts).

export type BoardCard = {
	id: string;
	label: string; // short console label, run/xxxxxx
	name: string;
	status: string; // active | passed | failed | abandoned
	mode: string; // simulated | live
	spent: number;
	verified_count: number;
	cost_per_verified: number | null;
	open_dissent: boolean;
};

export type Lane = "queued" | "working" | "dissent" | "verifying" | "verified" | "superseded";

// Order = left→right on the board. `color` is a chart-palette name (charts.tsx HEX).
export const LANES: { key: Lane; label: string; color: string }[] = [
	{ key: "queued", label: "Queued", color: "steel" },
	{ key: "working", label: "Working", color: "amber" },
	{ key: "dissent", label: "Dissent", color: "violet" },
	{ key: "verifying", label: "Verifying", color: "steel" },
	{ key: "verified", label: "Verified", color: "sage" },
	{ key: "superseded", label: "Superseded", color: "dimmer" },
];

// An open dissent "needs you", so it wins over the run's own status. Otherwise:
// failed/abandoned → superseded; passed → verified once something cleared a gate,
// else still verifying; active → working, or queued if nothing has run yet.
export function laneFor(card: BoardCard): Lane {
	if (card.open_dissent) return "dissent";
	switch (card.status) {
		case "failed":
		case "abandoned":
			return "superseded";
		case "passed":
			return card.verified_count > 0 ? "verified" : "verifying";
		default: // active (and any unknown status) is in-flight
			return card.spent === 0 && card.verified_count === 0 ? "queued" : "working";
	}
}

export function bucket(cards: BoardCard[]): Record<Lane, BoardCard[]> {
	const out = Object.fromEntries(LANES.map((l) => [l.key, [] as BoardCard[]])) as Record<Lane, BoardCard[]>;
	for (const c of cards) out[laneFor(c)].push(c);
	return out;
}
