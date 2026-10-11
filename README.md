# Lineage — orchestrator console

Multi-agent build orchestration with supersession-aware memory, a deterministic
arbiter, and a dissent ledger. This repo is the **M1 vertical slice** of
[`plan.md`](./plan.md): the console (faithful to `references/`), a typed
backend, the real DB schema, and a compose gate — built first because the plan
says to (§17).

## Run it

```bash
docker compose up --build
```

- Console → http://localhost:5173
- API → http://localhost:8000/api/health
- Postgres (pgvector) → localhost:5432 (`lineage`/`lineage`)

## What's here

| Area | Status |
|------|--------|
| Six views (New run, Lineage, Memory, Agents, Dissent, Workspace) | ✅ §19, tokens §12 |
| Header spend rail + quota, rail-nav, **live SSE ticker** (tails episodic_events) | ✅ |
| **Postgres persistence** — every view DB-backed, mutated live by the engine | ✅ |
| **Tenancy/RLS** — enabled + **forced**, app connects as `NOBYPASSRLS` role (§18.4) | ✅ isolation verified |
| Contracts (Pydantic, `extra=forbid` injection defence) | ✅ §20.2 |
| **Live orchestrator** — DAG walk, consensus arbitration, dissent, verify, leases | ✅ §17 M1+consensus |
| **Verifies behavior** (runs the produced code: build/test/lint) | ❌ **no (M1)** — verifiers are structural only; lands in Phase 1 |
| **Run mode** — every run tagged `simulated`/`live`; a simulated run can't earn verified-skill credit | ✅ §P0 truth-in-labeling, self-checked |
| Deterministic five-stage arbiter | ✅ real + self-checked, §18.3 |
| Dissent ledger (record / resurrect / settle, all over SQL) | ✅ real, populated by live runs, §8 |
| **Dissent rollback** — one-click Resurrect (settle in place) + Fork from any dissent | ✅ real, §8/§19.7 |
| **Replay & forking** — fork a run at any node, carry prior decisions + worktree, re-run | ✅ real, §16.5 |
| **Template drift** — nightly sweep (npm/PyPI/OSV), re-verify stale, quarantine + pitfall | ✅ real + self-checked, §18.2 |
| Roles — user-defined, central agent researches skills/resources into prompts | ✅ real, `/api/roles` + Settings panel, §3 |
| Multi-run — every New Run is a distinct run; switch/view any from the header | ✅ real, `is_current` + `?run=`, §16 |
| Transports — API (metered), subscription (headless CLI), local (Ollama/echo) | ✅ §4, §20.3 |
| Memory — embeddings, hybrid BM25+vector+RRF+rerank, supersede, distil | ✅ §20.7 |
| Planning — extract / match / roster / plan (fingerprint → DAG) | ✅ §3 |
| Security — broker, taint, egress allowlist, gitleaks secret scan | ✅ real + self-checked, §11 |
| Sandbox pool — warm dirs, opt-in Docker+gVisor (`SANDBOX_DOCKER=1`) | ✅ §14 |
| Compose run-gate | ✅ real + self-checked, §7 |
| Editor — CodeMirror 6, extension-only detection, lazy per-language grammar, blame gutter | ✅ §13, §19.8 |

## Live demo

1. **Settings** → add a model (pick any of the 10 providers; enter an API key,
   or choose `local`/`subscription`) → optionally define a **Role** (the central
   agent researches its skills/resources) → **Add agent** (bind a role to the
   model). Nothing is pre-populated — the roster is what you build.
2. **Workspace** → *Import folder* to load a real project (the compose gate lights
   up if it finds a compose file).
3. **New run** → brief → *Extract fingerprint* → *Start run*.
4. Watch it go live: **Agents** states/calls/pass-rates, **Dissent** ledger,
   **Lineage**/**Memory** graphs, **charts**, header spend rail — all poll every
   4s and stream over SSE. Hover any graph node (inheritance edges highlight
   amber), doughnut segment (centre fills with value + %), or the spend line
   (crosshair + computed *saved* figure) per `prompt_hover.md`.

Everything renders from live tables — no mockup snapshot. Empty by default,
populated by what you configure and run.

## What still needs real credentials/hardware to light up

Everything runs offline with sensible fallbacks; these get *better*, not
*enabled*, with config:

- **Real model calls** — set `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` (metered) or
  install the headless CLIs (subscription). Without them the local echo runs
  every node for free, so the loop still completes — but any run that touched the
  echo is tagged **`simulated`** (see the header badge) and cannot earn
  verified-skill credit or feed a benchmark. A run only becomes **`live`** once a
  real model *and* a behavioral verifier gate it (behavioral verifiers land in
  Phase 1, so today every run is honestly `simulated`).
- **Real embeddings** — set `EMBED_URL` to a text-embeddings-inference server
  (BGE-M3, §15). The local hashed embedder is deterministic but semantically
  weak by design; it exists so the retrieval pipeline runs with no GPU.
- **Kernel-enforced isolation** — `SANDBOX_DOCKER=1` + a `runsc` (gVisor)
  runtime turns the sandbox pool into read-only, network-none containers.

Grep the deliberate stand-ins: `grep -rn "ponytail:" backend web`.

## Verify

```bash
cd backend && python -m tests.test_core   # arbiter, run-gate, scheduler, embed,
                                          # egress, taint, broker, scan, envelope
```

RLS isolation, live-run state changes, and hybrid retrieval are verified against
the running stack (see the build notes / your own `docker compose` session).

## Layout

```
backend/lineage/
  contracts/     Pydantic models (envelope, node, fingerprint, usage)
  transports/    base · api · subscription · local  (§4)
  planning/      extract · match · roster · plan     (§3)
  execution/     scheduler · leases · verify · pool · runner · orchestrator
                 · worktree · reverify · fork         (§16.5, §18.2)
  arbitration/   arbiter · scores · dissent           (§8, §18.3, §20.6)
  memory/        embed · retrieval · store · supersede · distil
                 · manifest · registry · drift        (§5, §18.2, §20.7)
  security/      broker · taint · egress · scan       (§11)
  db/            schema.sql · tenancy · seed          (§18.4)
  api/           main (routes + SSE)
web/src/         shell (App) · components · CodeEditor · lang/registry (§13)
                 · views/{newrun,lineage,memory,agents,dissent,workspace}
compose.yaml     db (pgvector, RLS applied on boot) + backend (app role) + web
```
