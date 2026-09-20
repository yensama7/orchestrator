import { useApi } from "../api";
import { Donut, EmptyState, LineChart, Panel, PanelHeader, Slice } from "../components";
import { TipLine } from "../hover";

type Agent = {
  agent: string; role: string; model: string; state: string;
  calls: number; tokens: string; cached: string; cost: string; pass: string; vind: string;
};
type Charts = {
  token_attr: Slice[]; cost_share: Slice[]; verification: Slice[];
  spend_series: Record<string, number>[]; throughput: Record<string, number>[];
};

const STATE_COLOR: Record<string, string> = { running: "var(--sage)", waiting: "var(--amber)", idle: "var(--dimmer)" };

export default function Agents() {
  const { data } = useApi<Agent[]>("agents");
  const { data: charts } = useApi<Charts>("charts");
  if (!data) return null;

  if (!data.length) {
    return (
      <Panel pad>
        <EmptyState message="No agents yet. Add models and assign roles in Settings, then start a run."
          action={<span className="hint">Settings → Add model → Add agent</span>} />
      </Panel>
    );
  }

  // spend chart footer: the computed saved figure (prompt_hover.md Task 4).
  const savedFooter = (row: Record<string, number>): TipLine[] => {
    const saved = (row.uncached ?? 0) - (row.actual ?? 0);
    const pct = row.uncached ? Math.round((saved / row.uncached) * 100) : 0;
    return [{ text: `saved  $${saved.toFixed(2)}  (${pct}%)`, mono: true, color: "var(--sage)" }];
  };

  return (
    <div className="stack">
      <Panel>
        <table className="data">
          <thead>
            <tr>
              <th>Agent</th><th>Role</th><th>Model</th><th>State</th>
              <th>Calls</th><th>Tokens</th><th>Cached</th><th>Cost</th><th>Pass</th><th>Vind</th>
            </tr>
          </thead>
          <tbody>
            {data.map((a) => (
              <tr key={a.agent}>
                <td className="mono">{a.agent}</td>
                <td className="role">{a.role}</td>
                <td className="mono dim">{a.model}</td>
                <td><span className="state"><span className="dot" style={{ background: STATE_COLOR[a.state] }} />{a.state}</span></td>
                <td className="mono">{a.calls}</td>
                <td className="mono">{a.tokens}</td>
                <td className="mono dim">{a.cached}</td>
                <td className="mono amber">{a.cost}</td>
                <td className="mono">{a.pass}</td>
                <td className="mono violet">{a.vind}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Panel>

      {charts && (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 14 }}>
          <ChartCard title="Cumulative spend" hint="against the uncached counterfactual">
            {charts.spend_series.length
              ? <LineChart data={charts.spend_series} series={[
                  { key: "actual", label: "actual", color: "amber" },
                  { key: "uncached", label: "uncached", color: "rust" }]} footer={savedFooter} />
              : <Empty />}
          </ChartCard>
          <ChartCard title="Throughput" hint="nodes completed over time">
            {charts.throughput.length
              ? <LineChart data={charts.throughput} series={[{ key: "nodes", label: "nodes", color: "violet" }]} />
              : <Empty />}
          </ChartCard>
          <ChartCard title="Token attribution" hint="what filled the context window">
            {charts.token_attr.length ? <Donut slices={charts.token_attr} centerLabel="tokens" /> : <Empty />}
          </ChartCard>
          <ChartCard title="Cost share" hint="by agent — differs from token share">
            {charts.cost_share.length ? <Donut slices={charts.cost_share} centerLabel="spend" /> : <Empty />}
          </ChartCard>
          <ChartCard title="Verification" hint="nodes by outcome">
            {charts.verification.some((s) => s.value) ? <Donut slices={charts.verification} centerLabel="nodes" /> : <Empty />}
          </ChartCard>
        </div>
      )}
    </div>
  );
}

function ChartCard({ title, hint, children }: { title: string; hint: string; children: React.ReactNode }) {
  return (
    <Panel pad>
      <PanelHeader title={title} />
      <p className="hint" style={{ marginTop: -6, marginBottom: 10 }}>{hint}</p>
      <div style={{ display: "flex", justifyContent: "center", minHeight: 130, alignItems: "center" }}>{children}</div>
    </Panel>
  );
}

const Empty = () => <span className="hint">no data yet</span>;
