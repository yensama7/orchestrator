import { useState } from "react";
import { useApi } from "../api";
import { Chip, EmptyState, Legend, Panel, PanelHeader, Pt, Row, Scatter, spread } from "../components";

type Lin = {
  points: (Pt & { kind: string })[];
  edges: [string, string][];
  nearest: { name: string; score: number; outcome: string }[];
  inherited: { template: string; status: string; rows: { label: string; n: string; color?: string }[] } | null;
  domains: string[];
};

export default function Lineage() {
  const { data } = useApi<Lin>("lineage");
  const [domain, setDomain] = useState("all domains");
  if (!data) return null;

  // filtered-out run nodes render dimmed as context (not hittable); templates always shown.
  // spread() fans out stacked points so the graph stays legible as runs accumulate.
  const points: Pt[] = spread(data.points.map((p) => ({
    ...p,
    dimmed: p.kind === "run" && domain !== "all domains" && p.domain !== domain,
  })));
  const runCount = data.points.filter((p) => p.kind === "run").length;

  return (
    <div className="grid-2">
      {data.points.length ? (
        <div className="stack" style={{ gap: 8 }}>
          <Scatter points={points} edges={data.edges} />
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
            <Legend items={[
              { color: "sage", label: "passed" }, { color: "amber", label: "active" },
              { color: "rust", label: "failed" }, { color: "violet", label: "template" },
            ]} />
            <span className="hint">{runCount} run{runCount === 1 ? "" : "s"}</span>
          </div>
        </div>
      ) : (
        <Panel pad><EmptyState message="No runs yet. Start one from New run to populate the lineage graph." /></Panel>
      )}

      <div className="stack">
        <Panel pad>
          <PanelHeader title="Nearest past work" help="Matched on spec fingerprint, not prose similarity." />
          {data.nearest.length
            ? data.nearest.map((r) => <Row key={r.name} color={r.outcome} label={r.name} n={r.score.toFixed(2)} />)
            : <p className="hint">no comparable runs yet</p>}
        </Panel>

        {data.inherited && (
          <Panel pad>
            <PanelHeader title={`Inherited from ${data.inherited.template}`}
                         help="What the template contributed before any model was called." />
            {data.inherited.rows.map((r) => (
              <Row key={r.label} label={<span className={r.color}>{r.label}</span>} n={r.n} />
            ))}
          </Panel>
        )}

        <Panel pad>
          <PanelHeader title="Show" />
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
            {data.domains.map((d) => (
              <Chip key={d} active={d === domain} onClick={() => setDomain(d)}>{d}</Chip>
            ))}
          </div>
          <p className="hint" style={{ marginTop: 8 }}>Hover a node to trace its inheritance edges.</p>
        </Panel>
      </div>
    </div>
  );
}
