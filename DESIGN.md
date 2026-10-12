---
name: lineage-design-system
description: "Use for any frontend/ renderer UI, visual polish, component, layout, theme, motion, or interaction change in Lineage. Read before proposing or implementing visual work."
---

# Design system — Lineage

Lineage is an orchestrator console for multi-agent builds with supersession-aware
memory, a deterministic consensus arbiter, and a dissent ledger. It makes the
state of a build legible: what is running, what disagreed, what is verified,
what was superseded, and where a human decision has the most leverage.

This is a product UI, not a marketing site. It must feel calm under sustained
use, reward scanning, and tell the truth about cost and whether a result is
`simulated` or `live`.

The graphite token system, shadcn primitives, and app shell are ported from the
Orchestrator.inc reference (`agent-orchestrator`); that project's `DESIGN.md` is
the parent of this one. Where this guide is silent, the reference guide applies.
This guide records only what differs because Lineage's core object is a **run**,
not a coding session.

## 1. Product and reader

- **Reader:** an operator supervising a multi-agent build — choosing models and
  roles, starting runs, watching consensus and dissent, and deciding what to
  resurrect, settle, fork, or ship.
- **Reader's job:** understand the current state of every run in seconds; see
  what needs a human (an open dissent); trust the cost and verified counts; open
  the right run and intervene.
- **Core object:** a **run** — a brief → fingerprint → DAG of nodes, each with a
  `mode` (`simulated`/`live`), spend, arbitration outcome, and verify state.
- **Memorable promise:** "I can run several agents and trust what they produced
  and what it cost."
- **Product posture:** operational, cost-honest, technically literate, compact.
  Lineage never hides that a result is simulated or that a disagreement happened.

### Non-negotiable hierarchy

When requirements compete, preserve them in this order:

1. Truthful operational state: `simulated` vs `live`, honest spend, real verify
   status. Never let polish imply a result is verified when it is not.
2. The open decision — a dissent that needs the user (resurrect / settle / fork).
3. Context for the active run: nodes, lineage, memory, arbitration, workspace.
4. Fast scanning across runs on the board.
5. A coherent visual system and refined motion.

## 2. Visual thesis

Inherited verbatim from the reference: **dark-first precision instrument**,
layered charcoal (not pure black), rare semantic color, modest radius, compact
density, quiet competence. No gradients, glass, glow, stock imagery, emoji, or
novelty visual language in the working UI. Do not re-derive these; follow the
reference `DESIGN.md` §2, §6–§8.

## 3. App architecture expressed visually

One persistent shell; routes replace the center surface.

- **Sidebar:** rail nav across the views (Board, Lineage, Memory, Agents,
  Dissent, Workspace, Settings) plus the run section. Answers "where am I?".
- **Topbar:** orientation + the **spend rail** (live spend/quota) + the
  Simple/Expert toggle + theme toggle. High-value only; no page-control dupes.
- **Center:** the board, an analytical view, a run detail, or settings.

Routing is **hash history** (`createHashHistory`) — matches the reference and
needs no nginx SPA-fallback config.

### Progressive disclosure — Simple vs Expert

Lineage adds one architectural rule the reference does not have. The
`ui-store.mode` (`simple` | `expert`, persisted) governs the home route:

- **Simple:** `_shell.index` is a single column — brief → progress →
  result with cost and verified-count. No board, no analytical views in the
  nav's foreground. For someone who just wants a verified build.
- **Expert:** `_shell.index` is the Kanban board and the full rail nav is live.

Simple mode is the default. The toggle must never hide a `simulated` badge or a
cost figure — truth-in-labeling outranks disclosure.

## 4. Operational state and color — Lineage status lanes

Status is derived from durable run/node facts (status + `mode` + dissent
presence), never stored as a separate display truth. The mapping lives in a pure
function, `lib/board-presentation.ts` (self-checked by `board-presentation.test.ts`).

### Board lanes

The canonical lanes, left to right, are a run's life, not a session's:

| Lane | Meaning | Derived from |
| --- | --- | --- |
| Queued | accepted, not yet working | run/node status before first active node |
| Working | nodes executing | an active node, no open dissent |
| Dissent | **needs you** — a recorded disagreement is open | open dissent on the run |
| Verifying | a behavioral verifier is gating | node in verify |
| Verified | a real model + verifier gated it → `live` | all nodes verified, `mode = live` |
| Superseded | replaced by a newer run/decision | supersession recorded |

Reuse the reference's `--color-status-*` tokens for lane dots and card accents.
Map Lineage meanings onto the existing palette — do **not** add new status hex:

- Working → `--color-status-working`
- Dissent (needs you) → `--color-status-needs-you`
- Verifying → `--color-status-validating`
- Verified → `--color-status-ready`
- Superseded → `--color-status-merged` (historical terminal state)
- Queued / idle → muted/passive tokens

### The `simulated` / `live` badge

Every run and node carries a `mode` badge (`ModeBadge.tsx`). This is Lineage's
most important semantic signal and the one rule that overrides brevity: a
`simulated` run must always show the badge, on the board card, the run detail,
and any summary. `simulated` uses a cautionary (not success) treatment; `live`
is quiet. Pair color with the word — never color alone.

### Cost honesty

Spend, verified-count, and cost-per-verified are first-class metadata, not
decoration. Use tabular figures. The topbar spend rail and card metrics read
from the same live `useStream` ticks the engine emits; they must not drift from
a run's recorded spend. A cost figure is never rounded away to look cleaner.

## 5. Board and cards

The board (`Board.tsx`, `BoardLane`, `SessionCard`) is the project's operational
overview, not a KPI dashboard. It follows the reference's kanban rules (§9
"Kanban board and cards") with Lineage's object:

- A card represents one **run** (the legitimate exception to "no individual
  borders"); drilling in reveals its nodes. Click → `/run/:id`.
- Card information order: label; `mode` badge; one derived status line; then
  compact spend / verified-count / cost-per-verified. A **"needs you"** flag
  appears only when a dissent is open — the one place restrained attention
  motion is allowed.
- Lanes are one continuous grid with shared vertical dividers and a compact
  header (semantic dot, sentence-case name, count). Not rounded panels.
- The board re-derives live from SSE; preserve spatial continuity — no flicker
  or broad skeleton replacement for a single node's state change.

## 6. Views carried from the old console

The six analytical views (Lineage, Memory, Agents, Dissent, Workspace) keep
their data and endpoints exactly (`lib/api.ts`: `useApi`/`post`/`useStream`,
ported unchanged). Only presentation moved to shadcn primitives + graphite
tokens. The CodeMirror 6 editor (`CodeEditor.tsx` + `lang-registry.ts`) is
copied verbatim, not rewritten. When reskinning any of these, apply the
reference's shared-list, hairline, and sentence-case rules; do not invent a
one-off primitive where a shared one exists.

## 7. Everything else

For tokens, typography, spacing, radius/borders, buttons, inputs, dropdowns,
dialogs, tooltips, motion, accessibility, anti-patterns, and the design-QA
checklist, follow the reference `DESIGN.md` (`agent-orchestrator/DESIGN.md`)
§6–§15 as written — the token files and primitives are the same ones. This guide
overrides it only on the three Lineage-specific points above: the Simple/Expert
home split (§3), the status lanes and the `simulated`/`live` + cost rules (§4),
and the run-as-card board (§5).

## Decisions log

| Date | Decision | Rationale |
| --- | --- | --- |
| 2026-10-12 | Adopt the reference graphite tokens, shadcn primitives, and shell wholesale; record only Lineage deltas here | The reference's UID language is the thing worth copying; re-stating it would just drift from the parent guide. |
| 2026-10-12 | Board lanes are run life-cycle (Queued→…→Superseded), mapped onto existing `--color-status-*` tokens | Lineage's object is a run, not a session; reusing the palette keeps one semantic color system. |
| 2026-10-12 | `simulated`/`live` badge and cost figures override brevity and progressive disclosure | Truth-in-labeling and cost-honesty are the product's core promise; disclosure must never suppress them. |
| 2026-10-12 | Hash history, no nginx SPA fallback | Matches the reference and needs zero nginx rewrite config. |
