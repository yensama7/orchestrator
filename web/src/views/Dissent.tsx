import { useState } from "react";
import { useApi } from "../api";
import { Chip, Panel } from "../components";

type Dis = {
  leaderboard: {
    agent: string; model: string; rate: number;
    overruled: number; resurrected: number; vindicated: number; refuted: number; promote: boolean;
  }[];
  ledger: { node: string; dissenter: string; winner: string; stage: number; reason: string; status: string }[];
};

const STATUS_COLOR: Record<string, string> = {
  dormant: "var(--dimmer)", resurrected: "var(--violet)", vindicated: "var(--sage)", refuted: "var(--rust)",
};

export default function Dissent({ run }: { run?: string }) {
  const { data } = useApi<Dis>("dissent", run);
  const [filter, setFilter] = useState<string>("all");
  if (!data) return null;
  const rows = data.ledger.filter((r) => filter === "all" || r.status === filter);

  return (
    <div className="stack">
      <div className="section-title">Vindication leaderboard — the roads not taken, and which were right</div>
      <div className="leaderboard">
        {data.leaderboard.map((a) => (
          <div className="lb-card" key={a.agent}>
            <div className="name">{a.agent}</div>
            <div className="model">{a.model}</div>
            <div className="rate sage">{a.rate}%</div>
            <div className="microbar">
              <span style={{ flex: a.overruled, background: "var(--dimmer)" }} />
              <span style={{ flex: a.resurrected, background: "var(--violet)" }} />
              <span style={{ flex: a.vindicated, background: "var(--sage)" }} />
              <span style={{ flex: a.refuted, background: "var(--rust)" }} />
            </div>
            {a.promote && <div className="promote"><Chip active>promote?</Chip></div>}
          </div>
        ))}
      </div>

      <div className="section-title">The ledger</div>
      <div style={{ display: "flex", gap: 6, marginBottom: 4 }}>
        {["all", "dormant", "resurrected", "vindicated", "refuted"].map((s) => (
          <Chip key={s} active={s === filter} onClick={() => setFilter(s)}>{s}</Chip>
        ))}
      </div>
      <Panel>
        <table className="data">
          <thead>
            <tr><th>Node</th><th>Dissenter</th><th>Winner</th><th>Stage</th><th>Reason</th><th>Status</th><th></th></tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.node + r.dissenter}>
                <td className="mono">{r.node}</td>
                <td className="mono">{r.dissenter}</td>
                <td className="mono dim">{r.winner}</td>
                <td className="mono">{r.stage}</td>
                <td className="dim">{r.reason}</td>
                <td>
                  <span className="state">
                    <span className="dot" style={{ background: STATUS_COLOR[r.status] }} />{r.status}
                  </span>
                </td>
                <td>{r.status === "dormant" && <button className="btn ghost" style={{ padding: "2px 8px" }}>Resurrect</button>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Panel>
    </div>
  );
}
