import { useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { useApi } from "../api";
import CodeEditor from "../CodeEditor";
import { EmptyState } from "../components";
import { resolve } from "../lang/registry";

type Ws = {
  worktree: string; empty: boolean;
  tree: { folder: string; files: { name: string; ext: string; held: string | null }[] }[];
  open: {
    name: string; ext: string; mode: string; why: string;
    lines: number; chars: number; content: string; blame: string[]; held: string | null;
  } | null;
  gate: { ready: boolean; file?: string; reason?: string; offer?: { label: string };
          services?: { name: string; health: string }[] };
};

export default function Workspace({ run }: { run?: string }) {
  const qc = useQueryClient();
  const { data } = useApi<Ws>("workspace", run);
  const rq = run ? `?run=${encodeURIComponent(run)}` : "";
  const [selected, setSelected] = useState<string | null>(null);
  const [importing, setImporting] = useState(false);
  const [runMsg, setRunMsg] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  if (!data) return null;

  const runCompose = async () => {
    setRunMsg("Starting…");
    const r = await fetch(`/api/runs/${run ?? "current"}/run`, { method: "POST" }).then((x) => x.json());
    setRunMsg(r.started ? `compose up · ${r.file}` : `can't run: ${r.reason}`);
  };

  const importFolder = async (files: FileList) => {
    setImporting(true);
    try {
      const fd = new FormData();
      const paths: string[] = [];
      Array.from(files).forEach((f) => {
        fd.append("files", f);
        paths.push((f as any).webkitRelativePath || f.name);
      });
      fd.append("paths", JSON.stringify(paths));
      await fetch(`/api/workspace/import${rq}`, { method: "POST", body: fd });
      setSelected(null);
      qc.invalidateQueries({ queryKey: ["workspace"] });
    } finally { setImporting(false); }
  };

  const clear = async () => {
    await fetch(`/api/workspace${rq}`, { method: "DELETE" });
    setSelected(null);
    qc.invalidateQueries({ queryKey: ["workspace"] });
  };

  const importInput = (
    <input ref={inputRef} type="file" hidden multiple
      {...({ webkitdirectory: "", directory: "" } as any)}
      onChange={(e) => e.target.files && importFolder(e.target.files)} />
  );

  if (data.empty) {
    return (
      <div className="ws" style={{ gridTemplateColumns: "1fr" }}>
        <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 12 }}>
          {importInput}
          <EmptyState message="No worktree yet. Import a folder to browse and run it."
            action={<button className="btn primary" disabled={importing}
              onClick={() => inputRef.current?.click()}>{importing ? "Importing…" : "Import folder"}</button>} />
        </div>
      </div>
    );
  }

  const f = data.open;
  const active = selected ?? f?.name ?? null;
  const showEditor = f && active === f.name;
  const res = f ? resolve(f.name) : null;

  return (
    <div className="ws">
      <div className="ws-tree">
        <div className="ws-folder mono" style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <span style={{ flex: 1 }}>{data.worktree}</span>
          {importInput}
          <button className="btn ghost" style={{ padding: "1px 6px", fontSize: 11 }}
            onClick={() => inputRef.current?.click()} title="Import folder">＋</button>
          <button className="btn ghost" style={{ padding: "1px 6px", fontSize: 11 }}
            onClick={clear} title="Clear worktree">✕</button>
        </div>
        {data.tree.map((grp) => (
          <div key={grp.folder}>
            <div className="ws-folder">{grp.folder}</div>
            {grp.files.map((file) => (
              <div key={grp.folder + file.name}
                   className={"ws-file" + (file.name === active ? " active" : "")}
                   onClick={() => setSelected(file.name)}>
                <span>{file.name}</span>
                {file.held && <span title={`held by ${file.held}`}>🔒</span>}
                <span className="ext-badge">{file.ext}</span>
              </div>
            ))}
          </div>
        ))}
      </div>

      <div className="ws-main">
        <div className="breadcrumb">
          <span className="seg">{data.worktree}</span>
          {active && <>
            <span className="sep">›</span>
            <span className="seg">{data.tree.find((g) => g.files.some((x) => x.name === active))?.folder.replace(/\/$/, "")}</span>
            <span className="sep">›</span>
            <span className="seg" style={{ color: "var(--bone)" }}>{active}</span>
          </>}
        </div>

        {showEditor && f && res ? (
          <>
            <div className="edbar">
              <span className="ext-badge">{f.ext || "txt"}</span>
              <span className="fn">{f.name}</span>
              <span className="meta">· {f.mode} · {f.lines} lines · {f.chars} chars</span>
              <span className="meta" style={{ cursor: "help" }}
                    title={`extension .${f.ext} → tier ${res.tier} → ${res.mode}`}> ⓘ why</span>
              {res.tier === 3 && <span className="meta rust"> · generic fallback</span>}
              {f.held && <span className="lock">🔒 held by {f.held}</span>}
            </div>
            <div style={{ flex: 1, minHeight: 0 }}>
              <CodeEditor filename={f.name} content={f.content} blame={f.blame} readOnly={!!f.held} />
            </div>
          </>
        ) : (
          <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center" }}>
            <EmptyState message="Select a file with a local copy to view it." />
          </div>
        )}

        <div className="runbar">
          {data.gate.ready ? (
            <>
              <span className="sage">{data.gate.file} ✓</span>
              <button className="btn primary" style={{ padding: "4px 12px" }} onClick={runCompose}>▶ Run</button>
              {runMsg && <span className="meta" style={{ marginLeft: 8 }}>{runMsg}</span>}
              {data.gate.services?.map((s) => (
                <span className="svc" key={s.name}>
                  <span className="dot" style={{ background: s.health === "up" ? "var(--sage)" : "var(--rust)" }} />{s.name}
                </span>
              ))}
            </>
          ) : (
            <EmptyState
              message={data.gate.reason === "no_compose"
                ? "No compose file. Generate one from the Dockerfile?"
                : "Not containerised yet — no compose file in the imported worktree."}
              action={<button className="btn">{data.gate.offer?.label}</button>} />
          )}
        </div>
      </div>
    </div>
  );
}
