import assert from "node:assert/strict";
import { test } from "node:test";
import { bucket, laneFor, type BoardCard } from "./board-presentation.ts";

const card = (over: Partial<BoardCard>): BoardCard => ({
	id: "1", label: "run/aaaaaa", name: "x", status: "active", mode: "simulated",
	spent: 0, verified_count: 0, cost_per_verified: null, open_dissent: false, ...over,
});

test("open dissent wins over status", () => {
	assert.equal(laneFor(card({ status: "passed", verified_count: 5, open_dissent: true })), "dissent");
});

test("status → lane", () => {
	assert.equal(laneFor(card({ status: "active", spent: 0, verified_count: 0 })), "queued");
	assert.equal(laneFor(card({ status: "active", spent: 1.2 })), "working");
	assert.equal(laneFor(card({ status: "passed", verified_count: 0 })), "verifying");
	assert.equal(laneFor(card({ status: "passed", verified_count: 3 })), "verified");
	assert.equal(laneFor(card({ status: "failed" })), "superseded");
	assert.equal(laneFor(card({ status: "abandoned" })), "superseded");
});

test("bucket groups every card into exactly one lane", () => {
	const cards = [card({ id: "a", status: "active", spent: 1 }), card({ id: "b", status: "failed" })];
	const b = bucket(cards);
	assert.equal(b.working.length, 1);
	assert.equal(b.superseded.length, 1);
	assert.equal(Object.values(b).reduce((n, l) => n + l.length, 0), cards.length);
});
