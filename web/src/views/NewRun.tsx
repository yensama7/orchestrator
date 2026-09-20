import { Fragment, useState } from "react";
import { Chip, Panel, Row } from "../components";

// §19.3 — six numbered step cards, one column, completed steps collapse.
const STEPS = ["Brief", "Fingerprint", "Lineage match", "Roster", "Budget", "Plan review"];

// placeholder example shown before a real extraction returns
const FINGERPRINT: [string, string][] = [
  ["domain", "commerce"], ["subdomain", "storefront"], ["stack_hints", "nextjs, postgres"],
  ["payments", "paystack"], ["auth", "required"], ["multi_tenant", "false"], ["region", "NG"],
];

type Fp = Record<string, unknown>;
type Match = {
  nearest: { name: string; score: number; outcome: string }[];
  inherited: { template: string; status: string; rows: { label: string; n: string; color?: string }[] } | null;
};
type RosterRow = {
  role: string; model: string; transport: string; consensus: string;
  pass_rate: number | null; vindication_rate: number | null; available: boolean;
};
type Node = {
  id: string; role: string; intent: string; irreversible: boolean;
  budget_usd: number; constraints: string[]; depends_on: string[];
};
type Plan = { nodes: Node[] };

const LIST_FIELDS = new Set(["stack_hints", "compliance"]);

// the kv grid stringifies everything; put the real types back before the API
// validates them (SpecFingerprint wants list/bool, not comma-strings).
function normalizeFp(raw: Fp): Fp {
  const out: Fp = { ...raw };
  for (const f of LIST_FIELDS) {
    if (typeof out[f] === "string") out[f] = (out[f] as string).split(",").map((s) => s.trim()).filter(Boolean);
  }
  if (typeof out.multi_tenant === "string") out.multi_tenant = out.multi_tenant === "true";
  return out;
}

async function postJson<T>(url: string, body: unknown): Promise<T> {
  const r = await fetch(url, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) });
  return r.json();
}

export default function NewRun({ onDone }: { onDone: () => void }) {
  const [step, setStep] = useState(0);
  const [brief, setBrief] = useState("");
  const [ceiling, setCeiling] = useState(15);
  const [fp, setFp] = useState<Fp | null>(null);
  const [match, setMatch] = useState<Match | null>(null);
  const [roster, setRoster] = useState<RosterRow[] | null>(null);
  const [plan, setPlan] = useState<Plan | null>(null);
  const [busy, setBusy] = useState(false);

  const body = () => ({ fingerprint: normalizeFp(fp ?? {}), budget: ceiling });

  const extract = async () => {
    setBusy(true);
    try {
      setFp(await postJson<Fp>("/api/extract", { brief }));
      setStep(1);
    } finally { setBusy(false); }
  };

  // step 1 → 2: fingerprint is confirmed, so match lineage + propose a roster
  const findSimilar = async () => {
    setBusy(true);
    try {
      const [m, r] = await Promise.all([
        postJson<Match>("/api/match", body()),
        postJson<RosterRow[]>("/api/roster", body()),
      ]);
      setMatch(m); setRoster(r); setStep(2);
    } finally { setBusy(false); }
  };

  // step 4 → 5: build the real DAG at the chosen ceiling
  const reviewPlan = async () => {
    setBusy(true);
    try {
      setPlan(await postJson<Plan>("/api/plan", body()));
      setStep(5);
    } finally { setBusy(false); }
  };

  const startRun = async () => {
    setBusy(true);
    try {
      await postJson("/api/runs/run%2F4f2a9c/start", { fingerprint: normalizeFp(fp ?? {}), ceiling });
    } finally { setBusy(false); }
    onDone();
  };

  const fpRows: [string, string][] = fp
    ? Object.entries(fp)
        .filter(([, v]) => typeof v !== "object" || v === null || Array.isArray(v))
        .map(([k, v]) => [k, Array.isArray(v) ? v.join(", ") : String(v ?? "")])
    : FINGERPRINT;

  return (
    <div className="wizard">
      {STEPS.map((label, i) => (
        <Panel pad key={label} className={i > step ? "step future" : "step"}>
          <div className="panel-h">
            <span className="num">{i + 1}</span>
            <h3>{label}</h3>
            {i < step && <button className="step-summary edit" onClick={() => setStep(i)}>Edit</button>}
          </div>

          {i === step && (
            <div>
              {i === 0 && (
                <>
                  <textarea rows={5} value={brief} onChange={(e) => setBrief(e.target.value)}
                    placeholder="Build a storefront for a Nigerian fashion label, Paystack checkout, admin dashboard, ~2k SKUs." />
                  <div style={{ marginTop: 10 }}>
                    <button className="btn primary" disabled={!brief.trim() || busy} onClick={extract}>
                      {busy ? "Extracting…" : "Extract fingerprint"}
                    </button>
                  </div>
                </>
              )}

              {i === 1 && (
                <>
                  <div className="kv">
                    {fpRows.map(([k, v]) => (
                      <Fragment key={k}><label>{k}</label>
                        <input value={v} onChange={(e) => setFp((prev) => ({ ...(prev ?? {}), [k]: e.target.value }))} />
                      </Fragment>
                    ))}
                  </div>
                  <div style={{ marginTop: 12, display: "flex", gap: 8 }}>
                    <button className="btn ghost" disabled={busy} onClick={() => { setStep(0); extract(); }}>Re-extract</button>
                    <button className="btn primary" disabled={busy} onClick={findSimilar}>
                      {busy ? "Matching…" : "Find similar work"}
                    </button>
                  </div>
                </>
              )}

              {i === 2 && (
                <>
                  {match?.nearest.length
                    ? match.nearest.map((r) => <Row key={r.name} color={r.outcome} label={r.name} n={r.score.toFixed(2)} />)
                    : <p className="hint">No prior runs to match against yet — this will be the first in its neighbourhood.</p>}
                  {match?.inherited && (
                    <div className="panel pad" style={{ marginTop: 12 }}>
                      <div className="panel-h"><h3>{match.inherited.template}</h3><Chip active>{match.inherited.status}</Chip></div>
                      <p className="hint">
                        {match.inherited.rows.map((row, k) => (
                          <span key={row.label} className={row.color}>{k ? " · " : ""}{row.n} {row.label.toLowerCase()}</span>
                        ))}
                      </p>
                    </div>
                  )}
                  <div style={{ marginTop: 12, display: "flex", gap: 8 }}>
                    <button className="btn primary" onClick={() => setStep(3)}>
                      {match?.inherited ? "Use this template" : "Start clean"}
                    </button>
                  </div>
                </>
              )}

              {i === 3 && (
                <>
                  <Panel>
                    <table className="data">
                      <thead><tr><th>Role</th><th>Model</th><th>Transport</th><th>Consensus</th><th>Pass</th><th>Vind.</th></tr></thead>
                      <tbody>
                        {(roster ?? []).map((r) => (
                          <tr key={r.role} style={r.available ? undefined : { opacity: 0.5 }}>
                            <td className="mono">{r.role}</td>
                            <td className="mono dim">{r.model ?? "— unassigned"}</td>
                            <td className="mono">{r.transport}</td>
                            <td className="dim">{r.consensus}</td>
                            <td className="mono">{r.pass_rate != null ? `${Math.round(r.pass_rate * 100)}%` : "—"}</td>
                            <td className="mono">{r.vindication_rate != null ? `${Math.round(r.vindication_rate * 100)}%` : "—"}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </Panel>
                  <div style={{ marginTop: 12, display: "flex", gap: 8 }}>
                    <button className="btn primary" onClick={() => setStep(4)}>Continue</button>
                  </div>
                </>
              )}

              {i === 4 && (
                <>
                  <div className="metric"><span className="lbl">Ceiling</span>
                    <div className="val amber">${ceiling.toFixed(2)}</div></div>
                  <input className="slider" type="range" min={2} max={40} step={0.5}
                    value={ceiling} onChange={(e) => setCeiling(+e.target.value)} />
                  <p className="hint">
                    Budget is split evenly across DAG nodes — projected spend at this ceiling is{" "}
                    <span className="amber">${ceiling.toFixed(2)}</span>.
                  </p>
                  <button className="btn primary" style={{ marginTop: 12 }} disabled={busy} onClick={reviewPlan}>
                    {busy ? "Planning…" : "Review plan"}
                  </button>
                </>
              )}

              {i === 5 && (
                <>
                  {(() => {
                    const nodes = plan?.nodes ?? [];
                    const withPitfall = nodes.filter((n) => n.constraints.length).length;
                    return (
                      <>
                        <p className="hint">
                          DAG · {nodes.length} nodes. Irreversible nodes get consensus;
                          {withPitfall ? <> <span className="rust">{withPitfall}</span> carry an inherited pitfall constraint.</> : " no inherited pitfalls."}
                        </p>
                        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", margin: "10px 0" }}>
                          {nodes.map((n) => (
                            <span key={n.id} className="chip" title={`${n.role} · $${n.budget_usd.toFixed(2)}${n.constraints.length ? ` · ${n.constraints.length} pitfall(s)` : ""}`}
                              style={n.constraints.length ? { borderColor: "var(--rust)", color: "var(--rust)" }
                                : n.irreversible ? { borderColor: "var(--amber)", color: "var(--amber)" } : undefined}>
                              {n.id}
                            </span>
                          ))}
                        </div>
                      </>
                    );
                  })()}
                  <div style={{ display: "flex", gap: 8 }}>
                    <button className="btn primary" disabled={busy} onClick={startRun}>
                      {busy ? "Starting…" : "Start run"}
                    </button>
                    <button className="btn ghost" onClick={() => setStep(4)}>Send back</button>
                  </div>
                </>
              )}
            </div>
          )}

          {i < step && <div className="step-summary">{summary(i, brief, ceiling, fp, roster, plan)}</div>}
        </Panel>
      ))}
    </div>
  );
}

function summary(i: number, brief: string, ceiling: number, fp: Fp | null, roster: RosterRow[] | null, plan: Plan | null) {
  switch (i) {
    case 0: return brief.slice(0, 60) + (brief.length > 60 ? "…" : "");
    case 1: {
      if (!fp) return "—";
      return [fp.domain, fp.subdomain, fp.region, fp.payments].filter(Boolean).map(String).join(" / ") || "—";
    }
    case 2: return "lineage matched";
    case 3: return roster ? `${roster.length} roles assigned` : "roster proposed";
    case 4: return `ceiling $${ceiling.toFixed(2)}${plan ? ` · ${plan.nodes.length} nodes` : ""}`;
    default: return "";
  }
}
