import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useApi } from "../api";
import { Chip, Panel, PanelHeader } from "../components";

type Catalog = {
  providers: { provider: string; key_env: string | null; cli?: string;
               models: { id: string; label: string; transports: string[] }[] }[];
  roles: string[];
};
type Settings = {
  credentials: { model: string; transport: string; enabled: boolean; has_key: boolean; key_hint: string }[];
  agents: { agent: string; role: string; model: string; transport: string; enabled: boolean }[];
};

type TestResult = { tested: boolean; working?: boolean; detail?: string };

async function post(url: string, body?: unknown): Promise<any> {
  const r = await fetch(url, { method: "POST", headers: { "content-type": "application/json" }, body: body ? JSON.stringify(body) : undefined });
  return r.json().catch(() => ({}));
}
async function del(url: string) { await fetch(url, { method: "DELETE" }); }

export default function SettingsView() {
  const qc = useQueryClient();
  const { data: cat } = useApi<Catalog>("catalog");
  const { data: st } = useApi<Settings>("settings");
  const refresh = () => { qc.invalidateQueries({ queryKey: ["settings"] }); qc.invalidateQueries({ queryKey: ["agents"] }); };
  if (!cat || !st) return null;

  const configured = new Set(st.credentials.map((c) => c.model));

  return (
    <div className="stack" style={{ maxWidth: 900, margin: "0 auto" }}>
      <h2 className="view-title">Settings</h2>

      {/* ── models + keys ── */}
      <Panel pad>
        <PanelHeader title="Models" help="Add a model and its API key, or pick subscription/local transport. Configured models can be assigned to agents below." />
        {cat.providers.map((p) => (
          <div key={p.provider} style={{ marginBottom: 16 }}>
            <div className="section-title" style={{ margin: "6px 0" }}>
              {p.provider}{p.key_env && <span className="hint" style={{ marginLeft: 8 }}>{p.key_env}</span>}
            </div>
            {p.models.map((m) => (
              <ModelRow key={m.id} m={m} configured={configured.has(m.id)}
                onSaved={refresh} />
            ))}
          </div>
        ))}
      </Panel>

      {/* ── configured credentials ── */}
      <Panel pad>
        <PanelHeader title="Configured models" />
        {st.credentials.length ? (
          <table className="data">
            <thead><tr><th>Model</th><th>Transport</th><th>Key</th><th>Enabled</th><th>Status</th><th></th></tr></thead>
            <tbody>
              {st.credentials.map((c) => <CredRow key={c.model} c={c} onRemoved={refresh} />)}
            </tbody>
          </table>
        ) : <p className="hint">No models configured. Add one above to enable agents.</p>}
      </Panel>

      {/* ── agents ── */}
      <Panel pad>
        <PanelHeader title="Agents" help="An agent is a role bound to a configured model. The orchestrator runs the roster you build here." />
        <AddAgent roles={cat.roles} models={st.credentials} onAdded={refresh} />
        {st.agents.length ? (
          <table className="data" style={{ marginTop: 10 }}>
            <thead><tr><th>Agent</th><th>Role</th><th>Model</th><th>Transport</th><th></th></tr></thead>
            <tbody>
              {st.agents.map((a) => (
                <tr key={a.agent}>
                  <td className="mono">{a.agent}</td>
                  <td className="role">{a.role}</td>
                  <td className="mono dim">{a.model}</td>
                  <td className="mono">{a.transport}</td>
                  <td><button className="btn ghost" style={{ padding: "2px 8px" }}
                    onClick={async () => { await del(`/api/settings/agents/${encodeURIComponent(a.agent)}`); refresh(); }}>Remove</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : <p className="hint" style={{ marginTop: 10 }}>No agents yet.</p>}
      </Panel>
    </div>
  );
}

function CredRow({ c, onRemoved }: {
  c: { model: string; transport: string; enabled: boolean; has_key: boolean; key_hint: string };
  onRemoved: () => void;
}) {
  const [res, setRes] = useState<TestResult | null>(null);
  const [busy, setBusy] = useState(false);
  return (
    <tr>
      <td className="mono">{c.model}</td>
      <td className="mono">{c.transport}</td>
      <td className="mono dim">{c.transport === "api" ? (c.has_key ? c.key_hint : "— no key") : "n/a"}</td>
      <td>{c.enabled ? <span className="sage">✓</span> : <span className="dim">off</span>}</td>
      <td>
        <button className="btn ghost" style={{ padding: "2px 8px" }} disabled={busy}
          onClick={async () => { setBusy(true); setRes(await post(`/api/settings/credentials/${encodeURIComponent(c.model)}/test`)); setBusy(false); }}>
          {busy ? "…" : "Test"}
        </button>
        {res && (res.working
          ? <span className="sage" title={res.detail} style={{ marginLeft: 6 }}>✓</span>
          : <span className="rust" title={res.detail} style={{ marginLeft: 6 }}>✗</span>)}
      </td>
      <td><button className="btn ghost" style={{ padding: "2px 8px" }}
        onClick={async () => { await del(`/api/settings/credentials/${encodeURIComponent(c.model)}`); onRemoved(); }}>Remove</button></td>
    </tr>
  );
}

function ModelRow({ m, configured, onSaved }: {
  m: { id: string; label: string; transports: string[] };
  configured: boolean; onSaved: () => void;
}) {
  const [transport, setTransport] = useState(m.transports[0]);
  const [key, setKey] = useState("");
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [res, setRes] = useState<TestResult | null>(null);
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "5px 0", borderBottom: "1px solid #222839" }}>
      <span className="mono" style={{ width: 200 }}>{m.label}</span>
      <span className="mono dim" style={{ width: 150 }}>{m.id}</span>
      {configured ? <Chip active>added</Chip> : (
        open ? (
          <>
            <select value={transport} onChange={(e) => setTransport(e.target.value)}>
              {m.transports.map((t) => <option key={t} value={t}>{t}</option>)}
            </select>
            {transport === "api" && <input placeholder="API key" value={key} type="password"
              onChange={(e) => setKey(e.target.value)} style={{ width: 200 }} />}
            <button className="btn primary" style={{ padding: "4px 10px" }} disabled={busy}
              onClick={async () => {
                setBusy(true); setRes(null);
                const r: TestResult = await post("/api/settings/credentials", { model: m.id, transport, api_key: key || null, enabled: true });
                setBusy(false); setRes(r);
                // keep the row open on failure so the user can correct the key; close on success
                if (!r.tested || r.working) { setOpen(false); setKey(""); onSaved(); }
              }}>{busy ? "Testing…" : "Save & test"}</button>
            <button className="btn ghost" style={{ padding: "4px 10px" }} onClick={() => setOpen(false)}>Cancel</button>
            {res && res.tested && (res.working
              ? <span className="sage" title={res.detail}>✓ key works</span>
              : <span className="rust" title={res.detail}>✗ {res.detail}</span>)}
          </>
        ) : <button className="btn" style={{ padding: "3px 10px" }} onClick={() => setOpen(true)}>Add</button>
      )}
    </div>
  );
}

function AddAgent({ roles, models, onAdded }: {
  roles: string[]; models: { model: string; transport: string }[]; onAdded: () => void;
}) {
  const [agent, setAgent] = useState("");
  const [role, setRole] = useState(roles[0]);
  const [model, setModel] = useState(models[0]?.model ?? "");
  if (!models.length) return <p className="hint">Add a model first.</p>;
  const transport = models.find((m) => m.model === model)?.transport ?? "api";
  return (
    <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
      <input placeholder="agent name (e.g. dev-a)" value={agent} onChange={(e) => setAgent(e.target.value)} style={{ width: 170 }} />
      <select value={role} onChange={(e) => setRole(e.target.value)}>{roles.map((r) => <option key={r}>{r}</option>)}</select>
      <select value={model} onChange={(e) => setModel(e.target.value)}>{models.map((m) => <option key={m.model}>{m.model}</option>)}</select>
      <span className="chip">{transport}</span>
      <button className="btn primary" disabled={!agent.trim()} style={{ padding: "4px 12px" }}
        onClick={async () => { await post("/api/settings/agents", { agent, role, model, transport }); setAgent(""); onAdded(); }}>
        Add agent
      </button>
    </div>
  );
}
