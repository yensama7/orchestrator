import { useState } from "react";
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

type RunData = {
  id: string; label: string; spec: string; template: string;
  spent: number; projected: number; ceiling: number;
  rail: { label: string; usd: number; color: string }[];
  cache_note: string;
  navfoot: { egress: string; agents: string; blocked: string };
};
type RunsList = {
  current: string;
  runs: { id: string; name: string; status: string; spent: number; current: boolean }[];
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
  const [view, setView] = useState<string>("lineage");
  // null = follow the server's current run; a uuid = view that specific run.
  const [selectedRun, setSelectedRun] = useState<string | null>(null);
  const { data: run } = useApi<RunData>("run", selectedRun ?? undefined);
  const { data: runs } = useApi<RunsList>("runs");
  const { events, spent, stale } = useStream(run?.id ?? "current");
  const liveSpent = spent ?? run?.spent ?? 0;

  // after a New Run starts, that run becomes server-current — follow it and refresh.
  const afterNewRun = () => {
    setSelectedRun(null);
    qc.invalidateQueries();
    setView("lineage");
  };

  return (
    <div className="shell">
      <Header run={run} runs={runs} selectedRun={selectedRun} onSelectRun={setSelectedRun}
              spent={liveSpent} stale={stale} onNewRun={() => setView("newrun")} />

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

      <main className={"stage" + (view === "workspace" ? " flush" : "")}>
        {view === "newrun" && <NewRun onDone={afterNewRun} />}
        {view === "lineage" && <Lineage run={run?.id} />}
        {view === "memory" && <Memory run={run?.id} />}
        {view === "agents" && <Agents run={run?.id} />}
        {view === "dissent" && <Dissent run={run?.id} />}
        {view === "workspace" && <Workspace run={run?.id} />}
        {view === "settings" && <SettingsView />}
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

function Header({ run, runs, selectedRun, onSelectRun, spent, stale, onNewRun }: {
  run?: RunData; runs?: RunsList; selectedRun: string | null;
  onSelectRun: (id: string | null) => void;
  spent: number; stale: boolean; onNewRun: () => void;
}) {
  const total = run ? run.rail.reduce((s, r) => s + r.usd, 0) : 1;
  return (
    <header className="header" style={stale ? { opacity: 0.6 } : undefined}>
      <div className="row1">
        <span className="wordmark">lineage<span className="tick">·</span>orchestrator</span>
        {runs && runs.runs.length > 0 ? (
          <select className="runid" value={selectedRun ?? runs.current}
            onChange={(e) => onSelectRun(e.target.value === runs.current ? null : e.target.value)}
            title="Switch run">
            {runs.runs.map((r) => (
              <option key={r.id} value={r.id}>
                {r.name} · {r.status}{r.current ? " · current" : ""}
              </option>
            ))}
          </select>
        ) : <span className="runid">{run?.label}</span>}
        <span className="spec">
          {run?.spec} · inherited from <a href="#">{run?.template}</a>
        </span>
        <button className="newrun-btn" onClick={onNewRun}>+ New run</button>
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
