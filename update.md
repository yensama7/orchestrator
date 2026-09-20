Audited the backend and frontend end-to-end. Here's what I found, grouped by what you asked. Evidence is `file:line`.

## 1. Uncommitted modifications
Only your chart work is dirty — nothing else has drifted:
- `web/src/components.tsx`, `web/src/styles.css`, `web/src/views/Agents.tsx` (the `Pie` component + graph polish). Not committed yet.

## 2. Incomplete integrations (built, but not wired)
These are the real gaps — code exists and is tested in isolation, but nothing calls it in the live path.

**A. ~~Dissent resurrect/settle loop — the headline feature is half-wired.~~** `[done]` — wired. `_node` now calls `_resurrect_and_settle` on verify-fail (`orchestrator.py:110-114`), which walks dormant dissents highest-stage-first, re-verifies each stored proposal, settles `vindicated`/`refuted`, and `_bump_vind` recomputes `agents.vind_pct` from settled rows. `resurrected`/`vindicated`/`refuted` now populate from real runs.
~~`arbitration/dissent.py` (`DissentLedger.resurrect`/`settle`) is **dead code** — only its own `demo()` calls it (grep confirms zero other callers). In the real loop, `_node` inserts dissent rows as `dormant` then, on verify-fail, does nothing (`orchestrator.py:87-106`) — no resurrection, no retry with the runner-up's proposal. Consequence: `resurrected`/`vindicated`/`refuted` in the leaderboard (`main.py:114-122`) and `agents.vind_pct` (`main.py:431`) are **always 0/"—" from real runs**. README claims "resurrect/settle ✅ real, populated by real runs" — that's overstated.~~

**B. The deterministic arbiter runs on fake/absent inputs.** Two of its five stages are effectively dead:
- ~~`proposal.agreement` is synthetic — `round(0.9 - 0.25*i, 3)` by dispatch order, not real inter-proposal agreement. It just biases toward whichever agent went first.~~ `[done]` — `_agreements()` now computes each proposal's mean cosine to its peers' `choice` text via `embed()` (`orchestrator.py:_propose`), so stage 3's `agree` weight is real.
- `proposal.verifier_passes` is never set, so arbiter **stage 2** ("a passing test beats any vote", `arbiter.py:52`) never fires. Verification runs only on the *winner*, *after* arbitration (`orchestrator.py:87`). So consensus is really stages 1→3→4 only.

**C. Role research is unwired end-to-end.** `/api/roles` CRUD + `research_role` exist (`main.py:267-298`), but the frontend never calls them (it uses `catalog.ROLE_HINTS` for the dropdown, `Settings.tsx:163`). So the `roles` table stays empty, and `orchestrator._role_profile` (`orchestrator.py:224`) always returns `""`. The whole "central agent researches skills/resources for a role" feature is dark.

**D. The §7 Run gate never launches anything.** `execution/runner.py` (compose detection + `docker compose up`) has zero callers outside its own demo (grep confirms). `/api/runs/{id}/start` runs the DAG walk (`orchestrator.start`), not `runner.start`. So "import a folder → press Run → compose it up" isn't connected.

**E. ~~Budget ceiling isn't enforced.~~** `[done]` — `_run` checks `_over_ceiling` before each scheduler level and halts the walk (marking the run `abandoned`, emitting a `blocked` ticker) once `spent_usd >= ceiling_usd` (`orchestrator.py:60-64, 384-389`).
~~`complete(prompt)` is called with no `Budget` (`orchestrator.py:155`); `_charge` accumulates `spent_usd` but never checks it against `ceiling_usd` to halt. A run can blow straight past its cap. The `Budget` dataclass is only used in the settings `_probe`.~~

**F. Everything is pinned to one hardcoded run.** `RUN = seed.RUN_UUID` (`main.py:29`); every handler ignores its `run_id` path param and uses `RUN`. `/start` reuses the same UUID each time. There's partial multi-run plumbing (`queries` selects `runs WHERE id<>$1`), but no history/multi-run is reachable.

## 3. Deferred (explicitly marked — these are honest)
`grep -rn "ponytail:"` — all documented, with upgrade paths:
- `runner.py:55` — bare `docker compose up`, no gVisor/egress netns yet.
- `api.py:111` — OpenAI-compatible cost billed at full input rate (cache discount not modeled).
- `schema.sql:6` — single-file schema, no migrations dir. `schema.sql:182` — API keys plaintext at rest (needs KMS before shipping).
- `orchestrator.py:32,225` — module-dict run context; per-dispatch role query.
- `web/index.html:7` — CDN fonts, not self-hosted.

## 4. Ways to make it better (ranked by value/effort)
1. ~~**Wire resurrect+settle on verify-fail** (`orchestrator.py:_node`). Biggest win — closes the headline feature and makes `vind_pct`/leaderboard real. ~15 lines: on fail, pick highest dormant dissent, re-verify its proposal, `settle()` accordingly.~~ `[done]` — `_resurrect_and_settle` + `_bump_vind`.
2. ~~**Compute real `agreement`** — you already have `embed()`; cosine between proposal `choice` texts is a few lines and makes stage 3 meaningful.~~ `[done]` — `_agreements()` in `_propose`.
3. **Verify proposals *before* arbitration** and set `verifier_passes`, so stage 2 actually gates.
4. ~~**Enforce the ceiling** — pass `Budget` to `complete()` and `break` the DAG walk when `spent >= ceiling`, emitting a `blocked` ticker.~~ `[done]` — `_over_ceiling` gate per level, halts + `blocked` ticker.
5. **Decouple `_pick` from the literal `"senior-dev"`** (`orchestrator.py:114`) — trigger consensus whenever `>1` agent shares `node.role`. Right now, if a user's agent role doesn't exactly match the template strings (`planner/senior-dev/frontend/security`, `plan.py:12`), every node collapses to `flat[0]` — one agent, no consensus.
6. **Delete `dissent.py`'s dead `DissentLedger`** (once #1 reuses its logic in SQL) or route the loop through it — right now it's a tested no-op.
7. **Decide on roles UI**: build a Roles panel that calls `/api/roles`, or delete the endpoints + `research.py`.
8. **Fix README** claims C/D/A that say "real, populated by real runs" — they aren't yet.

Also note: `build_dag` is a fixed 8-node template that ignores the brief entirely (`plan.py:12`), and `depends_on` is a linear chain, so `scheduler.levels` + `asyncio.gather` never actually parallelize (every level is one node). Fine for the M1 slice, but that's why the DAG looks identical for every run.

Want me to fix any of these? #1 (dissent loop) + #4 (ceiling) are the two that make the biggest correctness difference for the smallest diff — I'd start there.
