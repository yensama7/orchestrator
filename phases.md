# Lineage — Phases to Real Value

This document is the roadmap from what Lineage *is* (a faithful, well-wired M1
vertical slice) to what it *claims to be* (a system that makes software more
correct, cheaper, faster, and safer than a single agent would). It is written
to be read by a skeptic. Every phase states what it entails, the engineering
practices it demands, how we know it's done, and which real issue or suggestion
it closes.

It also answers, directly and without marketing, the only questions that
matter:

> **Why should I use this orchestrator? How does it help my agentic use? What
> are the benefits?**

The honest answer today is *"not yet — here's why, and here's the path."* The
honest answer after Phase 3 is a number on a benchmark. That gap is the whole
point of this file.

---

## Part A — The verdict as it stands today (strict)

I am judging the system as a build engine that takes a brief and produces
working software. Not as a UI demo. On that bar:

### What is genuinely good

- **The console and plumbing are real.** Postgres persistence, forced RLS
  tenancy (verified), SSE ticker, Pydantic contracts with `extra=forbid`, a
  deterministic five-stage arbiter with a real self-check, a dissent ledger
  over SQL, leases, worktrees, fork/replay. This is not a mockup; the tables
  mutate live. That is more than most "agent orchestrator" repos can say.
- **The arbiter is honestly deterministic.** Same inputs → same winner, ties
  held for a human instead of coin-flipped (`arbiter.py:65`). That is the
  correct design and it is implemented correctly.
- **The recent wiring pass (update.md) was real work.** Resurrect/settle,
  real semantic agreement, verify-before-arbitrate, ceiling enforcement,
  multi-run — these were dead code and are now live. Credit where due.

### What is theater (the hard truth)

1. **The DAG is a lie.** `plan.py:12` is a hardcoded 8-node storefront script
   (`schema.design → auth.session → payments.webhook → api.orders → ui.build`).
   **Every run builds this, regardless of the brief.** Ask it for a portfolio
   site and it plans a payments webhook. Fingerprint extraction is cosmetic —
   its output never changes the plan. This single fact invalidates the headline
   claim "build software from a brief."

2. **Verification does not verify software.** The only verifiers
   (`verify.py`) are `envelope.valid` (choice is a non-empty string),
   `json.parses`, and `confidence.min` (a self-reported float ≥ 0.5). Nothing
   runs the produced code, no test executes, no build happens. "Executable
   ground truth beats any vote" is true only if "ground truth" means "the JSON
   has a field." So the claim *"makes software MORE CORRECT"* is currently
   unsupported by anything measurable.

3. **Offline, nothing is built.** The local transport echoes keyword stubs —
   `JWT`, `postgres 16`, `paystack`, `proceed` (`local.py:46`). Without real
   API keys *and* a real verifier, the entire loop is a choreographed animation
   of a build, not a build.

4. **No outcome metric exists.** suggestion.md is right: the system should
   optimize *cost per verified successful result*, not activity. Today it
   measures `cost/model-call` and agent `pass_rate` against trivial verifiers.
   There is no number that answers "did Lineage help?"

5. **Scores are credulous.** `AgentScore` (`scores.py`) uses raw rates. A 5/5
   agent outranks a 950/1000 agent. No shrinkage, no sample floor, no
   new-vs-experienced separation. Lineage can promote an agent on luck.

### One-line verdict

> **Today Lineage is a beautifully engineered chassis with a cardboard engine.**
> The orchestration, persistence, security scaffolding, and UI are production-
> grade. The thing they orchestrate — planning and verification — is a fixed
> script checked by structural asserts. It cannot yet answer "why use this,"
> because it cannot yet demonstrate a single verified outcome that a bare agent
> couldn't produce.

**Grade as-is: C+.** (Infrastructure: A-. Core value delivery: D.)

---

## Part B — The four questions this system must answer

suggestion.md sets the bar: a change is only worth shipping if it makes the
software **more correct, cheaper, faster, or safer**. Every phase below is
mapped to at least one. If a phase can't name which, it doesn't ship.

| Question | What Lineage must prove | Lands in |
|----------|-------------------------|----------|
| More **correct**? | Real verifiers (tests/build/lint) gate decisions; resurrect/settle recovers from wrong winners. | Phase 1, 3 |
| **Cheaper**? | Complexity-routed model tiers + cost-per-verified-result optimization, not a "40% local" quota. | Phase 2 |
| **Faster**? | A DAG that actually parallelizes independent work + warm sandbox reuse. | Phase 1, 4 |
| **Safer**? | Defense-in-depth secret redaction + sandboxed execution adapters, as first-class CI tests. | Phase 4 |

And the target user is explicitly **User B** (teams that repeatedly build
SaaS/APIs/payment/internal tools), not the student building one portfolio site.
Lineage earns its complexity only on repeated, verification-heavy work where a
wrong answer is expensive. Phases are ordered to make that user's case first.

---

## Part C — Issues found in the system scan

Grounded, with evidence. Grouped by severity. The `[P#]` tag is the phase that
closes it.

### Blocking (the value prop depends on these)

- **`plan.py:12` — static DAG ignores the brief.** `_TEMPLATE_DAG` is a fixed
  storefront. `build_dag` never reads the fingerprint beyond the domain for
  pitfall lookup. Linear `depends_on` chain means `scheduler.levels` +
  `asyncio.gather` never parallelize — every "level" is one node (confirmed in
  update.md §Also note). `[P1]`
- **`verify.py:44-62` — verifiers are structural, not behavioral.** No build,
  test, lint, or typecheck execution. A proposal "passes" by having a non-empty
  `choice`. `[P1]`
- **`local.py:46` — echo stubs stand in for real generation.** Fine as a
  no-GPU fallback for plumbing, but it means offline runs produce nothing real;
  this must be labeled honestly in the UI and never counted in benchmarks. `[P1]`
- **No cost-per-verified-result metric anywhere.** `_charge` accumulates
  `spent_usd`; nothing divides spend by verified successes. `[P2]`

### High (correctness/economics of the engine)

- **`scores.py:9` — no confidence-aware scoring.** Raw `pass_rate` /
  `vindication_rate`; no Bayesian shrinkage, no minimum-sample threshold, no
  new/experienced/specialist separation. Premature promotion on luck. `[P3]`
- **Dissent has 3 states, not a retention ladder.** `orchestrator.py:393`
  settles to `vindicated`/`refuted` only. suggestion.md wants
  `archive → low → high → promote-to-knowledge`. Vindicated dissent never
  becomes reusable knowledge. `[P3]`
- **Memory model is `Failure → MUST NOT`** (pitfalls as hard constraints,
  `plan.py:29`). suggestion.md wants
  `Observation → Hypothesis → Verification → Confidence → Knowledge`. The
  current model can't represent "tried, worked" — only "tried, banned." `[P3]`
- **No complexity scorer.** Every node gets the same treatment; a one-line
  config change and a payment flow are routed identically. `[P2]`

### Medium (robustness, security depth, UX)

- **Secret handling is egress-only.** `security/` has broker/taint/egress/scan;
  update.md confirms no redaction at prompt/output/DB/telemetry/log. A secret
  can reach logs long before the egress scanner. `[P4]`
- **Single execution path (compose).** `runner.py` gates on compose only;
  suggestion.md's Execution Adapter (Compose / Dockerfile / native sandbox,
  each with a verifier behind one sandbox boundary) does not exist. Non-compose
  projects (CLI, static site, Terraform, library) can't be run. `[P4]`
- **SSE + 4s polling overlap** (README "poll every 4s and stream over SSE").
  Two mechanisms carrying the same state. Should be: REST snapshot on load →
  SSE for deltas → polling only as a fallback when SSE drops. `[P4]`
- **One UI for everyone.** No simple/expert split; a first-time user sees the
  DAG, lineage graph, and dissent ledger at once. `[P5]`

### Low (already honestly marked `ponytail:` — tracked, not hidden)

- `schema.sql:182` API keys plaintext at rest (needs KMS before shipping). `[P5]`
- `schema.sql:6` single-file schema, no migrations dir. `[P5]`
- `runner.py:55` bare `docker compose up`, no gVisor/egress netns in the
  default path. `[P4]`
- `api.py:111` OpenAI cost billed at full input rate (cache discount not
  modeled) — distorts the very cost metric Phase 2 needs. `[P2]`
- `orchestrator.py:32,225` module-dict run context; per-dispatch role query. `[P5]`
- `web/index.html:7` CDN fonts, not self-hosted. `[P5]`

---

## Part D — The phases

Each phase is shippable on its own and leaves the system more honest than it
found it. Order is deliberate: **close the credibility gap first** (Phase 1),
then prove the economic claim (Phase 2), then make it learn (Phase 3), then
make it safe for others' code (Phase 4), then make it usable and deployable by
others (Phase 5).

---

### Phase 0 — Make the lie impossible to tell (1–2 days)

**Goal:** stop the system from overstating itself while the real engine is
built. Honesty is a feature; a benchmark built on echo stubs is fraud.

**Entails:**
- A `run.mode` surfaced in the UI and stored on the run: `simulated` (echo /
  trivial verifiers) vs `live` (real model + real verifier). Every chart,
  leaderboard, and the README "populated by real runs" claim is scoped to
  `live`.
- Benchmarks (Phase 2+) refuse to run in `simulated` mode.
- README "What's here" table gains an honest **"verifies behavior: no (M1)"**
  row until Phase 1 lands.

**Engineering practice:** truth-in-labeling as a code-enforced invariant, not a
footnote. A `simulated` run can never write to the `agent_scores` table used
for routing.

**Exit criteria:** no screen or doc presents simulated output as a verified
outcome. A reviewer can tell at a glance whether a number is real.

**Answers:** safer (against self-deception). Prereq for every claim after.

---

### Phase 1 — A real engine: dynamic DAG + behavioral verification (2–4 weeks)

This is the phase that moves the grade. Everything else is polish on top of a
real engine or a cardboard one.

**1a. Brief → DAG (kill the template).**
- Replace `_TEMPLATE_DAG` with a planner that derives nodes from the fingerprint
  and the detected project shape (package.json / pyproject / go.mod / Cargo.toml
  / Dockerfile / none). The storefront template becomes *one* template among
  several, selected by `match`, not the universal default.
- `depends_on` must express **real** dependencies (schema before API, API
  before UI) so `scheduler.levels` produces genuinely parallel levels — the
  parallelism the scheduler already supports but never sees.
- A node's `writes`/`reads` globs must come from the plan, not a fixed list, so
  leases actually protect concurrent writers.

**Engineering practice:** the planner is still deterministic given
(fingerprint, template, pitfalls) — replay/fork (§16.5) depends on this. No LLM
in the walk. Golden-file tests: fixture brief → expected DAG shape.

**1b. Behavioral verifiers (make "correct" mean something).**
- Add verifiers that *execute*: `build.succeeds`, `tests.pass`,
  `typecheck.clean`, `lint.clean`, `schema.migrates`. They run the proposal's
  produced artifacts inside the existing sandbox pool (`pool.py`), not against a
  JSON blob.
- Keep the trivial verifiers for cheap stage-1 gating, but a node that writes
  code must carry at least one behavioral acceptance check or the planner
  refuses to emit it.
- Verifier results feed the arbiter's stage 2 exactly as now — the plumbing is
  already correct (`arbiter.py:49`); only the verifiers change.

**Engineering practice:** verifiers are pure functions of (acceptance,
artifacts) with hard timeouts and resource caps; a hanging test is a fail, not a
hang. Every verifier ships with a self-check in `test_core.py`.

**Exit criteria:**
- Two different briefs produce two visibly different DAGs.
- At least one level in a real run runs ≥2 nodes concurrently.
- A deliberately broken proposal fails a behavioral verifier and the
  resurrect/settle loop recovers a working alternative — demonstrated, not
  asserted.

**Answers:** correct (verification), faster (parallelism). **Grade after: B.**

---

### Phase 2 — Optimize for verified outcomes, not activity (1–2 weeks)

Now that "verified" means something, optimize it. This is where suggestion.md's
central economic argument lands.

**Entails:**
- **The metric:** `cost_per_verified_result = Σ spend / count(verified
  successes)` per run and per agent×domain. Store it, chart it, and make it the
  headline number. Replace the "40% should be local" quota entirely — cheap
  that causes a repair → re-call → re-verify cycle is not cheap.
- **Complexity scorer:** a deterministic scorer per node (fan-in, writes
  breadth, irreversibility, acceptance strength, prior failure rate for this
  fingerprint) → a tier. Trivial nodes route to local/cheap models; complex or
  irreversible nodes route to the strong model. Routing is a function of
  complexity × historical cost-per-verified-result, not a fixed percentage.
- **Fix cost accounting first** (`api.py:111`): model the cache discount, or the
  metric it feeds is wrong. A Phase-2 metric on Phase-1 cost bugs is garbage.

**Engineering practice:** the router is a pure, logged decision (node →
tier → model) so a run explains *why* it spent what it spent. A/B the router
against "always strong model" and "always local" on the Phase-2 benchmark.

**Exit criteria:** a run report shows cost-per-verified-result, and the
complexity router demonstrably lowers it versus always-strong **without**
lowering the verified success rate. If it can't, the router is off by default.

**Answers:** cheaper — with proof it didn't trade away correctness.

---

### Phase 3 — Make it learn (confidence, dissent retention, real memory) (2–3 weeks)

The pitch for an orchestrator over a bare agent is that it gets *better* across
runs. Today it forgets everything useful and only remembers what to ban.

**3a. Confidence-aware scoring.**
- Replace raw rates with shrinkage estimates (e.g. Beta-Binomial posterior mean,
  or a Wilson lower bound) + a minimum-sample floor below which an agent scores
  at the prior, not at its lucky streak.
- Separate `new` / `experienced` / `specialist` cohorts so Lineage can't promote
  a 5/5 rookie over a 950/1000 veteran.

**3b. Dissent retention ladder** (suggestion.md):
`never-tested → archive`, `tested+failed → low`, `tested+succeeded → high`,
`repeatedly-vindicated → promote to knowledge`. A vindicated dissent that keeps
being right becomes a reusable decision, not just a settled row.

**3c. Memory as an evidence pipeline** (suggestion.md):
`Observation → Hypothesis → Verification → Confidence → Knowledge`, replacing
`Failure → MUST NOT`. A pitfall becomes a *low-confidence hypothesis* that
earns `MUST NOT` status only after repeated verified failure — and can be
*demoted* when a vindicated dissent proves it wrong. This also prevents a stale
pitfall from permanently poisoning every future DAG.

**Engineering practice:** confidence math gets property tests (more evidence
never decreases below the prior; a single failure can't zero a strong track
record). Knowledge promotion/demotion is auditable — every state transition is
an episodic event.

**Exit criteria:** across a batch of repeated runs on the same domain,
verified success rate rises and cost-per-verified-result falls run-over-run —
the learning curve is visible, not asserted.

**Answers:** correct + cheaper, compounding over time. This is the actual
answer to "why an orchestrator and not one agent." **Grade after: B+/A-.**

---

### Phase 4 — Safe for other people's code (2–3 weeks)

Required before anyone runs an untrusted brief or imports a real repo. Maps to
suggestion.md's execution-adapter and defense-in-depth arguments.

**4a. Execution Adapter abstraction.**
Replace "no Compose → don't run" with: *every execution method must declare a
sandboxable execution specification.* One boundary, several adapters:
`Compose`, `Dockerfile` (generate a minimal compose or run directly sandboxed),
`Native` (language-runner in a locked-down sandbox for CLI/static/library/
Terraform). The verifier sits behind the adapter, so Phase-1 behavioral checks
work for non-compose projects too.

**4b. Defense-in-depth secret redaction** (suggestion.md):
redact at `prompt → environment isolation → model output → DB → telemetry →
logs → artifacts → egress`, not egress alone. A secret must be scrubbed before
it can reach a log line.

**4c. Security tests are first-class CI** (suggestion.md): taint, egress
allowlist, redaction, and sandbox escape attempts run in CI on every commit —
not "verified manually against the running stack." Default-path gVisor/egress
netns (closes `runner.py:55`).

**4d. SSE as source of truth:** REST snapshot on load → SSE deltas → polling
*only* as a reconnect fallback (suggestion.md). Removes the dual-mechanism state
skew.

**Engineering practice:** security is tested as adversary, not as feature — a
red-team fixture tries to exfiltrate a planted secret through each channel and
CI fails if any path leaks.

**Exit criteria:** a planted secret cannot reach logs/telemetry/DB/egress (CI-
proven); a non-compose project builds, runs, and verifies; SSE drop degrades
gracefully with no duplicate state fetches.

**Answers:** safer — provably, in CI.

---

### Phase 5 — Usable and shippable by someone who isn't you (2–3 weeks)

Everything above makes the engine real; this makes it adoptable by User B.

**Entails:**
- **Simple vs Expert UI** (suggestion.md): Simple = brief in, progress, result,
  cost-per-verified-result out. Expert = DAG, lineage graph, dissent ledger,
  charts. Progressive disclosure, not two codebases.
- **Ship-readiness of the deferred `ponytail:` items that block production:**
  KMS for API keys (`schema.sql:182`), a real migrations dir (`schema.sql:6`),
  self-hosted fonts (`web/index.html:7`). These are explicitly tracked debt;
  this phase pays the ones that gate a real deployment.
- **Onboarding that reaches a verified result fast:** a one-command example
  brief that produces a genuinely verified artifact, so a new user sees the core
  value in minutes, not after wiring ten providers.

**Engineering practice:** the Simple UI is the default; the Expert UI is opt-in.
Migrations are forward-only and tested on a seeded DB in CI.

**Exit criteria:** a new User B clones, runs one command, and gets a verified
build with a real cost-per-verified-result number — without reading this file.

**Answers:** all four, made accessible.

---

## Part E — The benchmark (how we prove any of this)

suggestion.md asks for exactly one thing to justify the project's existence: a
before/after table on a meaningful benchmark. This is the acceptance test for
the whole roadmap, built in Phase 1 and populated through Phase 3.

A fixed suite of ~20 real briefs (API CRUD, auth flow, payment webhook, data
pipeline, CLI tool, static site — a spread, not all storefronts), each with
real acceptance checks. Run each with a **bare single agent** (control) and
with **Lineage** (treatment). Measure:

|                     | Bare agent | Lineage (target) |
|---------------------|-----------:|-----------------:|
| Verified builds     |        ?%  |            ≥ +15pp |
| Cost / verified build |      $?  |          ≤ −30%  |
| Wall-clock / build  |        ?m  |          ≤ −30%  |
| Human fixes needed  |         ?  |          ≤ −50%  |
| Repeated failures   |        ?%  |          ≤ −60%  |

The `?` cells are blank on purpose. **Until they hold real numbers from `live`
runs, the answer to "why should I use this orchestrator" is "we're still proving
it."** After they hold, the answer is the table.

---

## Part F — The judge, re-seated: as-is vs as-it-will-be

| Dimension | Today (as-is) | After Phase 3 | After Phase 5 |
|-----------|---------------|---------------|---------------|
| Builds from a brief | ❌ fixed template | ✅ dynamic DAG | ✅ + templates learned |
| Verifies correctness | ❌ structural only | ✅ build/test/lint | ✅ per-adapter |
| Optimizes cost | ❌ no metric | ✅ cost/verified-result | ✅ complexity-routed |
| Learns across runs | ❌ forgets / only bans | ✅ confidence + knowledge | ✅ compounding |
| Safe for others' code | ⚠️ egress-only, compose-only | ⚠️ unchanged | ✅ defense-in-depth, CI-proven |
| Usable by a newcomer | ⚠️ one dense UI | ⚠️ unchanged | ✅ simple/expert |
| **Overall grade** | **C+** | **B+** | **A−** |

### Closing judgment

As it stands, Lineage is an impressive answer to a question nobody asked:
*"what if agent orchestration had beautiful infrastructure?"* The chassis is
real and well-built. But a skeptic asking "why should I use this over one good
agent?" gets no answer today, because the engine doesn't yet do the one thing
that would justify the orchestration: **reliably turn a brief into verified,
working software, measurably better than a bare agent.**

Phase 1 is the whole ballgame. A dynamic DAG and verifiers that actually execute
code convert this from a demo into a tool. Phase 2–3 are what make it a tool
worth paying for — cheaper and smarter over time. Phase 4–5 are what make it a
tool other people can trust and use.

If only one phase ever ships, ship Phase 1. If the benchmark in Part E ever
fills in with the target numbers from `live` runs, then — and only then — this
project has earned its complexity, and the answer to "why should I use this"
stops being a promise and becomes a number.
