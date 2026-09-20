import { ReactNode, useEffect, useRef, useState } from "react";
import { hideTip, showTip, TipLine } from "./hover";

// token hex (canvas can't read CSS vars); DOM/tooltip can use var() or these.
export const HEX: Record<string, string> = {
  amber: "#e0a33c", sage: "#7fb894", rust: "#c96a52", violet: "#9b8ce0",
  steel: "#6d8bc7", dimmer: "#69708a", ink3: "#222940", bone: "#e7e4db",
  line: "#2b3348", line2: "#394261", dim: "#99a0b4",
};
export const COLOR: Record<string, string> = Object.fromEntries(
  Object.keys(HEX).map((k) => [k, `var(--${k})`])
);
const hex = (c: string) => HEX[c] ?? c;

export const Dot = ({ color, ring }: { color: string; ring?: boolean }) => (
  <span className={"dot" + (ring ? " ring" : "")}
        style={{ background: COLOR[color] ?? color, color: COLOR[color] ?? color }} />
);

export const Panel = ({ children, pad, className }: { children: ReactNode; pad?: boolean; className?: string }) => (
  <div className={"panel" + (pad ? " pad" : "") + (className ? " " + className : "")}>{children}</div>
);

export const PanelHeader = ({ title, help }: { title: string; help?: string }) => (
  <div className="panel-h">
    <h3>{title}</h3>
    {help && <button className="help" title={help}>?</button>}
  </div>
);

export const Row = ({ color, label, n }: { color?: string; label: ReactNode; n?: ReactNode }) => (
  <div className="row">
    {color && <Dot color={color} />}
    <span className="label">{label}</span>
    {n != null && <span className="n">{n}</span>}
  </div>
);

export const Chip = ({ active, children, onClick }: { active?: boolean; children: ReactNode; onClick?: () => void }) => (
  <button className={"chip" + (active ? " active" : "")} onClick={onClick}>{children}</button>
);

export const EmptyState = ({ message, action }: { message: string; action?: ReactNode }) => (
  <div className="empty"><p>{message}</p>{action}</div>
);

// ── interactive scatter (Tasks 2 + 5, prompt_hover.md) ──────────────────────
export type Pt = {
  id: string; x: number; y: number; size: number; color: string;
  name?: string; domain?: string; ring?: boolean; dimmed?: boolean;
  meta?: { status?: string; cost?: number; subject?: string };
};

// Deterministic fan-out: the hash embedder collapses similar fingerprints to
// near-identical coords, so points stack as runs accumulate. Group by cell and
// spread duplicates on a ring — keeps the graph readable at any node count.
const clamp = (v: number) => Math.max(0.02, Math.min(0.98, v));
export function spread(points: Pt[]): Pt[] {
  const buckets = new Map<string, Pt[]>();
  for (const p of points) {
    const k = `${Math.round(p.x * 80)},${Math.round(p.y * 80)}`;
    (buckets.get(k) ?? buckets.set(k, []).get(k)!).push(p);
  }
  const out: Pt[] = [];
  for (const g of buckets.values()) {
    if (g.length === 1) { out.push(g[0]); continue; }
    const r = 0.02 * Math.min(1 + Math.floor(g.length / 6), 4);
    g.forEach((p, i) => {
      const a = (i / g.length) * Math.PI * 2;
      out.push({ ...p, x: clamp(p.x + Math.cos(a) * r), y: clamp(p.y + Math.sin(a) * r) });
    });
  }
  return out;
}

export const Legend = ({ items }: { items: { color: string; label: string }[] }) => (
  <div className="legend">
    {items.map((it) => (
      <span key={it.label} className="legend-item">
        <span className="dot" style={{ background: COLOR[it.color] ?? it.color }} />{it.label}
      </span>
    ))}
  </div>
);

export function Scatter({
  points, edges = [], labels = [], height = 430, onCommit,
}: {
  points: Pt[]; edges?: [string, string][];
  labels?: { x: number; y: number; text: string }[];
  height?: number; onCommit?: (id: string) => void;
}) {
  const ref = useRef<HTMLCanvasElement>(null);
  const hover = useRef<string | null>(null);
  const raf = useRef(0);

  const draw = () => {
    const cv = ref.current; if (!cv) return;
    const dpr = window.devicePixelRatio || 1;
    const w = cv.clientWidth, h = height;
    cv.width = w * dpr; cv.height = h * dpr;
    const ctx = cv.getContext("2d")!; ctx.scale(dpr, dpr); ctx.clearRect(0, 0, w, h);
    const px = (p: Pt) => [p.x * w, p.y * h] as const;
    const byId = new Map(points.map((p) => [p.id, p]));
    const hv = hover.current ? byId.get(hover.current) : null;
    const hot = new Set<string>();
    if (hv) for (const [a, b] of edges) { if (a === hv.id) hot.add(b); if (b === hv.id) hot.add(a); }

    // grid
    ctx.strokeStyle = "#1c2334"; ctx.lineWidth = 1;
    for (let i = 1; i < 10; i++) {
      ctx.beginPath(); ctx.moveTo((w / 10) * i, 0); ctx.lineTo((w / 10) * i, h); ctx.stroke();
      ctx.beginPath(); ctx.moveTo(0, (h / 10) * i); ctx.lineTo(w, (h / 10) * i); ctx.stroke();
    }
    ctx.fillStyle = HEX.dimmer; ctx.font = "12px 'JetBrains Mono', monospace";
    labels.forEach((l) => ctx.fillText(l.text, l.x * w, l.y * h));

    // edges
    for (const [a, b] of edges) {
      const pa = byId.get(a), pb = byId.get(b); if (!pa || !pb) continue;
      const on = hv && (a === hv.id || b === hv.id);
      ctx.strokeStyle = on ? HEX.amber : "rgba(105,112,138,0.30)";
      ctx.lineWidth = on ? 1.4 : 1;
      const [x1, y1] = px(pa), [x2, y2] = px(pb);
      ctx.beginPath(); ctx.moveTo(x1, y1);
      ctx.quadraticCurveTo((x1 + x2) / 2, (y1 + y2) / 2 - 0.04 * h, x2, y2); ctx.stroke();
    }

    // points
    for (const p of points) {
      const [x, y] = px(p);
      const isHover = hv?.id === p.id;
      const alpha = p.dimmed ? 0.09 : hv && !isHover && !hot.has(p.id) ? 0.92 : 1;
      ctx.globalAlpha = alpha;
      const r = isHover ? p.size * 1.5 : p.size;
      ctx.beginPath(); ctx.arc(x, y, r, 0, Math.PI * 2); ctx.fillStyle = hex(p.color); ctx.fill();
      if (p.ring) { ctx.beginPath(); ctx.arc(x, y, r + 6, 0, Math.PI * 2); ctx.strokeStyle = hex(p.color); ctx.lineWidth = 1.5; ctx.stroke(); }
      if (isHover) { ctx.beginPath(); ctx.arc(x, y, r, 0, Math.PI * 2); ctx.strokeStyle = HEX.bone; ctx.lineWidth = 1.3; ctx.stroke(); }
      ctx.globalAlpha = 1;
    }
  };

  useEffect(draw, [points, edges, labels, height]);

  const pick = (e: React.MouseEvent): Pt | null => {
    const cv = ref.current!; const rect = cv.getBoundingClientRect();
    const mx = e.clientX - rect.left, my = e.clientY - rect.top;
    let best: Pt | null = null, bd = 13; // flat 13px hit radius
    for (const p of points) {
      if (p.dimmed) continue;
      const d = Math.hypot(p.x * rect.width - mx, p.y * rect.height - my);
      if (d < bd) { bd = d; best = p; }
    }
    return best;
  };

  const onMove = (e: React.MouseEvent) => {
    const clientX = e.clientX, clientY = e.clientY;
    if (raf.current) return;
    raf.current = requestAnimationFrame(() => {
      raf.current = 0;
      const p = pick({ clientX, clientY } as React.MouseEvent);
      if (p?.id !== hover.current) { hover.current = p?.id ?? null; draw(); }
      if (p) {
        const lines: TipLine[] = [{ text: p.name ?? p.id, color: hex(p.color), weight: 600 }];
        const meta = [p.domain, p.meta?.status, p.meta?.cost != null ? `$${p.meta.cost}` : null]
          .filter(Boolean).join(" · ");
        if (meta) lines.push({ text: meta, mono: true, color: HEX.dim });
        showTip(clientX, clientY, lines);
      } else hideTip();
    });
  };

  return (
    <div className="canvas-wrap">
      <canvas ref={ref} style={{ height }}
        tabIndex={0}
        onMouseMove={onMove}
        onMouseLeave={() => { hover.current = null; hideTip(); draw(); }}
        onClick={() => hover.current && onCommit?.(hover.current)} />
    </div>
  );
}

// ── interactive doughnut (Task 3) ───────────────────────────────────────────
export type Slice = { label: string; value: number; unit?: string; color: string };

export function Donut({ slices, size = 120, centerLabel }: {
  slices: Slice[]; size?: number; centerLabel?: string;
}) {
  const [hi, setHi] = useState<number | null>(null);
  const total = slices.reduce((s, x) => s + x.value, 0) || 1;
  const r = size / 2, cx = r, cy = r, inner = r * 0.56;
  let a0 = -Math.PI / 2;
  const arcs = slices.map((s, i) => {
    const a1 = a0 + (s.value / total) * Math.PI * 2;
    const mid = (a0 + a1) / 2;
    const large = a1 - a0 > Math.PI ? 1 : 0;
    const off = hi === i ? 4 : 0;   // offset outward along bisector
    const ox = Math.cos(mid) * off, oy = Math.sin(mid) * off;
    const P = (ang: number, rad: number) => [cx + ox + Math.cos(ang) * rad, cy + oy + Math.sin(ang) * rad];
    const [x0, y0] = P(a0, r), [x1, y1] = P(a1, r), [x2, y2] = P(a1, inner), [x3, y3] = P(a0, inner);
    a0 = a1;
    return { d: `M${x0},${y0} A${r},${r} 0 ${large} 1 ${x1},${y1} L${x2},${y2} A${inner},${inner} 0 ${large} 0 ${x3},${y3} Z`, mid };
  });
  const center = hi != null
    ? { big: fmt(slices[hi].value, slices[hi].unit), small: slices[hi].label }
    : { big: fmt(total, slices[0]?.unit), small: centerLabel ?? "total" };

  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}
      onMouseLeave={() => { setHi(null); hideTip(); }}>
      {arcs.map((a, i) => (
        <path key={i} d={a.d} fill={hex(slices[i].color)}
          style={{ opacity: hi == null || hi === i ? 1 : 0.55, cursor: "default" }}
          onMouseMove={(e) => {
            setHi(i);
            const pct = Math.round((slices[i].value / total) * 100);
            showTip(e.clientX, e.clientY, [
              { text: slices[i].label, color: hex(slices[i].color), weight: 600 },
              { text: `${fmt(slices[i].value, slices[i].unit)} · ${pct}%`, mono: true, color: HEX.dim },
            ]);
          }} />
      ))}
      <text x={cx} y={cy - 2} textAnchor="middle" fontFamily="var(--mono)" fontSize="15" fill={HEX.bone}>{center.big}</text>
      <text x={cx} y={cy + 12} textAnchor="middle" fontSize="10" fill={HEX.dimmer}>{center.small}</text>
    </svg>
  );
}

// ── line chart with crosshair + index tooltip (Task 4) ──────────────────────
export function LineChart({ data, series, footer, height = 130 }: {
  data: Record<string, number>[];
  series: { key: string; label: string; color: string }[];
  footer?: (row: Record<string, number>) => TipLine[];
  height?: number;
}) {
  const ref = useRef<SVGSVGElement>(null);
  const [hi, setHi] = useState<number | null>(null);
  if (!data.length) return <svg viewBox={`0 0 300 ${height}`} width="100%" height={height} />;
  const W = 300, H = height, pad = 8;
  const xs = data.map((_, i) => pad + (i / Math.max(data.length - 1, 1)) * (W - 2 * pad));
  const allV = data.flatMap((d) => series.map((s) => d[s.key] ?? 0));
  const maxV = Math.max(...allV, 1);
  const y = (v: number) => H - pad - (v / maxV) * (H - 2 * pad);

  const onMove = (e: React.MouseEvent) => {
    const rect = ref.current!.getBoundingClientRect();
    const mx = (e.clientX - rect.left) / rect.width * W;
    let idx = 0, bd = Infinity;
    xs.forEach((x, i) => { const d = Math.abs(x - mx); if (d < bd) { bd = d; idx = i; } });
    setHi(idx);
    const row = data[idx];
    const lines: TipLine[] = series
      .map((s) => ({ s, v: row[s.key] ?? 0 })).sort((a, b) => b.v - a.v)
      .map(({ s, v }) => ({ text: `${s.label}  ${fmt(v, "$")}`, mono: true, color: hex(s.color) }));
    if (footer) lines.push(...footer(row));
    showTip(e.clientX, e.clientY, lines);
  };

  return (
    <svg ref={ref} viewBox={`0 0 ${W} ${H}`} width="100%" height={height}
      onMouseMove={onMove} onMouseLeave={() => { setHi(null); hideTip(); }}>
      {series.map((s) => (
        <path key={s.key} fill="none" stroke={hex(s.color)} strokeWidth="1.5"
          strokeDasharray={s.key === "uncached" ? "3 3" : undefined}
          d={data.map((d, i) => `${i ? "L" : "M"}${xs[i]},${y(d[s.key] ?? 0)}`).join(" ")} />
      ))}
      {hi != null && <>
        <line x1={xs[hi]} y1={pad} x2={xs[hi]} y2={H - pad} stroke={HEX.line2} strokeWidth="1" />
        {series.map((s) => <circle key={s.key} cx={xs[hi]} cy={y(data[hi][s.key] ?? 0)} r="3" fill={hex(s.color)} />)}
      </>}
    </svg>
  );
}

function fmt(v: number, unit?: string): string {
  if (unit === "$") return `$${v.toFixed(2)}`;
  if (unit === "tokens") return v >= 1e6 ? `${(v / 1e6).toFixed(2)}M` : v >= 1e3 ? `${(v / 1e3).toFixed(0)}K` : `${v}`;
  return unit ? `${v} ${unit}` : `${v}`;
}
