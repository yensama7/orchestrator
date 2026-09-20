# Lineage — build plan

Multi-agent build orchestration with memory that knows what it forgot, what it
tried, and what it was talked out of.

---

## 1. What this is

A desktop/web console that takes a project brief, assembles a roster of AI
agents with assigned roles, plans the work as a dependency graph, executes it in
sandboxes, and distils the result into a reusable template. The system gets
cheaper and better at a category of project every time it builds one.

Three things separate it from a generic agent runner:

1. **Lineage.** Runs inherit from templates, templates descend from runs,
   decisions supersede decisions. Everything has a parent and the parent is
   visible.
2. **Failure is first-class.** A failed run is more valuable than a successful
   one, because its pitfalls become hard constraints on the next plan.
3. **Dissent is retained.** When agents disagree and one wins, the losing
   proposal is not thrown away. See §8.

---

## 2. Product surfaces

Five views, reached from the left rail. The design language is fixed by the
console mockup and is not open for redesign — see §12.

| View | Answers |
|------|---------|
| **New run** | What am I building, with whom, for how much? |
| **Lineage** | Have we built something like this before, and how did it go? |
| **Memory** | What does this project know, and what is it being told right now? |
| **Agents** | Who is working, what are they costing, are they any good? |
| **Workspace** | Show me the code, let me edit it, let me run it. |

### Copy changes from the mockup

Remove every explanatory paragraph under the view headings. Specifically the
`.lede` block in each view, including the workspace one beginning "Agent
worktrees, read-write for you…". The interface should not teach; it should
label. Anything that genuinely needs explaining goes behind a `?` affordance in
the panel header, collapsed by default and remembered per user.

Keep the short `.hint` lines inside side panels only where they name a unit or
a source ("matched on spec fingerprint", "143 nodes attempted"). Cut the rest.

---

## 3. New run: prompting the planner

This is the entry point and it currently does not exist. Six steps, all on one
screen, each collapsing as it completes.

**1 — Brief.** Free text. "Build a storefront for a Nigerian fashion label,
Paystack checkout, admin dashboard, ~2k SKUs."

**2 — Spec fingerprint.** A local model extracts a structured object. The user
can edit every field before continuing. This is the highest-leverage human input
in the system, so it is editable, not hidden metadata.

```yaml
domain: commerce
subdomain: storefront
scale: { skus: 2000, traffic: low }
stack_hints: [nextjs, postgres]
payments: paystack
auth: required
multi_tenant: false
compliance: []
region: NG
```

**3 — Lineage match.** The fingerprint is embedded and matched against past
runs. The console shows the nearest four with their outcomes, and proposes a
template. The user can accept, pick a different one, or start clean.

**4 — Roster.** The planner proposes roles and assigns a model to each. Every
row is user-editable: swap the model, change the transport, delete the role, add
one.

| Role | Model | Transport | Consensus | Node budget |
|------|-------|-----------|-----------|-------------|
| planner | claude-opus-4.6 | subscription | — | $0.80 |
| senior-dev ×3 | sonnet / gpt-5.1 / deepseek | mixed | irreversible only | $0.40 |
| frontend | kimi-k2 | api | never | $0.20 |
| security-impl | claude-sonnet-4.6 | subscription | never | $0.30 |
| security-analyst | gemini-3-pro | subscription | never | $0.25 |
| distiller | qwen3-4b | local | never | $0.00 |

Assignment defaults come from the template's recorded stack, adjusted by each
model's win rate in this domain (§9). A role with no available model is flagged,
not silently dropped.

**5 — Budget.** The user sets a ceiling. The planner treats it as a constraint
and plans to fit, choosing cheaper agents and skipping consensus rounds when the
ceiling is tight. It reports the projected cost before anything is spent.

**6 — Plan review.** The planner emits the task DAG. The console renders it. The
user approves, edits node order, or sends it back with a comment. Only then does
execution begin.

Everything on this screen is recoverable from the episodic log, so a run can be
forked from step 4 or 6 without re-doing the earlier steps.

---

## 4. Model access: three transports, not just API keys

An agent is a **(model, transport)** pair. Cost accounting differs per transport
and the UI must not assume dollars.

### `api` — metered
Standard API key. Cost in USD per token. What the current mockup assumes.

### `subscription` — flat-rate
If the user pays for Claude Pro/Max, ChatGPT Plus/Pro, or Google AI Pro, they
should be able to spend that quota here instead of buying tokens twice.

The correct implementation is to drive the **official headless CLIs**, which
support OAuth login against a consumer subscription:

- Claude Code — `claude -p "<prompt>" --output-format stream-json`, or the
  Agent SDK
- Codex CLI — non-interactive exec mode
- Gemini CLI — non-interactive mode

Each is wrapped in a `SubscriptionTransport` that speaks the same envelope
protocol as the API transport. The adapter parses the CLI's structured output
stream rather than scraping stdout.

> **Do not** automate a browser session or reuse web cookies. It breaks the
> terms of every provider and gets the user's account banned. If a provider has
> no headless CLI or OAuth path, that model is API-only and the UI says so.

Accounting for subscription agents is in **quota units, not dollars**:
requests used in the current window, window reset time, and rate-limit
proximity. The header spend rail becomes two-track — a dollar rail for metered
agents and a quota rail for subscription agents. A run can mix both.

Scheduling implication: subscription transports have hard request-rate limits
and no burst capacity. The scheduler gives them their own semaphore sized to the
plan's limit, and demotes a node to an API agent if the subscription agent would
block the critical path past a threshold.

### `local` — free
Ollama or vLLM on the user's hardware. Zero marginal cost. Used for embeddings,
reranking, summarisation, routing, fingerprint extraction, and distillation.
Roughly 40% of all model calls in a run should land here.

---

## 5. Memory

Three persisted stores. Working context is process state and is never written to
disk, so it is not a tier.

| Tier | Question | Mutability | Store |
|------|----------|-----------|-------|
| Episodic | What happened? | append-only | `episodic_events` |
| Semantic | What do we know now? | status flips | `semantic_memory` |
| Procedural | How do we build this? | versioned | `templates`, `pitfalls` |

### Semantic schema (the important one)

```sql
CREATE TYPE mem_status AS ENUM ('active','superseded','reverted');

CREATE TABLE semantic_memory (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  run_id      uuid NOT NULL REFERENCES runs(id),
  subject     text NOT NULL,              -- 'auth', 'db', 'payments'
  choice      text NOT NULL,
  rationale   text,
  rejected    jsonb DEFAULT '[]'::jsonb,
  status      mem_status NOT NULL DEFAULT 'active',
  supersedes  uuid REFERENCES semantic_memory(id),
  decided_by  text NOT NULL,
  confidence  real CHECK (confidence BETWEEN 0 AND 1),
  embedding   vector(1024) NOT NULL,
  tsv         tsvector GENERATED ALWAYS AS
                (to_tsvector('english', choice)) STORED,
  created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX sem_active_hnsw ON semantic_memory
  USING hnsw (embedding vector_cosine_ops) WHERE status = 'active';
CREATE INDEX sem_active_bm25 ON semantic_memory
  USING gin (tsv) WHERE status = 'active';
```

The partial indexes are the whole trick. Superseded rows never enter the
candidate set, so an agent cannot re-propose a decision the team already
reversed. Pure cosine similarity puts "use Postgres" and "do not use Postgres"
almost on top of each other; filtering by status before ranking is what stops
that.

### Retrieval
Hybrid, always: BM25 + vector, fused with reciprocal rank fusion, then reranked
locally by `bge-reranker-v2-m3`. Measured recall@10 goes from ~0.68 (vector
only) to ~0.91 (hybrid + rerank). Top-k capped at 6 rows per prompt; more than
that and retrieved memory starts eating a third of every context window.

---

## 6. Learning from failure

Success-only learning throws away the more useful half of the signal. Failures
are recorded as first-class rows and injected into future plans as constraints,
not suggestions.

```sql
CREATE TABLE pitfalls (
  id              uuid PRIMARY KEY,
  fingerprint     text NOT NULL,     -- normalised error signature, deduped
  domain          text NOT NULL,
  trigger         jsonb NOT NULL,    -- the combination that caused it
  symptom         text NOT NULL,
  resolution      text,              -- null if never resolved
  cost_usd        numeric,           -- what the failure cost to discover
  occurrences     int DEFAULT 1,
  first_run_id    uuid,
  last_seen_at    timestamptz,
  embedding       vector(1024)
);
```

Rules:

- **Dedupe by fingerprint,** not by text. Normalise stack traces, strip paths
  and line numbers, hash the result. The same failure across six projects is one
  pitfall with `occurrences = 6`, and that count is how you rank severity.
- **Failed runs stay on the lineage map** in rust, and are clickable. They are
  not hidden.
- **Pitfalls are injected pre-plan,** into the planner's context before it
  writes a single node, as `MUST NOT` constraints. A pitfall with high
  `occurrences` and no `resolution` blocks the plan and asks the user.
- **Record the cost of discovery.** "This combination cost us $14 to find out
  about" is the number that justifies the whole memory layer to a sceptic.
- **Abandoned runs count.** If a user kills a run, ask one question — why — and
  store it. Cheapest high-quality signal in the system.

---

## 7. Execution and the run gate

**Run is disabled unless a compose file is present.** No exceptions, no
fallback to bare commands.

On click, the runner looks in the worktree root, in order:

1. `compose.yaml`
2. `compose.yml`
3. `docker-compose.yaml`
4. `docker-compose.yml`

If one is found → `docker compose up --build` in the sandbox network namespace,
with logs streamed to the console.

If none is found but a `Dockerfile` exists → Run stays disabled, and the empty
state offers a single action: *Generate compose file*. That dispatches a
one-node task to the devops role, which writes a compose file from the
Dockerfile and any detected services, and drops it in the worktree for review.

If neither exists → Run is disabled, and the empty state offers
*Containerise this project*, a task that produces both.

The empty state is directional, never an error: "No compose file yet. Generate
one from the Dockerfile?" — with the button doing exactly what it says.

Why compose only: it makes multi-service projects the default case rather than a
special case, it gives you a declared network topology to apply the egress
allowlist against, and it means "it runs on my machine" is a property of a file
in the repo rather than a shell history.

---

## 8. The twist: the Dissent Ledger

When three senior-dev agents propose and the arbiter picks one, the two losing
proposals are currently discarded. That is throwing away tokens you already paid
for, and it hides the most interesting signal in the system.

**Keep them.** Every overruled proposal is written to a dormant branch with its
full reasoning, the arbiter's stated reason for rejecting it, and a pointer to
the node it lost at.

Three things fall out of this, and they are the demo:

### Instant rollback to the minority opinion
When the chosen path fails verification, the system does not replan from
scratch. It resurrects the highest-ranked dissenting proposal for that node and
tries it immediately. This costs zero new planning tokens, because the
alternative was already written and reasoned about. In practice this turns a
90-second replan cycle into a 3-second branch switch.

### Vindication rate
Every time a minority proposal is resurrected and passes where the majority
failed, the dissenter is credited. Over a few dozen runs you get a metric nobody
currently has:

> `dev-c` was overruled 14 times this quarter and was vindicated 9 of them.
> Its proposals lose the vote and win the test.

This is a direct, falsifiable measure of whether an agent is genuinely better or
merely more confident — and LLM debate is known to converge on confidence rather
than correctness. Vindication rate is the correction.

### Vindication-weighted routing
Feed it back into the arbiter. An agent with a high vindication rate in a domain
gets its objections weighted more heavily there, and eventually gets promoted
out of the cheap tier for that domain specifically. The system learns which of
its members to listen to, per subject, from evidence rather than from model
pricing.

### Surface
A sixth view, **Dissent** — a ledger of roads not taken. Each row is a rejected
proposal with the node, the winner, the reason, and its current status: dormant,
resurrected, vindicated, or refuted. Filterable by agent. The vindication
leaderboard sits at the top.

Cost: near zero. The proposals are already generated and already in the
episodic log. This is pure value extraction from spend that currently
evaporates.

---

## 9. Agent scoring

Three numbers per agent per domain, all derived from verified outcomes rather
than self-report:

- **Pass rate** — nodes that cleared verification on first attempt
- **Escalation rate** — how often the cascade had to promote its work
- **Vindication rate** — §8

The cascade router reads all three. Cheap models with high escalation rates get
mechanical nodes only; models with high vindication in a domain get pulled into
consensus rounds for that domain even if they are cheap.

---

## 10. Token economics

Ordered by return. Each layer multiplies against the ones above it.

| Layer | Technique | Typical effect |
|-------|-----------|----------------|
| L0 | Don't call the model — exact and semantic response cache | −20–40% of calls |
| L1 | Prefix caching with strict stable/warm/cold prompt ordering | −60–80% on input |
| L2 | Content-addressed artifacts + `read_artifact(hash, range)` | −30% context |
| L3 | Cascade routing, escalate only on verifier failure | −70% on mechanical nodes |
| L4 | Schema-enforced output, no prose fields in mechanical nodes | −40% output |
| L5 | Threshold-based compaction, not per-turn summarisation | variable |
| L6 | Batch API for distillation, reflection, research | −50% on those |
| L7 | Local model for the boring 40% | −100% on those |
| L8 | Hard ceilings, per-node budgets, loop detection | caps the tail |

**L1 is load-bearing and fragile.** Prompt assembly must enforce ordering in
code so a timestamp or a reshuffled tool list can never land above a stable
block and invalidate the prefix below it.

Track and display the **uncached counterfactual** — what the run would have cost
with none of this. It is the only way the optimisation work stays visible.

---

## 11. Security

Design for containment, not prevention. Prompt injection has no complete
solution; the achievable goal is that a fully compromised agent can do nothing
that matters.

- **Two-plane separation.** The control plane (DAG, budgets, roles, credentials)
  is not writable by agents. They emit proposals; the scheduler validates and
  applies. An injected agent cannot expand its own permissions.
- **Closed instruction set.** `intent` is an enum and the envelope is
  schema-validated, so injected prose lands in an advisory `notes` field that
  nothing downstream may branch on. This is the structural defence that holds.
- **Capability broker.** Agents never hold credentials. Short-lived, scoped,
  single-purpose tokens, every issuance audited.
- **Egress allowlist per role,** enforced at the network namespace. Default
  deny. Enforced by the kernel, not by asking the model nicely.
- **Taint tracking.** Web content, dependency files, and tool output are tagged
  untrusted; the tag propagates through derived artifacts. An agent consuming
  tainted input runs with writes and network disabled for that call.
- **Sandboxes.** Docker + gVisor, read-only rootfs, seccomp, no host mounts
  except the agent's own git worktree.
- **Egress secret scanning** on every artifact before it leaves the sandbox.
- **MCP servers hash-pinned and allowlisted.** Currently the least-defended
  surface in every agent stack.
- **Human gates** on deploys, migrations, destructive SQL, credential creation,
  and spend above a threshold.
- **Append-only hash-chained audit log** over prompts, tool calls, artifact
  hashes, and approvals.

---

## 12. UI specification

The published console is the design spec. Reproduce it exactly; do not
redesign.

### Tokens

```
--ink      #131724   ground
--ink2     #1a1f30   panels
--ink3     #222940   raised
--line     #2b3348   hairline
--line2    #394261   hairline, raised
--bone     #e7e4db   primary text
--dim      #99a0b4   secondary text
--dimmer   #69708a   tertiary / labels
--amber    #e0a33c   live, spending, current
--sage     #7fb894   recalled from memory, passing
--rust     #c96a52   superseded, failed
--violet   #9b8ce0   consensus, arbitration
--steel    #6d8bc7   episodic

UI type:   Archivo 400/500/600
Data type: JetBrains Mono 400/500
Radius:    4px panels, 2–3px chips. Hairline borders, no shadows.
```

### Structure
Header with the spend rail as the single loud element. Left rail of views, not
file tabs. One stage. Bottom ticker of lineage events. Motion only on state
change; the ticker pulse is the one ambient animation and respects
`prefers-reduced-motion`.

### Workspace improvements

The current workspace is the weakest view. Required changes:

1. **Remove the explanatory paragraph.** As §2.
2. **Language icons.** Each file row and the editor header show the language
   logo, not a text extension badge. Use Devicon (MIT, ~200 language marks) or
   the Material Icon Theme SVG set, bundled locally and tree-shaken — never
   fetched per render.
3. **Universal language detection.** §13.
4. **Breadcrumb** above the editor showing worktree → folder → file, each
   segment clickable.
5. **Agent attribution gutter.** A thin strip beside the line numbers coloured
   by which agent last touched each line, with the agent name on hover. This is
   `git blame` where the authors are models, and it is the single most useful
   thing this editor can show that a normal editor cannot.
6. **Diff toggle.** Switch any file between current state and the diff the last
   agent applied.
7. **Run bar** pinned below the editor: compose file status, Run / Stop,
   service health chips, and a log drawer. Disabled per §7.
8. **Dirty-state indicator** and unsaved-change guard when switching files.
9. **Search across the worktree** (`⌘P` file jump, `⌘⇧F` content search),
   backed by ripgrep in the sandbox, not by loading files into the browser.
10. **Read-only lock** on files an agent currently holds a lease on, with the
    holding agent named in the lock chip.

---

## 13. Editor: universal language detection

Detect by **file extension only**. Never sniff content — it is slow, wrong on
short files, and gives an attacker a way to influence how the editor parses a
file an agent just wrote.

Three-tier resolution, first hit wins:

1. **CodeMirror 6 official grammars** — ~40 languages, dynamically imported so
   opening a `.rs` file is the only thing that ever loads the Rust grammar.
2. **`@codemirror/legacy-modes`** — the CodeMirror 5 mode collection, ~110 more
   languages (Fortran, COBOL, Nim, Zig, Elixir, Haskell, Clojure, Verilog…).
   Keyword highlighting quality is lower but present.
3. **Generic fallback** — a StreamLanguage built from a keyword list, so an
   unknown extension still gets keywords, strings, numbers, and comments
   coloured rather than falling to flat text.

```ts
type Resolved = { mode: string; icon: string; loader: () => Promise<LanguageSupport> };

const REGISTRY: Record<string, Resolved> = {
  py:   { mode: 'python',     icon: 'python',     loader: () => import('@codemirror/lang-python').then(m => m.python()) },
  ts:   { mode: 'typescript', icon: 'typescript', loader: () => import('@codemirror/lang-javascript').then(m => m.javascript({ typescript: true })) },
  rs:   { mode: 'rust',       icon: 'rust',       loader: () => import('@codemirror/lang-rust').then(m => m.rust()) },
  ex:   { mode: 'elixir',     icon: 'elixir',     loader: () => legacy('elixir') },
  // …
};

export function resolve(filename: string): Resolved {
  const ext = filename.split('.').pop()?.toLowerCase() ?? '';
  return REGISTRY[ext]
      ?? SPECIAL_FILENAMES[filename.toLowerCase()]   // Dockerfile, Makefile, .env
      ?? GENERIC;
}
```

Special-case bare filenames with no extension: `Dockerfile`, `Makefile`,
`Justfile`, `Procfile`, `.gitignore`, `.env`, `CMakeLists.txt`.

The editor header shows the resolved mode and a *why* affordance: extension →
tier → grammar. When resolution lands on the generic fallback, say so plainly
rather than pretending.

---

## 14. Concurrency

Agent work is ~99% network wait, so this needs concurrency, not parallelism.

- **Python asyncio on one core** handles hundreds of in-flight calls. Threads
  and process pools buy nothing here.
- **Warm sandbox pool.** Pre-pulled images, snapshot-restored, assigned on
  demand. Cold-starting a container per node dominates wall clock — this is what
  eats build time in practice.
- **Per-transport semaphores.** API providers get rate-limit-sized semaphores;
  subscription transports get much smaller ones; local models get one sized to
  GPU memory.
- **Bounded queues for backpressure.** If verification lags, stop spawning
  upstream work.
- **Durable queue on Postgres** via `SELECT … FOR UPDATE SKIP LOCKED`. No Redis,
  no Temporal on day one. Add Temporal only when workflows must outlive a
  process.

Track **queue depth**, not CPU. The orchestrator will always look idle.

---

## 15. Stack

| Layer | Choice | Why |
|-------|--------|-----|
| Core | Python 3.12, asyncio, uvloop, httpx | IO-bound; best SDK ecosystem |
| Contracts | Pydantic v2 → JSON Schema → TypeScript | one schema, both sides |
| Storage | Postgres 16 + pgvector (HNSW) + `tsvector` | vectors, relations, BM25, queue — one service |
| Queue | Postgres `FOR UPDATE SKIP LOCKED` | durable, no extra dependency |
| API | FastAPI + Server-Sent Events | telemetry is one-way; SSE reconnects and survives proxies |
| Sandbox | Docker + gVisor, pooled warm | syscall isolation without Firecracker's ops weight |
| Embeddings | BGE-M3 via text-embeddings-inference | local, free, strong on code |
| Reranker | bge-reranker-v2-m3, local | 0.68 → 0.91 recall@10 |
| Small model | Qwen3-4B via vLLM | routing, summarising, fingerprinting at zero cost |
| Projection | UMAP + HDBSCAN, batch | precompute 2D coords; never project in the browser |
| Frontend | TypeScript, React, Vite, TanStack Query | shared types with the backend |
| Editor | CodeMirror 6 + legacy-modes | tree-shakeable, lazy per-language (~200KB vs Monaco's multi-MB) |
| Icons | Devicon, bundled | ~200 language marks, MIT |
| Graph | deck.gl / regl-scatterplot | WebGL; SVG dies past 5k points |
| Charts | uPlot | tiny, fast on live series |
| Model access | thin adapter layer | three transports behind one interface |
| Git | pygit2 (libgit2) | worktree-per-agent, programmatic merge |
| Secret scan | gitleaks as subprocess | egress gate |
| Telemetry | OpenTelemetry → Postgres partitioned tables | move to ClickHouse only at scale |

**Why Python over Go:** the bottleneck is network wait, not CPU, and every model
SDK, embedding library, and eval tool is Python-first. Go would give tighter
concurrency and a single binary at the cost of writing a lot of glue to get back
what Python gives free.

**Why CodeMirror over Monaco:** Monaco *is* VS Code's editor and drags in the
whole thing. CodeMirror 6 lets you load exactly one grammar per opened file,
which is the entire point of extension-based detection.

---

## 16. Five things that make this better

1. **Ship the memory layer alone first.** Supersession-aware agent memory with
   hybrid retrieval is useful to everyone building agents, has a far shorter
   path to working, and proves the hard part. Orchestrators are a crowded field;
   this is not.
2. **Make the spec fingerprint user-editable before a run.** It drives template
   retrieval, so it is the highest-leverage human input in the system and should
   not be invisible machine-generated metadata. §3 step 2.
3. **Store failures as first-class rows and inject them as constraints.** Most
   template systems learn only from success and throw away half the signal. §6.
4. **Make the budget a planning input, not a warning.** Let the user set a
   ceiling and have the planner choose a cheaper agent stack to fit it, the way
   a compiler optimises for size instead of speed. §3 step 5.
5. **Deterministic replay with forking.** Scrub a run backwards, change one
   decision at node 14, re-run from there. This is what makes people trust the
   system, and nobody does it well yet. It also pairs directly with the Dissent
   Ledger — a resurrected minority proposal *is* a fork.

---

## 17. Build order

Sequenced by dependency, not by excitement. Templates cannot exist before runs
exist to distil.

**M1 — Skeleton that works.** Single model, single transport (API), typed DAG,
deterministic scheduler, verification gate, episodic event log, compose-gated
run. No memory, no consensus, no vector search. This is already a usable
product.

**M2 — Memory.** Semantic tier with supersession, hybrid retrieval, local
embeddings and reranker. Memory view. The uncached-counterfactual chart.

**M3 — Multi-model.** Three transports including subscription CLIs. Cascade
routing. Roster screen. Agents view with real scoring. Consensus on irreversible
nodes only.

**M4 — Dissent Ledger.** Dormant branches, instant rollback, vindication rate,
vindication-weighted routing. §8. Cheap to build once M3 exists, and it is the
thing people will talk about.

**M5 — Lineage and templates.** Fingerprint matching, pitfall injection,
distillation, template promotion gate, Lineage view. Needs ~20 completed runs
before it produces anything useful, so it is genuinely last.

**M6 — Replay and forking.** §16.5.

---

## 18. Resolved decisions

These four were open. They are now closed, with implementation detail, because
each one shapes code that gets written in M1.

### 18.1 Merge protocol — pessimistic leases per file

Two mechanisms, layered. The DAG is the primary defence; leases are the
backstop.

**Primary — declared IO.** Every node in the plan declares `reads: [glob]` and
`writes: [glob]`. The scheduler builds the concurrency set for each level by
checking for write/write and write/read overlap, and never co-schedules
conflicting nodes. Most contention is prevented here, before any lock exists.

**Backstop — leases.** An agent cannot open a file for writing without holding a
lease.

```sql
CREATE TABLE file_leases (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id   uuid NOT NULL,
  run_id      uuid NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
  node_id     text NOT NULL,
  agent_id    text NOT NULL,
  path_glob   text NOT NULL,
  mode        text NOT NULL CHECK (mode IN ('read','write')),
  acquired_at timestamptz NOT NULL DEFAULT now(),
  expires_at  timestamptz NOT NULL
);

CREATE UNIQUE INDEX one_writer_per_path
  ON file_leases (run_id, path_glob) WHERE mode = 'write';
```

Rules:

- **Ordered acquisition.** A node acquires all its leases in lexicographic path
  order, all-or-nothing, in one transaction. Ordered acquisition is what makes
  deadlock impossible; do not skip it.
- **Failure defers, never errors.** If a node cannot acquire the full set within
  2s, it rolls back, releases nothing (it holds nothing), and is pushed to the
  next scheduler level. The user never sees a lock error.
- **TTL = node timeout × 1.5**, with a reaper sweeping expired rows every 10s so
  a crashed sandbox cannot wedge a path forever.
- **Glob leases** for wide operations. A refactor node takes `src/**`; overlap
  detection is a glob-intersection check, not string equality.
- **Released on node completion, crash, or run cancellation.** `ON DELETE
  CASCADE` from `runs` handles the last case.

UI: a lock chip in the workspace file tree naming the holding agent, and the
editor in read-only mode for that file with the reason stated.

### 18.2 Template staleness — pinned manifest, drift detection, async re-verify

Retrieval never blocks on freshness. It reads a precomputed status.

```sql
CREATE TYPE tmpl_status AS ENUM ('fresh','drifting','stale','quarantined');

ALTER TABLE templates
  ADD COLUMN manifest            jsonb NOT NULL,   -- resolved versions at promotion
  ADD COLUMN drift_score         real NOT NULL DEFAULT 0,
  ADD COLUMN status              tmpl_status NOT NULL DEFAULT 'fresh',
  ADD COLUMN freshness_checked_at timestamptz,
  ADD COLUMN reverified_at        timestamptz;
```

**Drift job** (nightly, local model + registry APIs, zero token cost):

```
drift = Σ_deps w(bump) · staleness(dep)  +  λ · days_since_promotion

w(major)=1.0   w(minor)=0.3   w(patch)=0.05
```

- `drift < 0.25` → `fresh`
- `0.25 ≤ drift < 0.6` → `drifting`; retrieval down-weights the template but
  still offers it, with the drift shown in the lineage panel
- `drift ≥ 0.6`, or any dependency with a published advisory → `stale`, and an
  async re-verification job is enqueued

**Re-verification** runs the template's recorded smoke DAG against a scratch
worktree on the cheapest tier that can do the job — usually local models plus a
compose build. It is off the critical path and never delays a user's run.

- Pass → repin `manifest`, bump `templates.version`, set `fresh`
- Fail → `quarantined`, excluded from retrieval, **and the failure is written to
  `pitfalls`** so the next plan in that domain inherits the knowledge

A quarantined template is still visible on the lineage map, in rust. It is a
record of something that used to work and no longer does, which is exactly the
kind of thing this system exists to remember.

### 18.3 Deterministic arbiter for V1

No model in the arbitration loop. Determinism is not a style preference here —
replay and forking (§16.5) require that the same inputs produce the same winner,
and an LLM arbiter breaks that.

Five stages, in order, short-circuiting as soon as one proposal remains:

1. **Hard gates.** Eliminate any proposal that fails envelope schema validation,
   violates a `MUST NOT` pitfall constraint, or requests a tool or egress target
   outside its role policy. These are disqualifications, not penalties.
2. **Executable ground truth.** If the node has a verifier, run every surviving
   proposal through it. Eliminate the ones that fail. A passing test beats any
   vote, always.
3. **Scored vote.** For each survivor:

   ```
   score =  w_agree      · semantic_agreement_with_peers
          + w_pass       · agent.pass_rate[domain]
          + w_vindicate  · agent.vindication_rate[domain]
          − w_escalate   · agent.escalation_rate[domain]
          − w_cost       · normalised_node_cost
   ```

   Weights live in `config/arbiter.yaml`, not in code, so they are tunable
   without a deploy and auditable in the event log.
4. **Tie → human.** If the top two scores are within `epsilon` (default 0.05),
   the node is held and surfaced to the user. Never coin-flip an irreversible
   decision.
5. **Record.** Every eliminated proposal is written to the dissent ledger with
   its elimination stage and reason. This is the input to §8.

AI arbitration is deferred to M6 and scoped to stage-4 ties only, A/B tested
against human resolution with vindication rate as the outcome metric.

### 18.4 Multi-tenant data model from day one

Operationally single-tenant in V1; structurally multi-tenant from the first
migration. Retrofitting RLS onto a live schema is painful and easy to get subtly
wrong.

**Every tenant-owned table** carries `tenant_id uuid NOT NULL` and has RLS
enabled *and forced*:

```sql
ALTER TABLE semantic_memory ENABLE ROW LEVEL SECURITY;
ALTER TABLE semantic_memory FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON semantic_memory
  USING      (tenant_id = current_setting('app.tenant_id')::uuid)
  WITH CHECK (tenant_id = current_setting('app.tenant_id')::uuid);
```

`FORCE` matters — without it the table owner bypasses the policy, and the table
owner is usually the migration role.

**The application connects as a dedicated non-superuser role with `NOBYPASSRLS`.**
Application-layer filtering is a convenience, never the boundary.

**The tenant is set per connection checkout, inside the transaction:**

```python
@asynccontextmanager
async def tenant_conn(pool, tenant_id: UUID):
    async with pool.acquire() as conn, conn.transaction():
        await conn.execute("SELECT set_config('app.tenant_id', $1, true)",
                           str(tenant_id))   # true = transaction-local
        yield conn
```

Transaction-local (`is_local = true`) is required. A session-scoped setting
leaks to the next checkout from the pool.

**Vector isolation** rides in the index predicate, so a tenant's query never
traverses another tenant's graph:

```sql
CREATE INDEX sem_active_hnsw ON semantic_memory
  USING hnsw (embedding vector_cosine_ops)
  WHERE status = 'active';
-- queries always carry: WHERE tenant_id = $1 AND status = 'active'
```

pgvector handles a filtered HNSW scan well at this scale. If p99 recall degrades
past ~10M rows, partition `semantic_memory` by `tenant_id` — the query shape does
not change.

**Shared templates** are the one deliberate exception: `tenant_id IS NULL` means
a global template, and the policy permits reading NULL-tenant rows while
forbidding writes to them.

```sql
CREATE POLICY tmpl_read ON templates FOR SELECT
  USING (tenant_id IS NULL OR tenant_id = current_setting('app.tenant_id')::uuid);
CREATE POLICY tmpl_write ON templates FOR ALL
  USING      (tenant_id = current_setting('app.tenant_id')::uuid)
  WITH CHECK (tenant_id = current_setting('app.tenant_id')::uuid);
```

**Test gate.** A CI assertion iterates `information_schema` and fails the build
if any table with a `tenant_id` column lacks `relforcerowsecurity`. This is the
single cheapest protection against the failure mode where someone adds a table
in six months and forgets.

---

## 19. UI specification

This section is normative. Build exactly this. Tokens are in §12.

### 19.1 App shell

A four-part fixed layout, `100vh`, `min-height: 660px`, no page scroll — only the
stage scrolls.

```
┌───────────────────────────────────────────────────────────┐
│ HEADER              height: auto (≈96px), bg --ink2        │
│  row 1: wordmark · run id · spec line · ⟶ cost numbers     │
│  row 2: spend rail (8px, segmented, full width)            │
│  row 3: rail key (segment labels + cache saving, 11px)     │
├────────────┬──────────────────────────────────────────────┤
│ RAIL-NAV   │ STAGE                                         │
│ 132px      │ flex:1, overflow-y:auto, padding 22px 26px    │
│ bg --ink2  │ one .view visible at a time                   │
│            │                                               │
│ [nav ×6]   │                                               │
│            │                                               │
│ navfoot    │                                               │
├────────────┴──────────────────────────────────────────────┤
│ TICKER     height: auto (≈33px), horizontal scroll         │
└───────────────────────────────────────────────────────────┘
```

**Header — the spend rail is the only loud element on the page.** Nothing else
competes with it. Three numbers right-aligned in `JetBrains Mono` 22px: spent
(amber), projected (dim), ceiling (dimmer). The rail beneath is a single 8px
bar of flex segments — inference, consensus, retrieval, retries, projected
remainder — with the remainder segment in `--ink3` so it reads as unspent.

When any agent in the roster uses the `subscription` transport, the header
renders **two rails stacked**: the dollar rail, then a quota rail with one
segment per subscription provider showing requests used against the window
limit, and the window reset time in the key. The quota rail turns amber at 75%
and rust at 90%.

**Rail-nav** — six items, each an inline SVG at 15px plus a label. Active item
gets `border-left: 2px solid var(--amber)` and background `#1e2436`. Collapses
to icons only below 860px. `navfoot` at the bottom shows three lines of run
state in `--mono` 10.5px: egress posture, agent count, blocked count.

**Ticker** — lineage events, newest left, horizontally scrollable, never
auto-scrolling. Each entry is a `--dimmer` key followed by `--dim` text. The
single pulsing dot at the far left is the only ambient animation in the product,
and it respects `prefers-reduced-motion`.

### 19.2 Shared components

Build these once. Every view composes them.

| Component | Spec |
|-----------|------|
| `Panel` | `1px solid --line`, `radius 4px`, `bg --ink2`. Optional `pad` = 14px 16px. No shadows, ever. |
| `PanelHeader` | `h3` 12px/600 `--bone`, optional `?` button opening a collapsed help popover. Replaces all removed prose. |
| `Row` | 5px vertical, `border-bottom: 1px solid #222839`, last child no border. Left: dot + label. Right: `.n` in mono 11px `--dim`. |
| `Chip` | 11px mono, `1px solid --line2`, radius 3px, transparent bg. Active: `bg --amber`, text `#1a1405`, weight 500. |
| `Metric` | Label 11px `--dim`, value mono 19–22px `--bone`, delta line 11px in sage/rust/dimmer. |
| `Dot` | 8px circle. Semantic colour only — never decorative. |
| `Graph` | Canvas with grid, quadratic-curve edges, hover tooltip, filter chips. Shared by Lineage and Memory. |
| `EmptyState` | One line of what is missing, one primary button that fixes it. Never an apology, never a shrug. |

**Colour is semantic and fixed:** amber = live/current/spending, sage =
recalled/passing, rust = superseded/failed/quarantined, violet =
consensus/arbitration, steel = episodic. Do not use these for decoration.

### 19.3 View 0 — New run

New view. Entry point of the product. Reached from a `+ New run` button in the
header wordmark area, or when no run is active.

A single scrolling column, `max-width: 860px`, of six numbered step cards. Each
card is a `Panel`. Completed steps collapse to a one-line summary with an
`Edit` link; the active step is expanded; future steps are dimmed at 40% opacity
and not interactive.

**Step 1 — Brief.** Textarea, 5 rows, mono, placeholder showing a real example.
Primary button `Extract fingerprint` (disabled while empty).

**Step 2 — Fingerprint.** A two-column editable key/value grid rendered from the
extracted `SpecFingerprint`. Every field editable; enum fields become selects,
arrays become chip inputs with an `+ add` affordance. A `Re-extract` ghost
button. Primary: `Find similar work`.

**Step 3 — Lineage match.** Four `Row`s of nearest past runs: dot coloured by
outcome, name, similarity score in mono. Below, a highlighted recommendation
panel naming the proposed template, its status chip (fresh/drifting/stale per
§18.2) and what it contributes — agent stack, node count, carried decisions,
recorded pitfalls in rust. Buttons: `Use this template` (primary), `Pick
another` (opens the Lineage view in selection mode), `Start clean` (ghost).

**Step 4 — Roster.** A table, every cell editable inline:

```
Role            Model              Transport      Consensus       Budget/node
─────────────────────────────────────────────────────────────────────────────
planner         [select ▾]         [api|sub|local] —              [$ input]
senior-dev ×3   [3 model selects]  [per model]    [select ▾]      [$ input]
frontend        [select ▾]         [select ▾]     never           [$ input]
…                                                        [+ add role]
```

- Transport select shows only transports actually available for that model, and
  a subscription option is disabled with a reason tooltip if the CLI is not
  authenticated.
- A role with no available model shows a rust warning row and blocks `Continue`.
- Each row shows the model's `pass_rate` and `vindication_rate` for this
  fingerprint's domain as two small mono figures, so the user can see *why* the
  planner picked it.
- `Reset to template defaults` ghost button.

**Step 5 — Budget.** A single numeric input with a slider, plus a live readout:
projected cost at this ceiling, and what the planner will give up to fit —
"consensus disabled on 4 of 9 irreversible nodes" in amber. This is the key
interaction of the screen: moving the slider visibly changes the plan shape.

**Step 6 — Plan review.** The DAG rendered as levels, left to right, each node a
small card with its role colour, name, declared reads/writes, and budget. Nodes
carrying an inherited pitfall constraint show a rust marker. The user can drag a
node between levels (revalidated against declared IO), or click `Send back` with
a comment to re-plan. Primary: `Start run`.

### 19.4 View 1 — Lineage

As currently built, minus the lede paragraph. Additions:

- Template status chips (`fresh` / `drifting` / `stale` / `quarantined`) on
  hover tooltips, with drift score.
- A `selection mode` used by New run step 3, where clicking a template node
  returns it to the wizard.
- Quarantined templates render as a rust ring rather than a filled dot, so they
  are visibly different from a failed run.

### 19.5 View 2 — Memory

As currently built, minus the lede. The three tier cards stay — they are labels,
not prose, and each is under 20 words. Additions:

- Clicking a tier card filters the row-level graph to that tier.
- The `Top-k per prompt` row becomes an inline control, so the user can change
  retrieval breadth and see the token attribution chart update.

### 19.6 View 3 — Agents

As currently built, minus the lede. Additions:

- A `vindication` column between `pass` and the end (see §19.7).
- Cost column shows `—` and a quota bar instead of dollars for subscription
  transports.
- Clicking any row opens a **context inspector** drawer from the right: the
  agent's current context window broken into blocks (system, retrieved memory,
  artifacts, task node) with the token count and percentage of each. This is the
  live working-memory view; it reads process state over SSE and is not backed by
  any table.

### 19.7 View 4 — Dissent

**New view. This is the feature people will talk about — give it room.**

Top third: **vindication leaderboard.** One card per agent, sorted by
vindication rate. Each card: agent name in mono, model, a large mono percentage,
and a stacked micro-bar showing overruled / resurrected / vindicated / refuted.
An agent whose vindication rate exceeds its peers' by more than the arbiter's
epsilon gets an amber `promote?` chip that opens a one-click roster change.

Below: **the ledger.** A table of rejected proposals, newest first.

```
Node          Dissenter   Winner    Stage   Reason                Status
────────────────────────────────────────────────────────────────────────────
schema.design dev-c       dev-a     3       score 0.61 vs 0.74    ● vindicated
api.orders    dev-b       dev-a     2       verifier fail         ○ refuted
auth.session  dev-c       dev-b     1       pitfall p-0042        ○ dormant
```

- Status dots: dormant `--dimmer`, resurrected `--violet`, vindicated `--sage`,
  refuted `--rust`.
- Clicking a row expands it in place to a side-by-side diff of the winning and
  dissenting proposals, with the arbiter's stage-by-stage elimination trace
  rendered as a five-step strip showing where each proposal dropped out.
- A `Resurrect` button on dormant rows for nodes that have since failed. It
  forks the run from that node using the dissenting proposal — the same
  machinery as §16.5, exposed as a one-click action.
- Filter chips: by agent, by status, by node.

The emotional beat of this view is *the roads not taken, and which of them were
right*. Design it so that reads at a glance.

### 19.8 View 5 — Workspace

Remove the lede paragraph. Everything below is the reworked spec.

```
┌──────────────┬──────────────────────────────────────────────┐
│ TREE 218px   │ BREADCRUMB   worktree › memory › schema.sql   │
│              ├──────────────────────────────────────────────┤
│ [icon] file  │ EDBAR  ⟦icon⟧ schema.sql · sql · 47 lines     │
│ [icon] file  │        [diff ▾] [🔒 held by dev-a]            │
│   🔒         ├──┬───┬───────────────────────────────────────┤
│              │ B│ N │                                        │
│              │ L│ U │  CodeMirror 6                          │
│              │ A│ M │                                        │
│              │ M│   │                                        │
│              │ E│   │                                        │
│              ├──┴───┴───────────────────────────────────────┤
│              │ RUNBAR  compose.yaml ✓  [▶ Run] ● api ● db    │
└──────────────┴──────────────────────────────────────────────┘
```

**Tree.** File rows show a language logo (Devicon SVG, bundled and tree-shaken,
never fetched per render) in place of the text extension badge. A lock glyph
appears on leased files. Folders collapse. `⌘P` opens a fuzzy file jump overlay;
`⌘⇧F` opens content search backed by ripgrep in the sandbox.

**Breadcrumb.** Each segment clickable; the last segment shows a dirty dot when
there are unsaved changes.

**Edbar.** Language logo, filename, resolved mode, line count. A `why` popover
on the mode showing `extension → tier → grammar` (§13). A diff toggle switching
between current state and the last agent's applied patch. A lock chip naming the
holding agent when leased.

**Blame gutter.** A 6px vertical strip between the line numbers and the code,
coloured per agent, showing which agent last touched each line. Hovering a
segment reveals agent, node id, and timestamp in a tooltip. Clicking jumps to
that node in the Dissent or Agents view. This is the one thing this editor does
that no normal editor can — do not cut it.

**Editor.** CodeMirror 6 per §13. Read-only with an explanatory chip when the
file is leased by an agent. Unsaved-change guard on file switch.

**Runbar.** Pinned below the editor, always visible.

- Compose file detected → `compose.yaml ✓` in sage, `Run` enabled, and a chip
  per service showing health once running.
- Dockerfile only → `Run` disabled, `EmptyState`: *"No compose file. Generate one
  from the Dockerfile?"* with a `Generate` button dispatching a devops node.
- Neither → `Run` disabled, *"Not containerised yet."* with `Containerise this
  project`.
- Running → `Stop` replaces `Run`; a log drawer slides up from the runbar with
  per-service tabs, streamed over SSE.

### 19.9 States

Every data surface implements four states explicitly. No spinners on the whole
stage; skeleton the panel that is loading and leave the rest interactive.

- **Loading** — skeleton rows at the panel level, matching final row heights so
  nothing reflows.
- **Empty** — one line naming what is missing, one button that creates it.
  Directional, never apologetic.
- **Error** — what failed, what it affects, one retry action. Never a raw stack
  trace in the UI; the trace goes to the ticker and the log drawer.
- **Stale** — when the SSE stream drops, the header rail dims to 60% and a
  `reconnecting` chip appears in the ticker. Data is never silently frozen.

### 19.10 Accessibility and input

- Visible keyboard focus on every interactive element, `2px solid --amber`,
  offset 2px.
- All six views reachable by keyboard; `⌘1`–`⌘6` switch views.
- Canvas graphs have a tabular fallback reachable by a `table view` toggle —
  a canvas is not accessible and the data must be.
- Colour never carries meaning alone: every status dot is paired with a text
  label or an icon shape.
- `prefers-reduced-motion` disables the ticker pulse and all transitions.

---

## 20. Code walkthrough

### 20.1 Repository layout

```
lineage/
├── contracts/            # Pydantic v2 models — the single source of truth
│   ├── envelope.py       #   agent-to-agent message
│   ├── node.py           #   NodeSpec, DAG, declared IO
│   ├── fingerprint.py    #   SpecFingerprint
│   └── usage.py          #   Usage, Cost, Quota
├── memory/
│   ├── store.py          # writes: episodic, semantic, procedural
│   ├── retrieval.py      # hybrid BM25 + vector + RRF + rerank
│   ├── supersede.py      # decision status transitions
│   └── distil.py         # run → template (batch, local model)
├── planning/
│   ├── extract.py        # brief → SpecFingerprint (local model)
│   ├── match.py          # fingerprint → nearest runs + template
│   ├── roster.py         # template + scores → proposed roster
│   └── plan.py           # brief + template + pitfalls → DAG
├── execution/
│   ├── scheduler.py      # level-wise DAG walk, budgets, backpressure
│   ├── leases.py         # §18.1
│   ├── pool.py           # warm sandbox pool
│   ├── verify.py         # verifier registry
│   └── runner.py         # compose gate, §7
├── arbitration/
│   ├── arbiter.py        # §18.3 deterministic five-stage
│   ├── dissent.py        # §8 ledger, resurrection, vindication
│   └── scores.py         # pass / escalation / vindication per agent×domain
├── transports/
│   ├── base.py           # Transport ABC
│   ├── api.py            # metered
│   ├── subscription.py   # headless CLI over OAuth
│   └── local.py          # Ollama / vLLM
├── security/
│   ├── broker.py         # scoped short-lived credentials
│   ├── taint.py          # untrusted-content propagation
│   ├── egress.py         # per-role allowlist → netns rules
│   └── scan.py           # gitleaks on egress
├── db/
│   ├── migrations/       # sqlc-style plain SQL, forward-only
│   └── tenancy.py        # §18.4 connection scoping
├── api/
│   ├── main.py           # FastAPI
│   ├── sse.py            # telemetry stream
│   └── routes/
└── web/                  # React + Vite + TanStack Query
    ├── src/shell/        # header, rail-nav, ticker
    ├── src/views/        # newrun, lineage, memory, agents, dissent, workspace
    ├── src/components/   # §19.2 shared
    └── src/lang/         # §13 registry + Devicon map
```

One rule about this layout: **`contracts/` imports nothing from the rest of the
tree.** Everything else imports from it. The Pydantic models generate JSON Schema
at build time, which generates the TypeScript types in `web/src/contracts.ts`.
There is one definition of an `Envelope` in the whole system.

### 20.2 Contracts

```python
# contracts/envelope.py
from enum import Enum
from pydantic import BaseModel, Field

class Intent(str, Enum):
    """Closed set. This is the structural defence against prompt injection:
    injected prose has no intent to become."""
    PROPOSE  = "propose"
    CRITIQUE = "critique"
    ACCEPT   = "accept"
    BLOCK    = "block"
    ASK      = "ask"

class Envelope(BaseModel):
    model_config = {"extra": "forbid"}     # unknown fields reject the message

    from_role:     str
    to_role:       str
    intent:        Intent
    task_id:       str
    artifact_refs: list[str] = Field(default_factory=list)   # sha256 CAS hashes
    claims:        list[str] = Field(default_factory=list)
    confidence:    float = Field(ge=0.0, le=1.0)
    tainted:       bool = False
    notes:         str = ""    # advisory; nothing downstream may branch on this
```

`extra="forbid"` is load-bearing. A model that invents a field gets its message
rejected at the boundary rather than forwarded, and the rejection is a retry
signal rather than a silent corruption.

`artifact_refs` are content hashes, never inlined content. This is layer L2 of
§10: an agent receives a 150-token summary plus a hash, and calls
`read_artifact(hash, line_range)` for what it actually needs. Pasting a
2,000-line file into five agents wastes four copies.

```python
# contracts/node.py
class NodeSpec(BaseModel):
    id:             str
    role:           str
    intent:         str
    irreversible:   bool = False
    reads:          list[str] = []      # globs — drives §18.1 co-scheduling
    writes:         list[str] = []
    acceptance:     list[str] = []      # verifier ids that must pass
    budget_usd:     float
    constraints:    list[str] = []      # injected pitfall ids
    depends_on:     list[str] = []
```

`reads`/`writes` are the primary concurrency mechanism, not documentation. The
scheduler refuses to co-schedule nodes whose write globs intersect.

### 20.3 Transports

Three implementations, one interface. Cost is a union type because subscription
agents do not spend dollars.

```python
# transports/base.py
from abc import ABC, abstractmethod

class Transport(ABC):
    name: str

    @abstractmethod
    async def complete(self, prompt: Prompt, *, schema: type[BaseModel] | None,
                       budget: Budget) -> Completion:
        ...

    @abstractmethod
    def capacity(self) -> Capacity:
        """Concurrency limit + current headroom. The scheduler sizes its
        semaphore from this, so a subscription CLI with a 5-request window
        cannot be dispatched 40 nodes."""
```

```python
# transports/subscription.py
class SubscriptionTransport(Transport):
    """Drives an official headless CLI authenticated against the user's
    consumer subscription. Never a browser session, never reused cookies —
    that path violates provider terms and gets accounts banned."""

    def __init__(self, cli: CliSpec, concurrency: int = 1):
        self._sem = asyncio.Semaphore(concurrency)
        self._cli = cli

    async def complete(self, prompt, *, schema, budget):
        async with self._sem:
            proc = await asyncio.create_subprocess_exec(
                *self._cli.argv(prompt, output="stream-json"),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=self._cli.env(),            # no inherited secrets
            )
            blocks = [json.loads(l) async for l in readlines(proc.stdout) if l]
            return self._cli.parse(blocks, schema)

    def capacity(self):
        return Capacity(limit=self._cli.window_limit,
                        used=self._quota.used,
                        resets_at=self._quota.resets_at,
                        unit="requests")
```

Parse the CLI's **structured output stream**, never stdout text. Every one of
these CLIs offers a JSON stream mode; using it is the difference between a
transport and a screen-scraper.

### 20.4 Scheduler

```python
# execution/scheduler.py
class Scheduler:
    def __init__(self, pool, leases, ledger, transports, max_inflight=16):
        self.pool, self.leases, self.ledger = pool, leases, ledger
        self.gate = asyncio.Semaphore(max_inflight)
        self.transport_gates = {
            name: asyncio.Semaphore(t.capacity().limit)
            for name, t in transports.items()
        }

    async def run(self, dag: Dag, ceiling_usd: float):
        pending = list(dag.nodes)
        while pending:
            level = self._concurrency_set(pending)     # no write-glob overlap
            deferred: list[NodeSpec] = []
            async with asyncio.TaskGroup() as tg:
                for node in level:
                    if self.ledger.spent >= ceiling_usd:
                        raise BudgetExceeded(node.id, self.ledger.spent)
                    tg.create_task(self._attempt(node, deferred))
            pending = [n for n in pending if n not in level] + deferred

    async def _attempt(self, node, deferred):
        held = await self.leases.acquire_all(node)     # ordered, all-or-nothing
        if held is None:
            deferred.append(node)                      # never an error
            return
        try:
            async with self.gate, self.transport_gates[node.transport]:
                result = await self.pool.dispatch(node)
            self.ledger.charge(node, result.usage)
            await self.verify(node, result)
        finally:
            await self.leases.release(held)
```

Three things to notice. **No LLM appears in this file** — the planner wrote the
DAG, this walks it, and that separation is what makes a run replayable. **Lease
contention defers rather than fails**, so the user never sees a lock error.
**`asyncio.TaskGroup`** gives structured concurrency: if one node raises, the
group cancels its siblings and the exception propagates with the others attached,
which is what you want for a budget breach.

Concurrency, not parallelism. One core, one event loop, hundreds of in-flight
calls. The expensive resource is the sandbox pool, not the CPU.

```python
# execution/leases.py
async def acquire_all(self, node) -> list[UUID] | None:
    globs = sorted(node.writes)                # ORDERED — prevents deadlock
    try:
        async with self.conn.transaction():
            ids = []
            for g in globs:
                row = await self.conn.fetchrow("""
                    INSERT INTO file_leases
                      (tenant_id, run_id, node_id, agent_id, path_glob, mode, expires_at)
                    VALUES ($1,$2,$3,$4,$5,'write', now() + $6)
                    ON CONFLICT DO NOTHING
                    RETURNING id
                """, self.tenant, node.run_id, node.id, node.agent, g, node.ttl)
                if row is None:
                    raise LeaseContention(g)     # rolls the whole txn back
                ids.append(row["id"])
            return ids
    except LeaseContention:
        return None
```

Lexicographic ordering plus all-or-nothing in one transaction is the entire
deadlock story. Do not optimise it into per-file acquisition.

### 20.5 Arbiter

```python
# arbitration/arbiter.py
class Arbiter:
    """Deterministic. Same inputs → same winner, which is what forking
    (§16.5) and replay require. No model in this loop."""

    def decide(self, node: NodeSpec, proposals: list[Proposal]) -> Decision:
        trace: list[Elimination] = []
        alive = proposals

        # 1 — hard gates
        alive, out = partition(alive, lambda p: self.gates.passes(p, node))
        trace += [Elimination(p, stage=1, reason=self.gates.why(p)) for p in out]
        if len(alive) == 1:
            return self._finish(alive[0], trace, stage=1)

        # 2 — executable ground truth
        if node.acceptance:
            results = self.verifier.run_all(node, alive)
            alive, out = partition(alive, lambda p: results[p.id].passed)
            trace += [Elimination(p, stage=2, reason=results[p.id].summary)
                      for p in out]
            if len(alive) == 1:
                return self._finish(alive[0], trace, stage=2)

        # 3 — scored vote
        scored = sorted(((self._score(p, node), p) for p in alive), reverse=True)

        # 4 — tie goes to a human, never a coin flip
        if len(scored) > 1 and scored[0][0] - scored[1][0] < self.cfg.epsilon:
            return Decision.held(node, scored, trace)

        winner = scored[0][1]
        trace += [Elimination(p, stage=3, reason=f"score {s:.2f} vs "
                              f"{scored[0][0]:.2f}") for s, p in scored[1:]]
        return self._finish(winner, trace, stage=3)

    def _score(self, p: Proposal, node: NodeSpec) -> float:
        a, d, w = self.scores[p.agent], node.domain, self.cfg.weights
        return ( w.agree     * p.agreement
               + w.pass_     * a.pass_rate[d]
               + w.vindicate * a.vindication_rate[d]
               - w.escalate  * a.escalation_rate[d]
               - w.cost      * p.normalised_cost )

    def _finish(self, winner, trace, stage) -> Decision:
        self.dissent.record(winner, trace, stage)      # §8 — nothing discarded
        return Decision.won(winner, trace, stage)
```

Weights live in `config/arbiter.yaml`, not here. They are tuning parameters, and
a tuning parameter in a source file is a tuning parameter nobody tunes.

`_finish` always calls `dissent.record`. That single line is what turns
already-paid-for losing proposals into the vindication dataset.

### 20.6 Dissent ledger

```python
# arbitration/dissent.py
class DissentLedger:
    async def record(self, winner, trace, stage):
        await self.db.executemany("""
            INSERT INTO dissent (tenant_id, run_id, node_id, dissenter,
                                 winner, stage, reason, proposal, status)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,'dormant')
        """, [(...) for e in trace])

    async def resurrect(self, node_id: str) -> Proposal | None:
        """Called when the winning path fails verification. Costs zero new
        planning tokens: the alternative was written and reasoned about
        during the original round."""
        row = await self.db.fetchrow("""
            SELECT * FROM dissent
            WHERE run_id = $1 AND node_id = $2 AND status = 'dormant'
            ORDER BY stage DESC, score DESC LIMIT 1
        """, self.run_id, node_id)
        if not row:
            return None
        await self._set_status(row["id"], "resurrected")
        return Proposal.model_validate_json(row["proposal"])

    async def settle(self, dissent_id: UUID, passed: bool):
        await self._set_status(dissent_id, "vindicated" if passed else "refuted")
        await self.scores.bump_vindication(dissent_id, passed)
```

The whole feature is three methods and one table. Everything it needs was
already generated and already in the episodic log — this is value extraction
from spend that currently evaporates.

`resurrect` turns a 90-second replan into a branch switch, because the
alternative plan already exists.

### 20.7 Hybrid retrieval

```sql
-- memory/retrieval.sql
WITH vec AS (
  SELECT id, row_number() OVER (ORDER BY embedding <=> $2) AS rank
  FROM semantic_memory
  WHERE tenant_id = $1 AND status = 'active'
  ORDER BY embedding <=> $2 LIMIT 50
),
kw AS (
  SELECT id, row_number() OVER (ORDER BY ts_rank_cd(tsv, q) DESC) AS rank
  FROM semantic_memory, plainto_tsquery('english', $3) q
  WHERE tenant_id = $1 AND status = 'active' AND tsv @@ q
  LIMIT 50
)
SELECT m.*, 1.0/(60 + COALESCE(v.rank, 1000))
          + 1.0/(60 + COALESCE(k.rank, 1000)) AS rrf
FROM semantic_memory m
LEFT JOIN vec v ON v.id = m.id
LEFT JOIN kw  k ON k.id = m.id
WHERE v.id IS NOT NULL OR k.id IS NOT NULL
ORDER BY rrf DESC
LIMIT 24;
```

Then rerank those 24 locally with `bge-reranker-v2-m3` and keep the top 6.

Every clause here earns its place. `status = 'active'` in both branches is what
stops an agent re-proposing a reversed decision — cosine similarity puts "use
Postgres" and "do not use Postgres" almost on top of each other, and only the
status filter separates them. Reciprocal rank fusion with k=60 is the standard
constant and needs no tuning. The 50→24→6 funnel is deliberate: wide recall,
cheap fusion, expensive rerank on a small set, and a hard cap of 6 because more
than that and retrieved memory eats a third of every context window.

Measured: ~0.68 recall@10 vector-only, ~0.91 with this pipeline.

### 20.8 Run gate

```python
# execution/runner.py
COMPOSE = ("compose.yaml", "compose.yml",
           "docker-compose.yaml", "docker-compose.yml")

def gate(worktree: Path) -> RunGate:
    for name in COMPOSE:
        if (worktree / name).exists():
            return RunGate.ready(name)
    if (worktree / "Dockerfile").exists():
        return RunGate.blocked(
            reason="no_compose",
            offer=Offer("Generate compose file", task="devops.compose_from_dockerfile"))
    return RunGate.blocked(
        reason="not_containerised",
        offer=Offer("Containerise this project", task="devops.containerise"))

async def start(worktree: Path, gate: RunGate, netns: Netns):
    assert gate.ready                      # Run is disabled otherwise, no bypass
    return await spawn(["docker", "compose", "-f", gate.file, "up", "--build"],
                       cwd=worktree, netns=netns)
```

Compose only, no bare-command fallback. It makes multi-service the default case,
gives you a declared topology to apply the egress allowlist against, and means
"it runs on my machine" becomes a property of a file in the repo.

Note the shape of `RunGate.blocked`: it carries an `Offer`, so the UI never has
to know *why* Run is disabled or what to suggest. The backend decides, the
`EmptyState` renders it.

### 20.9 Telemetry

One SSE endpoint, one event envelope, one client reducer.

```python
# api/sse.py
@router.get("/runs/{run_id}/stream")
async def stream(run_id: UUID, tenant=Depends(current_tenant)):
    async def gen():
        async for ev in bus.subscribe(run_id, tenant):
            yield f"event: {ev.kind}\ndata: {ev.model_dump_json()}\n\n"
    return EventSourceResponse(gen())
```

Event kinds: `spend`, `node`, `agent`, `lease`, `dissent`, `memory`, `service`,
`ticker`. The client keeps one normalised store and every view is a selector
over it, so the header rail, the agents table, and the dissent ledger cannot
disagree about the state of a run.

SSE over WebSockets because the flow is one-way, it reconnects for free, and it
survives corporate proxies that eat WS upgrades. When the stream drops, the UI
dims per §19.9 rather than silently freezing.

### 20.10 What to build first

Follow §17. M1 is a single model, a single transport, a typed DAG, the
scheduler, leases, the verifier, the episodic log, and the compose gate. That is
a working product with no memory, no consensus, and no vector search in it —
and building it first is what keeps the interesting parts honest.
