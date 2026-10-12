# Refactor plan — adopt the Orchestrator.inc structure + UI

**Chosen approach: Option B — Restructure repo + reskin**, staged so it lands as
A (reskin + Kanban) first and grows into B (repo restructure + typed contracts).
Reference: `C:\Users\Error_401\Desktop\agent-orchestrator` ("Orchestrator.inc").
Ours: `C:\Users\Error_401\Desktop\orchestrator` ("Lineage").

Backend stays **FastAPI/Python** — logic unchanged. The change is the frontend
shape + UI, plus typed contracts between the two.

---

## Why we're copying the shell, not rewriting the engine

The reference's value to us is its **UI language** and its **session/board
model** — not Go or Electron. Our differentiators are what make the clone worth
doing, and they must survive the refactor:

1. **Provenance-first** — supersession-aware memory + inheritance/lineage graph.
2. **Consensus arbiter + dissent ledger** — recorded, reversible disagreement
   (resurrect / settle / fork).
3. **Truth-in-labeling** — `simulated` vs `live`; cost-per-verified-result.
4. **Memory as a substrate** — hybrid BM25+vector+RRF+rerank, distil, drift.
5. **Cost-honest + transport-agnostic** — API / subscription / local, OpenRouter
   live pricing + balance, spend rail.
6. **Security/tenancy posture** — forced RLS, egress allowlist, taint, scan,
   envelope-encrypted keys, sandbox pool.
7. **Progressive disclosure + offline-first** — Simple↔Expert, runs with no key/GPU.

---

## Target structure (theirs, adapted — Python backend kept)

```
orchestrator/
  frontend/
    src/
      renderer/
        routes/          TanStack Router: _shell.tsx + board, lineage, memory,
                         agents, dissent, workspace, settings, run.$id
        components/
          ui/            shadcn primitives (button, card, dialog, select,
                         dropdown-menu, tabs, tooltip, sidebar, badge, input,
                         separator, sheet, skeleton)
          ...            feature components (Sidebar, Topbar, SpendRail, Board,
                         SessionCard, LineageGraph, ...)
        stores/          zustand (ui-store: simple/expert, run-store)
        hooks/  lib/
        styles/          tokens.css (ported graphite system) + styles.css
        main.tsx  router.tsx  routeTree.gen.ts
      api/schema.ts      generated from backend OpenAPI (Phase 5)
    index.html  vite.config.ts  tailwind  tsconfig.json  package.json
  backend/lineage/...    FastAPI, logic UNCHANGED (+ OpenAPI emit in Phase 5)
  DESIGN.md              our adapted design-system doc
  compose.yaml           web service points at frontend/
```

**Current frontend being replaced:** `web/src` (~2,130 lines) — plain React 18,
manual `useState(view)` switching in `App.tsx` (186 lines), inline color tokens
(`COLOR` in `components.tsx`, 489 lines), no router, no Tailwind, no shadcn.
Views: NewRun (262), Lineage (73), Memory (70), Agents (106), Dissent (128),
Workspace (163), Settings (452), SimpleRun (96). Data layer: `api.ts` — `useApi`
(react-query GET), `post`, `useStream` (SSE EventSource at
`/api/runs/:id/stream`, ticker + spend events). **All of this behaviour is kept;
only the presentation changes.**

**Routing note:** the reference uses `createHashHistory()` because Electron
serves the renderer from `file://`. We serve over nginx with an `/api` proxy, so
we *could* use browser history — but hash history needs **zero nginx config**
(no SPA fallback rewrite) and is otherwise identical. **Decision: use hash
history**, same as the reference.

---

## Phased execution

Each phase ends in a **runnable** state and has an explicit verification step.
Backend stays up the whole time (`docker compose up -d db backend`); the new
frontend talks to it via a Vite dev proxy, so phases 0–5 don't touch the running
stack.

### Phase 0 — Scaffold `frontend/` + design tokens
**Goal:** a new Vite+React+Tailwind app that boots with the reference's graphite
theme, proxying `/api` to the backend. Nothing ported yet.

Steps:
1. `frontend/` with `npm create vite@latest` (react-ts). Set
   `package.json` name `orchestrator-frontend`, React 19 (`react@19`,
   `react-dom@19`, `@types/react@19`).
2. Add deps: `tailwindcss @tailwindcss/vite`, `class-variance-authority`,
   `clsx`, `tailwind-merge`, `lucide-react`, `@tanstack/react-query@5`,
   `@fontsource/archivo`, `@fontsource/jetbrains-mono` (fonts we already use).
3. `vite.config.ts`: `@tailwindcss/vite` plugin; `server.proxy` maps `/api` →
   `http://localhost:8000` with `ws`/SSE passthrough (`changeOrigin: true`).
   `server.port: 5173`. `resolve.alias` `@` → `src`.
4. Port `frontend/src/renderer/styles/tokens.css` from the reference verbatim
   (the full graphite oklch system + light/dark + status colors), then a thin
   `styles.css` that imports tokens + Tailwind layers + our font-faces.
5. `lib/apply-initial-theme.ts` (read `localStorage.theme`, set
   `:root[data-theme]`) + `lib/cn.ts` (`clsx` + `tailwind-merge`).
6. Minimal `main.tsx`: QueryClientProvider + a placeholder shell that renders the
   theme so colors are visible.

Files: `frontend/{package.json,vite.config.ts,tsconfig.json,index.html}`,
`frontend/src/{main.tsx,renderer/styles/tokens.css,renderer/styles/styles.css,renderer/lib/cn.ts,renderer/lib/apply-initial-theme.ts}`.

**Verify:** `cd frontend && npm run dev` boots on :5173; a hard-coded `fetch("/api/health")`
returns 200 through the proxy; dark graphite background + Archivo font render;
theme toggle flips `data-theme`.

### Phase 1 — Primitives + app shell
**Goal:** the reference's Sidebar + Topbar shell, built on shadcn primitives,
with our Simple/Expert toggle moved to a zustand store. Still no real views.

Steps:
1. Install Radix deps the primitives need (`@radix-ui/react-dialog`,
   `-dropdown-menu`, `-select`, `-tabs`, `-tooltip`, `-separator`, `-label`,
   `-slot`). Add `components.json` (shadcn config) so later `npx shadcn add`
   works.
2. Port the `components/ui` primitives we'll use, copied from the reference and
   trimmed to our needs: `button, card, dialog, select, dropdown-menu, tabs,
   tooltip, sidebar, badge, input, label, separator, sheet, skeleton`.
3. Build the shell components from the reference: `Sidebar.tsx` (rail nav +
   project/run section), `ShellTopbar.tsx` (title + spend rail slot + Simple/
   Expert + theme toggle), `CenterPanelShell.tsx` (page frame). Match the DESIGN.md
   rules (hairline borders, sentence case, compact).
4. `stores/ui-store.ts` (zustand, persisted): `{ mode: "simple"|"expert",
   theme, setMode, setTheme }` — replaces the `localStorage("ui")` logic in the
   old `App.tsx`.
5. Static nav list mirroring our current `VIEWS` (Board, Lineage, Memory, Agents,
   Dissent, Workspace, Settings), wired to local state for now (router lands in
   Phase 2).

Files: `frontend/src/renderer/components/ui/*.tsx`,
`.../components/{Sidebar,ShellTopbar,CenterPanelShell,SpendRail}.tsx`,
`.../stores/ui-store.ts`, `frontend/components.json`.

**Verify:** shell renders with sidebar + topbar matching the reference visually;
Simple/Expert and theme toggles persist across reload; `npm run typecheck` clean.

### Phase 2 — Router (TanStack Router)
**Goal:** replace the manual `useState(view)` switch with file-based routing and
a shared `_shell` layout; add a run-detail route.

Steps:
1. Add `@tanstack/react-router` + `@tanstack/router-plugin` (Vite codegen for
   `routeTree.gen.ts`). Enable the plugin in `vite.config.ts`.
2. `routes/__root.tsx` (QueryClient context, pending fallback),
   `routes/_shell.tsx` (renders Sidebar+Topbar+`<Outlet/>` from Phase 1).
3. Child routes, one per current view (empty placeholders, filled in Phase 3):
   `_shell.index.tsx` (→ Board), `_shell.lineage.tsx`, `_shell.memory.tsx`,
   `_shell.agents.tsx`, `_shell.dissent.tsx`, `_shell.workspace.tsx`,
   `_shell.settings.tsx`, and `_shell.run.$runId.tsx` (run detail).
4. `router.tsx` with `createHashHistory()` + `defaultPreloadStaleTime: 0`
   (SSE is source of truth, same rationale as the reference).
5. Rewire Sidebar nav items to `<Link>`; drop the Phase-1 local view state.

Route ↔ old view map:

| Route | Replaces | Notes |
|---|---|---|
| `_shell.index` | SimpleRun / landing | Board in Expert; Simple summary in Simple mode |
| `_shell.lineage` | Lineage | |
| `_shell.memory` | Memory | |
| `_shell.agents` | Agents | |
| `_shell.dissent` | Dissent | |
| `_shell.workspace` | Workspace | keeps CodeMirror editor |
| `_shell.settings` | Settings | |
| `_shell.run.$runId` | (new) | per-run detail, replaces `?run=` selection |

**Verify:** every route navigates via the sidebar; `?run=`-style selection now
works as `/run/:id`; back/forward work; typecheck clean.

### Phase 3 — Port the views (the bulk)
**Goal:** rewrite each view's markup on shadcn primitives + tokens. **Keep the
data hooks and endpoints exactly** (`useApi`/`post`/`useStream` ported unchanged
from `web/src/api.ts`).

Order (smallest/most-contained first, to shake out the primitive set early):
1. **Memory** (70) + **Lineage** (73) — graph/list views; establish the
   `Card`/`Table`/`Badge` patterns and the graph container.
2. **Agents** (106) — state/calls/pass-rate table + per-agent cards.
3. **Dissent** (128) — ledger table + Resurrect/Fork actions (Dialog + Button).
4. **Workspace** (163) — keep the **CodeMirror 6** editor as-is (port the
   `CodeEditor.tsx` + `lang/registry.ts` files verbatim); reskin the surrounding
   file tree + compose-gate panel.
5. **NewRun** (262) — brief → extract fingerprint → start; Dialog/Form on
   `Input`+`Select`+`Button`.
6. **Settings** (452, largest) — providers/models/roles/agents/credits; port the
   OpenRouter searchable dropdown into shadcn `Command`/`Popover`, the local-model
   download panel, and the envelope-key UX.
7. **SpendRail + Topbar live data** — wire `useStream` spend ticks + quota into
   the Topbar rail; the SSE ticker feed into a small activity surface.
8. **Simple mode** — `_shell.index` renders the brief→progress→result+cost/
   verified summary when `ui-store.mode === "simple"`, Board when `expert`.

Per view: port data hook usage verbatim, re-lay-out with primitives, match
DESIGN.md (hairlines, sentence case, no redundant subtext). The CodeMirror editor
and `lang/registry` are copied, not rewritten.

**Verify (per view):** against the live backend, the view shows the same data as
the old one, mutations (New Run, Resurrect, Fork, add model/role/agent) hit the
same endpoints and succeed, SSE ticker + spend still update live. Typecheck clean.

### Phase 4 — Live Kanban (the one net-new feature)
**Goal:** a board that makes run/node state legible the way the reference's
session board does — the piece our six analytical views lack.

Steps:
1. **Lanes** from our own domain facts (not sessions): `Queued → Working →
   Dissent → Verifying → Verified → Superseded`. Map existing node/run status +
   `mode` (`simulated`/`live`) + dissent presence to a lane via a pure
   `lib/board-presentation.ts` (mirrors the reference's `session-presentation.ts`).
2. **Cards** = runs (default) with a drill-in to nodes; each card shows label,
   mode badge (`simulated`/`live`), spend, verified-count, cost-per-verified, and
   a "needs you" flag when a dissent is open. Reuse the reference card layout +
   `--color-status-*` tokens.
3. **Data:** derive client-side from the existing `/api/runs` + per-run nodes
   first (no backend change). Only if the derivation needs data we don't expose,
   add a thin read-only `GET /api/board` in `backend/lineage/api/` that returns
   pre-bucketed lanes. SSE already pushes changes → board re-derives live.
4. Board is `_shell.index` in Expert mode; clicking a card → `/run/:id`.

Files: `.../routes/_shell.index.tsx`, `.../components/{Board,BoardLane,SessionCard}.tsx`,
`.../lib/board-presentation.ts`, (maybe) `backend/lineage/api/queries.py` +
route in `main.py`.

`ponytail:` derive lanes client-side first; add `/api/board` only if the client
can't bucket from data it already fetches.

**Verify:** start two runs; cards appear in the right lanes, move lanes live as
nodes verify / dissents open, mode badges correct, click-through to run detail
works. A small `test_board_presentation` (pure function, assert-based) covers the
status→lane mapping.

### Phase 5 — Typed contracts (the "B" upgrade)
**Goal:** replace the untyped `fetch`/`useApi<T>` guesses with types generated
from the backend's OpenAPI, matching the reference's `api:spec`/`api:ts` scripts.

Steps:
1. FastAPI already produces OpenAPI at `/openapi.json`. Add a backend script
   `python -m lineage.api.export_openapi > ../frontend/openapi.json` (dumps
   `app.openapi()`), wired as `npm run api:spec`.
2. `npm run api:ts`: `openapi-typescript frontend/openapi.json -o
   frontend/src/api/schema.ts`. Combined `npm run api` runs both (same shape as
   the reference's root `package.json`).
3. Introduce a tiny typed client wrapping `fetch` using `schema.ts` `paths`
   types; migrate `useApi`/`post` call sites to it incrementally (types only, no
   runtime change).
4. Add a CI/`npm run check` step: regenerate + `git diff --exit-code` on
   `schema.ts` so the contract can't drift (mirrors the reference `cloud:check`).

Files: `backend/lineage/api/export_openapi.py`, `frontend/src/api/{schema.ts,client.ts}`,
`frontend/package.json` scripts.

**Verify:** `npm run api` regenerates `schema.ts` with no diff on a clean tree;
typecheck passes with the typed client; a deliberately wrong endpoint name fails
`tsc`.

### Phase 6 — Wire compose + clean up
**Goal:** the new frontend is the shipped one; old `web/` is gone; docs updated.

Steps:
1. `frontend/Dockerfile` (multi-stage: `npm ci && npm run build` → nginx static
   serve) + `frontend/nginx.conf` (port 5173, `/api` reverse-proxy to
   `backend:8000`, SPA fallback not needed with hash history — just serve
   `index.html`). Port these from the existing `web/Dockerfile` + `web/nginx.conf`.
2. `compose.yaml`: point the `web` service `build:` at `./frontend` (keep the
   `API_UPSTREAM`/port wiring and the `depends_on: backend healthy` gate). No
   other service changes.
3. Delete `web/` once parity is confirmed.
4. Update `README.md` (layout section, screenshots) and write our adapted
   `DESIGN.md` (graphite tokens, shell, board, our status lanes) using the
   reference's DESIGN.md as the template.

**Verify:** `docker compose up --build` brings up db + backend + frontend;
console on :5173 is the new UI, fully functional end-to-end (the live-demo flow
in the README passes); `grep -rn "ponytail:" backend frontend` lists only the
deliberate stand-ins.

---

## Deliberately NOT doing (ask to add any)
Electron, Go, the xterm embedded terminal, cloud sync, mobile, i18n/translations,
release/packaging workflows, Lexical editor. These are the reference's
*desktop-product* overhead, not its UI identity — add only if we later decide we
need a native desktop app (the separate Option C).
`ponytail:` skipped desktop shell, add when a native terminal/offline binary is
actually required.

## Baked in (required for a faithful copy)
- **Tailwind + shadcn** replace our inline-CSS tokens (shadcn requires Tailwind;
  their whole UI is shadcn).
- **React 18 -> 19** to match their primitives. Low risk at this size.
- **Hash history** (not browser history) — matches the reference and needs no
  nginx SPA-fallback config.
