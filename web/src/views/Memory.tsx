import { useState } from "react";
import { useApi } from "../api";
import { EmptyState, HEX, Panel, PanelHeader, Pt, Row, Scatter } from "../components";

type Mem = {
  tiers: { key: string; n: number; color: string; lines: string[] }[];
  recall: { label: string; n: number; color: string }[];
  quality: { label: string; n: string }[];
  points: Pt[];
};

const BLURB: Record<string, string> = {
  episodic: "What happened, in order, never edited. Powers replay and audit.",
  semantic: "What the project knows now, distilled from the diary. This is what agents retrieve.",
  procedural: "How to build things — the agent stack, the order, the known traps.",
};

export default function Memory() {
  const { data } = useApi<Mem>("memory");
  const [filter, setFilter] = useState<string | null>(null);
  if (!data) return null;

  // semantic points coloured by status; subject filter dims the rest.
  const points: Pt[] = data.points.map((p) => ({
    ...p, dimmed: !!filter && p.meta?.subject !== filter,
  }));

  return (
    <div className="stack">
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 14 }}>
        {data.tiers.map((t) => (
          <div key={t.key} className="panel pad" style={{ cursor: "pointer", borderTop: `2px solid ${HEX[t.color]}` }}
               onClick={() => setFilter(null)}>
            <div className="panel-h">
              <span className="dot" style={{ background: HEX[t.color] }} />
              <h3 style={{ textTransform: "capitalize" }}>{t.key}</h3>
              <span className="n" style={{ marginLeft: "auto" }}>{t.n.toLocaleString()}</span>
            </div>
            <p className="hint" style={{ marginBottom: 10 }}>{BLURB[t.key]}</p>
            <pre className="mono" style={{ fontSize: 11.5, color: "var(--dim)", margin: 0, whiteSpace: "pre-wrap" }}>
              {t.lines.join("\n")}
            </pre>
          </div>
        ))}
      </div>

      <div className="grid-2">
        {data.points.length ? (
          <Scatter points={points} height={430} onCommit={(id) => {
            const p = data.points.find((x) => x.id === id);
            setFilter(p?.meta?.subject ?? null);
          }} />
        ) : (
          <Panel pad><EmptyState message="No decisions recorded yet. Run something to populate memory." /></Panel>
        )}
        <div className="stack">
          <Panel pad>
            <PanelHeader title="Row-level recall"
                         help="Individual memory rows for this run — open when an agent does something you can't explain." />
            {data.recall.map((r) => <Row key={r.label} color={r.color} label={r.label} n={r.n.toLocaleString()} />)}
          </Panel>
          <Panel pad>
            <PanelHeader title="Retrieval quality" />
            {data.quality.map((q) => <Row key={q.label} label={q.label} n={q.n} />)}
          </Panel>
        </div>
      </div>
    </div>
  );
}
