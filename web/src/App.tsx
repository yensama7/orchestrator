import { useState } from "react";
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
  id: string; spec: string; template: string;
  spent: number; projected: number; ceiling: number;
  rail: { label: string; usd: number; color: string }[];
  cache_note: string;
  navfoot: { egress: string; agents: string; blocked: string };
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
  const [view, setView] = useState<string>("lineage");
  const { data: run } = useApi<RunData>("run");
  const { events, spent, stale } = useStream(run?.id ?? "run/4f2a9c");
  const liveSpent = spent ?? run?.spent ?? 0;

  return (
    <div className="shell">
      <Header run={run} spent={liveSpent} stale={stale} onNewRun={() => setView("newrun")} />

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
        {view === "newrun" && <NewRun onDone={() => setView("lineage")} />}
        {view === "lineage" && <Lineage />}
        {view === "memory" && <Memory />}
        {view === "agents" && <Agents />}
        {view === "dissent" && <Dissent />}
        {view === "workspace" && <Workspace />}
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

function Header({ run, spent, stale, onNewRun }: {
  run?: RunData; spent: number; stale: boolean; onNewRun: () => void;
}) {
  const total = run ? run.rail.reduce((s, r) => s + r.usd, 0) : 1;
  return (
    <header className="header" style={stale ? { opacity: 0.6 } : undefined}>
      <div className="row1">
        <span className="wordmark">lineage<span className="tick">·</span>orchestrator</span>
        <span className="runid">{run?.id}</span>
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
