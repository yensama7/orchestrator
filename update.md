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
- ~~`proposal.verifier_passes` is never set, so arbiter **stage 2** ("a passing test beats any vote") never fires. Verification runs only on the *winner*, *after* arbitration. So consensus is really stages 1→3→4 only.~~ `[done]` — `_node` now runs `verify.run` on **every** proposal before `arb.decide` and sets `verifier_passes`, so stage 2 gates; the winner's status reuses that same result (no double-verify) (`orchestrator.py:_node`).

**C. ~~Role research is unwired end-to-end.~~** `[done]` — Settings now has a **Roles** panel (`RolesPanel`, `Settings.tsx`) that calls `GET/POST/DELETE /api/roles`; researched roles are merged into the agent role dropdown. Creating a role populates the `roles` table, so `orchestrator._role_profile` injects its skills/resources into node prompts.
~~`/api/roles` CRUD + `research_role` exist, but the frontend never calls them (it uses `catalog.ROLE_HINTS` for the dropdown). So the `roles` table stays empty, and `orchestrator._role_profile` always returns `""`.~~

**D. ~~The §7 Run gate never launches anything.~~** `[done]` — new `POST /api/runs/{id}/run` materialises the DB worktree to a temp dir (path-traversal guarded), calls `runner.gate`, and `runner.start` (`docker compose up`) when ready, reporting `not_containerised`/`no_compose`/`docker_missing` otherwise. The Workspace **▶ Run** button is wired to it (`Workspace.tsx`).
~~`execution/runner.py` has zero callers outside its own demo. `/api/runs/{id}/start` runs the DAG walk, not `runner.start`. So "import a folder → press Run → compose it up" isn't connected.~~

**E. ~~Budget ceiling isn't enforced.~~** `[done]` — `_run` checks `_over_ceiling` before each scheduler level and halts the walk (marking the run `abandoned`, emitting a `blocked` ticker) once `spent_usd >= ceiling_usd` (`orchestrator.py:60-64, 384-389`).
~~`complete(prompt)` is called with no `Budget` (`orchestrator.py:155`); `_charge` accumulates `spent_usd` but never checks it against `ceiling_usd` to halt. A run can blow straight past its cap. The `Budget` dataclass is only used in the settings `_probe`.~~

**F. ~~Everything is pinned to one hardcoded run.~~** `[done]` — multi-run is now reachable:
> - **Current-run state**: new `runs.is_current` flag (partial unique index → at most one per tenant), since seed rows share a txn timestamp and can't be ordered by `created_at`. `_current_run`/`_resolve` (`main.py`) pick the flagged run, else the newest, else the seed fallback.
> - **Run switcher**: new `GET /api/runs` (list + current); a `<select>` in the header (`App.tsx`) lets you view any run; the selected run's real UUID threads into the per-run reads (`useApi(key, run)` in `api.ts`) and into Lineage/Memory/Agents(charts)/Dissent(ledger)/Workspace.
> - **Distinct runs**: `/api/runs/{id}/start` with `new` mints a fresh UUID and marks it current, so every New Run is its own addressable run (`NewRun.tsx` posts `new`). Import/clear/compose-run target the resolved run; import-first with no run creates a draft.
> - Header/workspace now return the real UUID + a short `run/xxxxxx` label instead of the hardcoded `run/4f2a9c`.
>
> Scope note: the live `agents` roster and the dissent **leaderboard** stay global/career (agent stats reset each run — per-run agent snapshots would need a schema change); everything else is per-run.
~~`RUN = seed.RUN_UUID`; every handler ignores its `run_id` path param and uses `RUN`. `/start` reuses the same UUID each time.~~

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
3. ~~**Verify proposals *before* arbitration** and set `verifier_passes`, so stage 2 actually gates.~~ `[done]` — `_node` verifies every proposal before `arb.decide` (see 2.B).
4. ~~**Enforce the ceiling** — pass `Budget` to `complete()` and `break` the DAG walk when `spent >= ceiling`, emitting a `blocked` ticker.~~ `[done]` — `_over_ceiling` gate per level, halts + `blocked` ticker.
5. ~~**Decouple `_pick` from the literal `"senior-dev"`** — trigger consensus whenever `>1` agent shares `node.role`.~~ `[done]` — `_pick` now gives consensus on any irreversible node where `>1` agent shares the role, so user-defined role names get consensus too (`orchestrator.py:_pick`).
6. ~~**Delete `dissent.py`'s dead `DissentLedger`**~~ `[done]` — deleted; the live loop's `_resurrect_and_settle` is the real (SQL) implementation. Removed its test + README references.
7. ~~**Decide on roles UI**: build a Roles panel that calls `/api/roles`, or delete the endpoints.~~ `[done]` — built the panel (see 2.C).
8. ~~**Fix README** claims C/D/A that say "real, populated by real runs" — they aren't yet.~~ `[done]` — A/C/D are now genuinely real (fixed above), so the claims hold; also added Roles + Multi-run rows, dropped the deleted `dissent` self-check/layout refs.

Also note: `build_dag` is a fixed 8-node template that ignores the brief entirely (`plan.py:12`), and `depends_on` is a linear chain, so `scheduler.levels` + `asyncio.gather` never actually parallelize (every level is one node). Fine for the M1 slice, but that's why the DAG looks identical for every run.

Want me to fix any of these? #1 (dissent loop) + #4 (ceiling) are the two that make the biggest correctness difference for the smallest diff — I'd start there.
