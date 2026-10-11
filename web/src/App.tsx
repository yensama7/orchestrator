import { useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useApi, useStream } from "./api";
import { COLOR } from "./components";
import NewRun from "./views/NewRun";
import Lineage from "./views/Lineage";
import Memory from "./views/Memory";
import Agents from "./views/Agents";
import Dissent from "./views/Dissent";
import Workspace from "./views/Workspace";
import SettingsView from "./views/Settings";
import SimpleRun from "./views/SimpleRun";

type RunData = {
  id: string; label: string; spec: string; template: string; mode: string;
  status: string; spent: number; verified_count: number; cost_per_verified: number | null;
  projected: number; ceiling: number;
  rail: { label: string; usd: number; color: string }[];
  cache_note: string;
  navfoot: { egress: string; agents: string; blocked: string };
};
type RunsList = {
  current: string;
  runs: { id: string; name: string; status: string; mode: string; spent: number; current: boolean }[];
};

const VIEWS = [
  { key: "newrun", label: "New run", ico: "+" },
  { key: "lineage", label: "Lineage", ico: "⑂" },
  { key: "memory", label: "Memory", ico: "▤" },
  { key: "agents", label: "Agents", ico: "⚇" },
  { key: "dissent", label: "Dissent", ico: "⚖" },
  { key: "workspace", label: "Workspace", ico: "⌗" },
  { key: "settings", label: "Settings", ico: "⚙" },
] as const;

export default function App() {
  const qc = useQueryClient();
  // §P5 progressive disclosure: Simple is the default; Expert opts into the full
  // console. One codebase — Expert just unhides the rail + machinery views.
  const [ui, setUi] = useState<"simple" | "expert">(
    () => (localStorage.getItem("ui") === "expert" ? "expert" : "simple"));
  const setUiMode = (m: "simple" | "expert") => { localStorage.setItem("ui", m); setUi(m); };
  const [view, setView] = useState<string>("lineage");
  // null = follow the server's current run; a uuid = view that specific run.
  const [selectedRun, setSelectedRun] = useState<string | null>(null);
  const { data: run } = useApi<RunData>("run", selectedRun ?? undefined);
  const { data: runs } = useApi<RunsList>("runs");
  const { events, spent, stale } = useStream(run?.id ?? "current");
  const liveSpent = spent ?? run?.spent ?? 0;

  // §P4d: each SSE delta (a new ticker line or a spend tick) invalidates the
  // read queries so the open views refetch on real change — this is what lets
  // polling stay off while the stream is healthy.
  useEffect(() => { qc.invalidateQueries(); }, [events.length, spent, qc]);

  // after a New Run (or a fork) starts, that run becomes server-current — follow
  // it and refresh.
  const afterNewRun = () => {
    setSelectedRun(null);
    qc.invalidateQueries();
    setView("lineage");
  };

  const simple = ui === "simple";

  return (
    <div className={"shell" + (simple ? " simple-ui" : "")}>
      <Header run={run} runs={runs} selectedRun={selectedRun} onSelectRun={setSelectedRun}
              spent={liveSpent} stale={stale} onNewRun={() => setView("newrun")}
              ui={ui} onUi={setUiMode} />

      {!simple && (
        <nav className="nav">
          {VIEWS.map((v) => (
            <button key={v.key} className={"nav-item" + (view === v.key ? " active" : "")}
                    onClick={() => setView(v.key)}>
              <span className="ico" aria-hidden>{v.ico}</span> {v.label}
            </button>
          ))}
          <div className="navfoot">
            <div>{run?.navfoot.egress}</div>
            <div>{run?.navfoot.agents}</div>
            <div>{run?.navfoot.blocked}</div>
          </div>
        </nav>
      )}

      <main className={"stage" + (!simple && view === "workspace" ? " flush" : "")}>
        {simple ? (
          <SimpleRun run={run} events={events} onStarted={afterNewRun} />
        ) : (
          <>
            {view === "newrun" && <NewRun onDone={afterNewRun} />}
            {view === "lineage" && <Lineage run={run?.id} />}
            {view === "memory" && <Memory run={run?.id} />}
            {view === "agents" && <Agents run={run?.id} />}
            {view === "dissent" && <Dissent run={run?.id} onForked={afterNewRun} />}
            {view === "workspace" && <Workspace run={run?.id} />}
            {view === "settings" && <SettingsView />}
          </>
        )}
      </main>

      <footer className="ticker" style={stale ? { opacity: 0.6 } : undefined}>
        <span className="pulse" />
        {stale && <span className="ev"><span className="k">reconnecting</span></span>}
        {events.map((e, i) => (
          <span className="ev" key={i}><span className="k">{e.key}</span>{e.text}</span>
        ))}
      </footer>
    </div>
  );
}

function Header({ run, runs, selectedRun, onSelectRun, spent, stale, onNewRun, ui, onUi }: {
  run?: RunData; runs?: RunsList; selectedRun: string | null;
  onSelectRun: (id: string | null) => void;
  spent: number; stale: boolean; onNewRun: () => void;
  ui: "simple" | "expert"; onUi: (m: "simple" | "expert") => void;
}) {
  return (
    <header className="header" style={stale ? { opacity: 0.6 } : undefined}>
      <div className="row1">
        <span className="wordmark">lineage<span className="tick">·</span>orchestrator</span>
        <div className="ui-toggle" role="group" aria-label="interface mode">
          <button className={ui === "simple" ? "on" : ""} onClick={() => onUi("simple")}>Simple</button>
          <button className={ui === "expert" ? "on" : ""} onClick={() => onUi("expert")}>Expert</button>
        </div>
        {runs && runs.runs.length > 0 ? (
          <select className="runid" value={selectedRun ?? runs.current}
            onChange={(e) => onSelectRun(e.target.value === runs.current ? null : e.target.value)}
            title="Switch run">
            {runs.runs.map((r) => (
              <option key={r.id} value={r.id}>
                {r.name} · {r.status} · {r.mode}{r.current ? " · current" : ""}
              </option>
            ))}
          </select>
        ) : <span className="runid">{run?.label}</span>}
        {run?.mode && <ModeBadge mode={run.mode} />}
        <span className="spec">
          {run?.spec} · inherited from <a href="#">{run?.template}</a>
        </span>
        {ui === "expert" && <button className="newrun-btn" onClick={onNewRun}>+ New run</button>}
        <div className="spend-nums">
          <span className="amber">${spent.toFixed(2)}<span className="lbl">spent</span></span>
          <span className="dim">${run?.projected.toFixed(2)}<span className="lbl">projected</span></span>
          <span className="dimmer">${run?.ceiling.toFixed(2)}<span className="lbl">ceiling</span></span>
        </div>
      </div>

      <div className="rail-bar">
        {run?.rail.map((r) => (
          <div key={r.label} className="rail-seg"
               style={{ flex: r.usd, background: COLOR[r.color] ?? r.color }}
               title={`${r.label} $${r.usd.toFixed(2)}`} />
        ))}
      </div>
      <div className="rail-key">
        {run?.rail.map((r) => (
          <span className="item" key={r.label}>
            <span className="swatch" style={{ background: COLOR[r.color] ?? r.color }} />
            {r.label} ${r.usd.toFixed(2)}
          </span>
        ))}
        <span className="cache">{run?.cache_note}</span>
      </div>
    </header>
  );
}

// §P0 truth-in-labeling: every chart/number on screen belongs to a run; this
// badge tells a reviewer at a glance whether it's a verified (live) outcome or a
// simulated one (echo stubs + structural verifiers). Until Phase 1, always sim.
function ModeBadge({ mode }: { mode: string }) {
  const live = mode === "live";
  return (
    <span className={"mode-badge" + (live ? " live" : " simulated")}
          title={live
            ? "live — real model + behavioral verifier; counts toward scoring/benchmarks"
            : "simulated — echo stub and/or structural verifiers only; not a verified outcome"}>
      {live ? "live" : "simulated"}
    </span>
  );
}
