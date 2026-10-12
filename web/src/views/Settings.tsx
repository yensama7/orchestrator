import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { useApi } from "../api";
import { Chip, Panel, PanelHeader } from "../components";

type Model = { id: string; label: string; transports: string[] };
type Catalog = {
  providers: { provider: string; key_env: string | null; cli?: string; models: Model[] }[];
  roles: string[];
};
type Settings = {
  credentials: { model: string; transport: string; enabled: boolean; has_key: boolean; key_hint: string }[];
  agents: { agent: string; role: string; model: string; transport: string; enabled: boolean }[];
};
type Role = { name: string; description: string; skills: string[]; resources: string[]; egress: string[]; researched_at: string | null };
type Preset = { name: string; description: string; model_hint: string; skills: string[]; resources: string[]; egress: string[] };

type TestResult = { ok?: boolean; tested: boolean; working?: boolean; detail?: string };

// one place deciding what a save result means, so ModelRow and ProviderPicker
// agree. The credential is persisted whenever ok !== false (the row saves even
// when the live test fails); a failed-closed save (ok:false, e.g. no
// LINEAGE_SECRET_KEY to seal the key) is NOT saved and its error must stay
// visible — the old code closed silently and left nothing added.
const notSaved = (r: TestResult) => r.ok === false;
const isErr = (r: TestResult) => r.ok === false || (r.tested && r.working === false);
const saveMsg = (r: TestResult) =>
  r.ok === false ? `✗ ${r.detail || "not saved"}`
    : r.tested ? (r.working ? "✓ key works" : `✗ ${r.detail} (saved — fix in the table below)`)
    : null;

// above this many models per provider, the picker is a searchable dropdown
// instead of one row per model (OpenRouter's live catalogue is hundreds).
const DROPDOWN_OVER = 8;

async function post(url: string, body?: unknown): Promise<any> {
  const r = await fetch(url, { method: "POST", headers: { "content-type": "application/json" }, body: body ? JSON.stringify(body) : undefined });
  return r.json().catch(() => ({}));
}
async function del(url: string) { await fetch(url, { method: "DELETE" }); }

async function saveCred(model: string, transport: string, key: string): Promise<TestResult> {
  return post("/api/settings/credentials", { model, transport, api_key: key || null, enabled: true });
}

export default function SettingsView() {
  const qc = useQueryClient();
  const { data: cat } = useApi<Catalog>("catalog");
  const { data: st } = useApi<Settings>("settings");
  const { data: roles } = useApi<Role[]>("roles");
  const refresh = () => { qc.invalidateQueries({ queryKey: ["settings"] }); qc.invalidateQueries({ queryKey: ["agents"] }); qc.invalidateQueries({ queryKey: ["credits"] }); };
  const refreshRoles = () => qc.invalidateQueries({ queryKey: ["roles"] });
  if (!cat || !st) return null;

  const configured = new Set(st.credentials.map((c) => c.model));
  // researched roles extend the built-in hints; agents can bind to either.
  const roleNames = [...new Set([...cat.roles, ...(roles ?? []).map((r) => r.name)])];

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
            {p.models.length > DROPDOWN_OVER
              ? <ProviderPicker models={p.models} configured={configured} onSaved={refresh} />
              : p.models.map((m) => (
                  <ModelRow key={m.id} m={m} configured={configured.has(m.id)} onSaved={refresh} />
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

      {/* ── live credit monitoring ── */}
      <Panel pad>
        <PanelHeader title="Credits & spend" help="OpenRouter balance (when used), API spend by provider, and subscription quota — all live." />
        <CreditsPanel />
      </Panel>

      {/* ── local models ── */}
      <Panel pad>
        <PanelHeader title="Local models" help="Download Ollama models to run nodes locally at zero marginal cost. Recommendations adapt to your detected GPU." />
        <LocalModelsPanel onChanged={refresh} />
      </Panel>

      {/* ── roles ── */}
      <Panel pad>
        <PanelHeader title="Roles" help="Define a role and the central agent researches its skills + resources (falling back to the ECC library), which get injected into every node prompt that uses the role." />
        <RolesPanel roles={roles ?? []} onChanged={refreshRoles} />
      </Panel>

      {/* ── agents ── */}
      <Panel pad>
        <PanelHeader title="Agents" help="An agent is a role bound to a configured model. The orchestrator runs the roster you build here." />
        <AddAgent roles={roleNames} models={st.credentials} onAdded={refresh} />
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
  m: Model; configured: boolean; onSaved: () => void;
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
                const r = await saveCred(m.id, transport, key);
                setBusy(false); setRes(r);
                // saved (ok !== false) → add it to the configured list and close,
                // even if the live test failed (consistent with the backend, which
                // persists the row so a bad key can be re-tested/removed in the
                // table). Only a not-saved result keeps the row open with its error.
                if (!notSaved(r)) { onSaved(); setOpen(false); setKey(""); }
              }}>{busy ? "Testing…" : "Save & test"}</button>
            <button className="btn ghost" style={{ padding: "4px 10px" }} onClick={() => setOpen(false)}>Cancel</button>
            {res && saveMsg(res) && <span className={isErr(res) ? "rust" : "sage"} title={res.detail}>{saveMsg(res)}</span>}
          </>
        ) : <button className="btn" style={{ padding: "3px 10px" }} onClick={() => setOpen(true)}>Add</button>
      )}
    </div>
  );
}

// Searchable single-select for providers with many models (OpenRouter live
// catalogue, installed local models). Pick one, set transport/key, add it.
function ProviderPicker({ models, configured, onSaved }: {
  models: Model[]; configured: Set<string>; onSaved: () => void;
}) {
  const [q, setQ] = useState("");
  const [picked, setPicked] = useState("");
  const [transport, setTransport] = useState("api");
  const [key, setKey] = useState("");
  const [busy, setBusy] = useState(false);
  const [res, setRes] = useState<TestResult | null>(null);

  const available = models.filter((m) => !configured.has(m.id));
  const filtered = q.trim()
    ? available.filter((m) => (m.label + " " + m.id).toLowerCase().includes(q.toLowerCase())).slice(0, 50)
    : available.slice(0, 50);
  const model = available.find((m) => m.id === picked);
  useEffect(() => { if (model) setTransport(model.transports[0]); }, [picked]); // eslint-disable-line

  return (
    <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center" }}>
      <input placeholder={`search ${available.length} models…`} value={q}
        onChange={(e) => { setQ(e.target.value); }} style={{ width: 200 }} />
      <select value={picked} onChange={(e) => { setPicked(e.target.value); setRes(null); }} style={{ minWidth: 260 }}>
        <option value="">— pick a model —</option>
        {filtered.map((m) => <option key={m.id} value={m.id}>{m.label} ({m.id})</option>)}
      </select>
      {model && (
        <>
          <select value={transport} onChange={(e) => setTransport(e.target.value)}>
            {model.transports.map((t) => <option key={t} value={t}>{t}</option>)}
          </select>
          {transport === "api" && <input placeholder="API key (optional if env set)" value={key} type="password"
            onChange={(e) => setKey(e.target.value)} style={{ width: 200 }} />}
          <button className="btn primary" style={{ padding: "4px 10px" }} disabled={busy}
            onClick={async () => {
              setBusy(true); setRes(null);
              const r = await saveCred(model.id, transport, key);
              setBusy(false); setRes(r);
              if (!notSaved(r)) { onSaved(); setPicked(""); setKey(""); setQ(""); }
            }}>{busy ? "Testing…" : "Save & test"}</button>
          {res && saveMsg(res) && <span className={isErr(res) ? "rust" : "sage"} title={res.detail}>{saveMsg(res)}</span>}
        </>
      )}
    </div>
  );
}

// ── live credit monitoring ───────────────────────────────────────────────────
type Credits = {
  openrouter: { configured: boolean; balance: { total: number; used: number; remaining: number } | null };
  api_spend: { total: number; by_provider: Record<string, number> };
  subscriptions: { cli: string; used: number; limit: number }[];
};
function CreditsPanel() {
  const { data } = useApi<Credits>("credits");
  if (!data) return <p className="hint">Loading…</p>;
  const or = data.openrouter;
  const providers = Object.entries(data.api_spend.by_provider);
  return (
    <div className="stack" style={{ gap: 14 }}>
      <div>
        <div className="section-title">OpenRouter</div>
        {!or.configured ? <p className="hint">No OpenRouter key — add one above or set OPENROUTER_API_KEY.</p>
          : or.balance ? (
            <div style={{ display: "flex", gap: 18 }}>
              <span className="sage">${or.balance.remaining.toFixed(2)}<span className="lbl dim"> remaining</span></span>
              <span className="dim">${or.balance.used.toFixed(2)} used</span>
              <span className="dimmer">${or.balance.total.toFixed(2)} total</span>
            </div>
          ) : <p className="hint rust">Balance unavailable (key rejected or OpenRouter unreachable).</p>}
      </div>
      <div>
        <div className="section-title">API spend (metered)</div>
        {providers.length ? (
          <div style={{ display: "flex", gap: 18, flexWrap: "wrap" }}>
            <span className="amber">${data.api_spend.total.toFixed(2)}<span className="lbl dim"> total</span></span>
            {providers.map(([p, v]) => <span key={p} className="dim">{p} ${v.toFixed(2)}</span>)}
          </div>
        ) : <p className="hint">No metered spend yet.</p>}
      </div>
      <div>
        <div className="section-title">Subscription quota</div>
        {data.subscriptions.length ? data.subscriptions.map((s) => (
          <div key={s.cli} style={{ display: "flex", alignItems: "center", gap: 8, margin: "3px 0" }}>
            <span className="mono" style={{ width: 70 }}>{s.cli}</span>
            <div style={{ flex: 1, maxWidth: 240, height: 6, background: "#222839", borderRadius: 3 }}>
              <div style={{ width: `${Math.min(100, (s.used / s.limit) * 100)}%`, height: "100%",
                background: s.used >= s.limit ? "#c0603a" : "#6a9", borderRadius: 3 }} />
            </div>
            <span className="dim">{s.used}/{s.limit} req</span>
          </div>
        )) : <p className="hint">No subscription agents configured.</p>}
      </div>
    </div>
  );
}

// ── local model download ──────────────────────────────────────────────────────
type LocalStatus = {
  url: string | null; up: boolean; runtime: boolean;
  gpu: { available: boolean; name: string | null; vram_gb: number };
  installed: string[];
  recommended: { id: string; label: string; size_gb: number; min_vram_gb: number; use: string; fits: boolean }[];
};
function LocalModelsPanel({ onChanged }: { onChanged: () => void }) {
  const qc = useQueryClient();
  const { data } = useApi<LocalStatus>("local/status");
  const [progress, setProgress] = useState<Record<string, string>>({});
  const esRef = useRef<EventSource | null>(null);
  useEffect(() => () => esRef.current?.close(), []);

  if (!data) return <p className="hint">Loading…</p>;
  const gpu = data.gpu;

  const pull = (id: string) => {
    esRef.current?.close();
    setProgress((p) => ({ ...p, [id]: "starting…" }));
    const es = new EventSource(`/api/local/pull?model=${encodeURIComponent(id)}`);
    esRef.current = es;
    es.onmessage = (e) => {
      try {
        const d = JSON.parse(e.data);
        const pct = d.total ? ` ${Math.round((d.completed || 0) / d.total * 100)}%` : "";
        setProgress((p) => ({ ...p, [id]: (d.status || "pulling") + pct }));
      } catch { /* keep last */ }
    };
    es.addEventListener("done", () => { es.close(); setProgress((p) => ({ ...p, [id]: "✓ installed" })); qc.invalidateQueries({ queryKey: ["local/status"] }); qc.invalidateQueries({ queryKey: ["catalog"] }); onChanged(); });
    es.addEventListener("error", (e) => {
      const data = (e as MessageEvent).data;
      es.close();
      // a generic transport close (no data) after "done" isn't a failure — only
      // a server-sent error event carries a message.
      if (!data) return;
      let msg = "failed"; try { msg = JSON.parse(data).error; } catch { /* generic */ }
      setProgress((p) => ({ ...p, [id]: "✗ " + msg }));
    });
  };

  return (
    <div className="stack" style={{ gap: 10 }}>
      <p className="hint">
        Runtime: {data.up ? <span className="sage">Ollama up ({data.url})</span>
          : data.runtime ? <span className="rust">configured but unreachable ({data.url}) — start it: <span className="mono">docker compose --profile local up</span></span>
          : <span className="dim">none — set OLLAMA_URL or run <span className="mono">docker compose --profile local up</span></span>}
        {" · "}
        GPU: {gpu.available ? <span className="sage">{gpu.name} ({gpu.vram_gb} GB)</span> : <span className="dim">none detected — CPU-only recommendations</span>}
      </p>
      <table className="data">
        <thead><tr><th>Model</th><th>Size</th><th>Use</th><th>Fit</th><th></th></tr></thead>
        <tbody>
          {data.recommended.map((m) => {
            const installed = data.installed.some((i) => i === m.id || i.startsWith(m.id + ":"));
            return (
              <tr key={m.id}>
                <td className="mono">{m.label}<span className="dim" style={{ marginLeft: 6 }}>{m.id}</span></td>
                <td className="dim">{m.size_gb} GB</td>
                <td className="dim">{m.use}</td>
                <td>{m.fits ? <span className="sage" title="fits detected hardware">✓</span>
                  : <span className="rust" title={`wants ${m.min_vram_gb} GB VRAM`}>needs GPU</span>}</td>
                <td>
                  {installed ? <Chip active>installed</Chip>
                    : <button className="btn" style={{ padding: "2px 10px" }} disabled={!data.up || /pulling|starting|%/.test(progress[m.id] || "")}
                        onClick={() => pull(m.id)}>Download</button>}
                  {progress[m.id] && <span className="dim mono" style={{ marginLeft: 8 }}>{progress[m.id]}</span>}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function RolesPanel({ roles, onChanged }: { roles: Role[]; onChanged: () => void }) {
  const [name, setName] = useState("");
  const [desc, setDesc] = useState("");
  const [busy, setBusy] = useState(false);
  const { data: presets } = useApi<Preset[]>("roles/presets");
  const have = new Set(roles.map((r) => r.name));
  const addable = (presets ?? []).filter((p) => !have.has(p.name));
  return (
    <>
      <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
        <input placeholder="role name (e.g. data-eng)" value={name} onChange={(e) => setName(e.target.value)} style={{ width: 170 }} />
        <input placeholder="description (optional)" value={desc} onChange={(e) => setDesc(e.target.value)} style={{ flex: 1, minWidth: 200 }} />
        <button className="btn primary" disabled={!name.trim() || busy} style={{ padding: "4px 12px" }}
          onClick={async () => {
            setBusy(true);
            await post("/api/roles", { name: name.trim(), description: desc.trim() });
            setBusy(false); setName(""); setDesc(""); onChanged();
          }}>{busy ? "Researching…" : "Research & add"}</button>
      </div>
      {addable.length ? (
        <div style={{ marginTop: 10 }}>
          <p className="hint" style={{ marginBottom: 6 }}>Starter roles (ECC) — skills, resources + egress pre-filled, no research call:</p>
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
            {addable.map((p) => (
              <button key={p.name} className="btn ghost" style={{ padding: "3px 10px" }} title={p.description}
                onClick={async () => { await post(`/api/roles/presets/${encodeURIComponent(p.name)}`); onChanged(); }}>
                + {p.name} <span className="dim">· {p.model_hint}</span>
              </button>
            ))}
          </div>
        </div>
      ) : null}
      {roles.length ? (
        <table className="data" style={{ marginTop: 10 }}>
          <thead><tr><th>Role</th><th>Skills</th><th>Resources</th><th>Egress</th><th></th></tr></thead>
          <tbody>
            {roles.map((r) => (
              <tr key={r.name}>
                <td className="role">{r.name}</td>
                <td className="dim">{r.skills.join(", ") || "—"}</td>
                <td className="dim">{r.resources.join(", ") || "—"}</td>
                <td className="dim">{r.egress?.length ? r.egress.join(", ") : "deny-all"}</td>
                <td><button className="btn ghost" style={{ padding: "2px 8px" }}
                  onClick={async () => { await del(`/api/roles/${encodeURIComponent(r.name)}`); onChanged(); }}>Remove</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : <p className="hint" style={{ marginTop: 10 }}>No researched roles yet. Add one above, or pick a starter role.</p>}
    </>
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
