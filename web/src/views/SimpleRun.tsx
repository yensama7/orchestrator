import { useState } from "react";
import { post, TickerEvent } from "../api";
import { Panel } from "../components";

// §P5 Simple UI: brief in → progress → result + cost-per-verified-result out.
// Progressive disclosure, not a second codebase — Expert reuses the same APIs and
// the same run. This view hides the DAG / lineage / dissent machinery behind one
// textarea and one result card.

type Run = {
  id: string; spec: string; mode: string; status: string;
  spent: number; verified_count: number; cost_per_verified: number | null;
};

const ACTIVE = (s?: string) => s === "active";

export default function SimpleRun({ run, events, onStarted }: {
  run?: Run; events: TickerEvent[]; onStarted: () => void;
}) {
  const [brief, setBrief] = useState("");
  const [busy, setBusy] = useState(false);

  const build = async () => {
    setBusy(true);
    try {
      // one step: fingerprint the brief, then start a fresh run on it.
      const fp = await post<Record<string, unknown>>("/api/extract", { brief });
      const name = String(fp.subdomain || fp.domain || "untitled run");
      await post("/api/runs/new/start", { fingerprint: fp, ceiling: 15, name });
      onStarted();
    } finally { setBusy(false); }
  };

  const running = ACTIVE(run?.status);
  const cpv = run?.cost_per_verified;

  return (
    <div className="simple">
      <Panel pad>
        <div className="panel-h"><h3>Build from a brief</h3></div>
        <textarea rows={4} value={brief} disabled={busy || running}
          onChange={(e) => setBrief(e.target.value)}
          placeholder="Describe what to build — e.g. a CLI that converts CSV to JSON, with tests." />
        <div style={{ marginTop: 10 }}>
          <button className="btn primary" disabled={!brief.trim() || busy || running} onClick={build}>
            {busy ? "Starting…" : running ? "Run in progress…" : "Build"}
          </button>
          {running && <span className="hint" style={{ marginLeft: 10 }}>a run is live — watch it below</span>}
        </div>
      </Panel>

      {run && run.id !== "—" && (
        <Panel pad className="result">
          <div className="panel-h">
            <h3>{run.spec}</h3>
            <ModeBadge mode={run.mode} />
            <span className={"status-pill " + (run.status || "")}>{run.status}</span>
          </div>
          <div className="result-metrics">
            <Metric label="cost / verified result"
                    value={cpv != null ? `$${cpv.toFixed(2)}` : "—"} big />
            <Metric label="verified nodes" value={String(run.verified_count)} />
            <Metric label="spent" value={`$${run.spent.toFixed(2)}`} />
          </div>
          {cpv == null && (
            <p className="hint">
              Nothing verified yet{running ? " — the run is still going." : "."} A result counts
              only when a check that <em>executes the produced code</em> passes.
            </p>
          )}
          <div className="progress-log">
            {events.slice(0, 8).map((e, i) => (
              <div key={i} className="line"><span className="k">{e.key}</span>{e.text}</div>
            ))}
            {events.length === 0 && <div className="line hint">no activity yet</div>}
          </div>
        </Panel>
      )}
    </div>
  );
}

function Metric({ label, value, big }: { label: string; value: string; big?: boolean }) {
  return (
    <div className="metric">
      <span className="lbl">{label}</span>
      <div className={"val" + (big ? " amber" : "")} style={big ? { fontSize: 26 } : undefined}>{value}</div>
    </div>
  );
}

// mirrors App's badge: live = real model + behavioral verifier; simulated otherwise.
function ModeBadge({ mode }: { mode: string }) {
  const live = mode === "live";
  return <span className={"mode-badge" + (live ? " live" : " simulated")}>{live ? "live" : "simulated"}</span>;
}
