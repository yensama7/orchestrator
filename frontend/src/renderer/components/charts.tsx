import { useEffect, useRef, useState } from "react";
import { hideTip, showTip, type TipLine } from "@/lib/hover";

// Custom canvas/SVG visualizations ported verbatim from web/src/components.tsx.
// These are not "markup to reskin" — they're a self-contained graphics subsystem
// with their own meaning-bearing palette (sage=passed, amber=active, rust=failed,
// violet=template/vindicated, steel=info). The palette lives here + in styles.css
// (--chart-*); the surrounding view chrome is what moves to shadcn/Tailwind.

// token hex (canvas can't read CSS vars); DOM/tooltip can use var() or these.
export const HEX: Record<string, string> = {
	amber: "#e0a33c",
	sage: "#7fb894",
	rust: "#c96a52",
	violet: "#9b8ce0",
	steel: "#6d8bc7",
	dimmer: "#69708a",
	ink3: "#222940",
	bone: "#e7e4db",
	line: "#2b3348",
	line2: "#394261",
	dim: "#99a0b4",
};
export const COLOR: Record<string, string> = Object.fromEntries(Object.keys(HEX).map((k) => [k, HEX[k]]));
const hex = (c: string) => HEX[c] ?? c;

export const Dot = ({ color, ring }: { color: string; ring?: boolean }) => (
	<span
		className={"chart-dot" + (ring ? " ring" : "")}
		style={{ background: COLOR[color] ?? color, color: COLOR[color] ?? color }}
	/>
);

export const Legend = ({ items }: { items: { color: string; label: string }[] }) => (
	<div className="chart-legend">
		{items.map((it) => (
			<span key={it.label} className="chart-legend-item">
				<span className="chart-dot" style={{ background: COLOR[it.color] ?? it.color }} />
				{it.label}
			</span>
		))}
	</div>
);

// ── interactive scatter ─────────────────────────────────────────────────────
export type Pt = {
	id: string;
	x: number;
	y: number;
	size: number;
	color: string;
	name?: string;
	domain?: string;
	ring?: boolean;
	dimmed?: boolean;
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
		if (g.length === 1) {
			out.push(g[0]);
			continue;
		}
		const r = 0.02 * Math.min(1 + Math.floor(g.length / 6), 4);
		g.forEach((p, i) => {
			const a = (i / g.length) * Math.PI * 2;
			out.push({ ...p, x: clamp(p.x + Math.cos(a) * r), y: clamp(p.y + Math.sin(a) * r) });
		});
	}
	return out;
}

// ── Obsidian-style force graph ──────────────────────────────────────────────
// A living graph, not a scatter plot: nodes repel, edges pull like springs, the
// whole thing settles to rest (alpha → 0) and reheats when you grab a node.
// Drag to pin, scroll to zoom toward the cursor, drag the void to pan. Hovering
// a node focuses it + its neighbours and fades everything else.
// ponytail: O(n²) repulsion — fine for tens–hundreds of nodes; Barnes-Hut only
// if a graph ever pushes past ~500.
type Sim = { p: Pt; x: number; y: number; vx: number; vy: number; o: number; to: number };
const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

export function Scatter({
	points,
	edges = [],
	height = 430,
	onCommit,
}: {
	points: Pt[];
	edges?: [string, string][];
	height?: number;
	onCommit?: (id: string) => void;
}) {
	const ref = useRef<HTMLCanvasElement>(null);
	const nodes = useRef<Map<string, Sim>>(new Map());
	const order = useRef<Sim[]>([]);
	const cam = useRef({ k: 1, px: 0, py: 0 });
	const hover = useRef<string | null>(null);
	const alpha = useRef(1);
	const raf = useRef(0);
	const drag = useRef<{ n: Sim; moved: boolean } | null>(null);
	const pan = useRef<{ x: number; y: number } | null>(null);

	// Rebuild sim nodes from props, preserving positions/velocity by id so a data
	// refresh nudges the layout instead of resetting it.
	useEffect(() => {
		const prev = nodes.current;
		const next = new Map<string, Sim>();
		points.forEach((p) => {
			const was = prev.get(p.id);
			next.set(
				p.id,
				was
					? { ...was, p }
					: { p, x: (p.x - 0.5) * 520, y: (p.y - 0.5) * 360, vx: 0, vy: 0, o: 1, to: 1 },
			);
		});
		nodes.current = next;
		order.current = [...next.values()];
		alpha.current = 1;
		if (reduceMotion) {
			for (let i = 0; i < 280; i++) step();
			alpha.current = 0;
		}
		kick();
		// eslint-disable-next-line react-hooks/exhaustive-deps
	}, [points, edges]);

	// One physics tick: link springs, pairwise repulsion, weak centering.
	const step = () => {
		const ns = order.current,
			a = alpha.current,
			byId = nodes.current;
		for (const [sa, sb] of edges) {
			const s = byId.get(sa),
				t = byId.get(sb);
			if (!s || !t) continue;
			let dx = t.x - s.x,
				dy = t.y - s.y;
			const l = Math.hypot(dx, dy) || 1;
			const f = ((l - 78) / l) * a * 0.5;
			dx *= f;
			dy *= f;
			t.vx -= dx;
			t.vy -= dy;
			s.vx += dx;
			s.vy += dy;
		}
		for (let i = 0; i < ns.length; i++) {
			const n = ns[i];
			for (let j = i + 1; j < ns.length; j++) {
				const m = ns[j];
				const dx = n.x - m.x,
					dy = n.y - m.y;
				const l2 = dx * dx + dy * dy || 1;
				const w = (150 * a) / l2;
				n.vx += dx * w;
				n.vy += dy * w;
				m.vx -= dx * w;
				m.vy -= dy * w;
			}
			n.vx += -n.x * 0.045 * a;
			n.vy += -n.y * 0.045 * a; // centering gravity
		}
		for (const n of ns) {
			if (drag.current?.n === n) {
				n.vx = n.vy = 0;
				continue;
			}
			n.vx *= 0.6;
			n.vy *= 0.6;
			n.x += n.vx;
			n.y += n.vy;
		}
		alpha.current += (0 - a) * 0.0228;
		if (alpha.current < 0.004) alpha.current = 0;
	};

	const toScreen = (n: Sim, w: number) => {
		const c = cam.current;
		return [w / 2 + c.px + n.x * c.k, height / 2 + c.py + n.y * c.k] as const;
	};

	const render = () => {
		const cv = ref.current;
		if (!cv) return;
		const dpr = window.devicePixelRatio || 1;
		const w = cv.clientWidth,
			h = height;
		if (cv.width !== w * dpr || cv.height !== h * dpr) {
			cv.width = w * dpr;
			cv.height = h * dpr;
		}
		const ctx = cv.getContext("2d")!;
		ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
		ctx.clearRect(0, 0, w, h);
		const k = cam.current.k;

		const hv = hover.current ? nodes.current.get(hover.current) : null;
		const hot = new Set<string>();
		if (hv) {
			hot.add(hv.p.id);
			for (const [a, b] of edges) {
				if (a === hv.p.id) hot.add(b);
				if (b === hv.p.id) hot.add(a);
			}
		}

		// ease each node's focus opacity toward its target (opacity-only motion)
		for (const n of order.current) {
			n.to = n.p.dimmed ? 0.08 : hv ? (hot.has(n.p.id) ? 1 : 0.12) : 1;
			n.o += (n.to - n.o) * 0.25;
		}

		// edges — straight, faint; the hovered node's lie on top, lit amber
		for (const [a, b] of edges) {
			const s = nodes.current.get(a),
				t = nodes.current.get(b);
			if (!s || !t) continue;
			const on = hv && hot.has(a) && hot.has(b);
			const [x1, y1] = toScreen(s, w),
				[x2, y2] = toScreen(t, w);
			ctx.globalAlpha = hv ? (on ? 0.9 : 0.05) : 0.22 * Math.min(s.o, t.o);
			ctx.strokeStyle = on ? HEX.amber : HEX.dimmer;
			ctx.lineWidth = on ? 1.6 : 1;
			ctx.beginPath();
			ctx.moveTo(x1, y1);
			ctx.lineTo(x2, y2);
			ctx.stroke();
		}
		ctx.globalAlpha = 1;

		// nodes
		ctx.font = "11px 'Geist Variable', system-ui, sans-serif";
		ctx.textAlign = "center";
		for (const n of order.current) {
			const [x, y] = toScreen(n, w);
			const focus = hv?.p.id === n.p.id;
			const r = (focus ? n.p.size * 1.35 : n.p.size) * k;
			ctx.globalAlpha = n.o;
			if (focus) {
				// soft glow behind the focused node
				ctx.beginPath();
				ctx.arc(x, y, r + 7, 0, Math.PI * 2);
				ctx.fillStyle = hex(n.p.color);
				ctx.globalAlpha = n.o * 0.18;
				ctx.fill();
				ctx.globalAlpha = n.o;
			}
			ctx.beginPath();
			ctx.arc(x, y, r, 0, Math.PI * 2);
			ctx.fillStyle = hex(n.p.color);
			ctx.fill();
			if (n.p.ring) {
				ctx.beginPath();
				ctx.arc(x, y, r + 5, 0, Math.PI * 2);
				ctx.strokeStyle = hex(n.p.color);
				ctx.lineWidth = 1.5;
				ctx.stroke();
			}
			if (focus) {
				ctx.beginPath();
				ctx.arc(x, y, r, 0, Math.PI * 2);
				ctx.strokeStyle = HEX.bone;
				ctx.lineWidth = 1.3;
				ctx.stroke();
			}
			// labels: always for the focus cluster, otherwise once zoomed in
			if (n.p.name && (hot.has(n.p.id) || k > 1.35) && n.o > 0.2) {
				ctx.globalAlpha = n.o * (focus || k > 1.35 ? 1 : 0.8);
				ctx.fillStyle = focus ? HEX.bone : HEX.dim;
				ctx.fillText(n.p.name, x, y + r + 12);
			}
			ctx.globalAlpha = 1;
		}
	};

	const loop = () => {
		if (alpha.current > 0) step();
		render();
		const fading = !!hover.current || order.current.some((n) => Math.abs(n.o - n.to) > 0.01);
		if (alpha.current > 0 || drag.current || fading) raf.current = requestAnimationFrame(loop);
		else raf.current = 0;
	};
	const kick = () => {
		if (!raf.current) raf.current = requestAnimationFrame(loop);
	};

	// on unmount: stop the loop and hide the shared tooltip.
	useEffect(() => () => {
		if (raf.current) cancelAnimationFrame(raf.current);
		hideTip();
	}, []);

	// native non-passive wheel so zoom can preventDefault the page scroll
	useEffect(() => {
		const cv = ref.current;
		if (!cv) return;
		const h = (e: WheelEvent) => {
			e.preventDefault();
			const rect = cv.getBoundingClientRect();
			const sx = e.clientX - rect.left,
				sy = e.clientY - rect.top,
				c = cam.current;
			const wx = (sx - rect.width / 2 - c.px) / c.k,
				wy = (sy - height / 2 - c.py) / c.k;
			c.k = Math.max(0.3, Math.min(4, c.k * Math.exp(-e.deltaY * 0.0012)));
			c.px = sx - rect.width / 2 - wx * c.k;
			c.py = sy - height / 2 - wy * c.k;
			kick();
		};
		cv.addEventListener("wheel", h, { passive: false });
		return () => cv.removeEventListener("wheel", h);
		// eslint-disable-next-line react-hooks/exhaustive-deps
	}, [height]);

	const atPointer = (e: React.PointerEvent) => {
		const rect = ref.current!.getBoundingClientRect();
		const sx = e.clientX - rect.left,
			sy = e.clientY - rect.top;
		const c = cam.current;
		const wx = (sx - rect.width / 2 - c.px) / c.k,
			wy = (sy - height / 2 - c.py) / c.k;
		return { sx, sy, wx, wy, w: rect.width };
	};
	const pick = (e: React.PointerEvent): Sim | null => {
		const { sx, sy, w } = atPointer(e);
		let best: Sim | null = null,
			bd = Infinity;
		for (const n of order.current) {
			if (n.p.dimmed) continue;
			const [x, y] = toScreen(n, w);
			const d = Math.hypot(x - sx, y - sy);
			if (d < Math.max(n.p.size * cam.current.k + 6, 11) && d < bd) {
				bd = d;
				best = n;
			}
		}
		return best;
	};

	const onDown = (e: React.PointerEvent) => {
		(e.target as HTMLElement).setPointerCapture(e.pointerId);
		const n = pick(e);
		if (n) {
			drag.current = { n, moved: false };
			alpha.current = Math.max(alpha.current, 0.3);
			kick();
		} else {
			const { sx, sy } = atPointer(e);
			pan.current = { x: sx, y: sy };
		}
	};
	const onMove = (e: React.PointerEvent) => {
		const { sx, sy, wx, wy } = atPointer(e);
		if (drag.current) {
			const { n } = drag.current;
			if (Math.hypot(wx - n.x, wy - n.y) * cam.current.k > 4) drag.current.moved = true;
			n.x = wx;
			n.y = wy;
			n.vx = n.vy = 0;
			if (!reduceMotion) alpha.current = Math.max(alpha.current, 0.3);
			kick();
			return;
		}
		if (pan.current) {
			cam.current.px += sx - pan.current.x;
			cam.current.py += sy - pan.current.y;
			pan.current = { x: sx, y: sy };
			kick();
			return;
		}
		const n = pick(e);
		if (n?.p.id !== hover.current) {
			hover.current = n?.p.id ?? null;
			kick();
		}
		if (n) {
			const lines: TipLine[] = [{ text: n.p.name ?? n.p.id, color: hex(n.p.color), weight: 600 }];
			const meta = [n.p.domain, n.p.meta?.status, n.p.meta?.cost != null ? `$${n.p.meta.cost}` : null]
				.filter(Boolean)
				.join(" · ");
			if (meta) lines.push({ text: meta, mono: true, color: HEX.dim });
			showTip(e.clientX, e.clientY, lines);
		} else hideTip();
	};
	const onUp = (e: React.PointerEvent) => {
		if (drag.current && !drag.current.moved) onCommit?.(drag.current.n.p.id);
		drag.current = null;
		pan.current = null;
		(e.target as HTMLElement).releasePointerCapture?.(e.pointerId);
	};
	return (
		<div className="chart-canvas-wrap">
			<canvas
				ref={ref}
				className="chart-graph"
				style={{ height, touchAction: "none" }}
				tabIndex={0}
				onPointerDown={onDown}
				onPointerMove={onMove}
				onPointerUp={onUp}
				onPointerCancel={onUp}
				onPointerLeave={() => {
					if (!drag.current && !pan.current) {
						hover.current = null;
						hideTip();
						kick();
					}
				}}
			/>
		</div>
	);
}

// ── interactive doughnut ─────────────────────────────────────────────────────
export type Slice = { label: string; value: number; unit?: string; color: string };

export function Donut({
	slices,
	size = 120,
	centerLabel,
}: {
	slices: Slice[];
	size?: number;
	centerLabel?: string;
}) {
	const [hi, setHi] = useState<number | null>(null);
	const total = slices.reduce((s, x) => s + x.value, 0) || 1;
	const r = size / 2,
		cx = r,
		cy = r,
		inner = r * 0.56;
	let a0 = -Math.PI / 2;
	const arcs = slices.map((s, i) => {
		const a1 = a0 + (s.value / total) * Math.PI * 2;
		const mid = (a0 + a1) / 2;
		const large = a1 - a0 > Math.PI ? 1 : 0;
		const off = hi === i ? 4 : 0; // offset outward along bisector
		const ox = Math.cos(mid) * off,
			oy = Math.sin(mid) * off;
		const P = (ang: number, rad: number) => [cx + ox + Math.cos(ang) * rad, cy + oy + Math.sin(ang) * rad];
		const [x0, y0] = P(a0, r),
			[x1, y1] = P(a1, r),
			[x2, y2] = P(a1, inner),
			[x3, y3] = P(a0, inner);
		a0 = a1;
		return {
			d: `M${x0},${y0} A${r},${r} 0 ${large} 1 ${x1},${y1} L${x2},${y2} A${inner},${inner} 0 ${large} 0 ${x3},${y3} Z`,
			mid,
		};
	});
	const center =
		hi != null
			? { big: fmt(slices[hi].value, slices[hi].unit), small: slices[hi].label }
			: { big: fmt(total, slices[0]?.unit), small: centerLabel ?? "total" };

	return (
		<svg
			className="chart-svg"
			width={size}
			height={size}
			viewBox={`0 0 ${size} ${size}`}
			onMouseLeave={() => {
				setHi(null);
				hideTip();
			}}
		>
			{arcs.map((a, i) => (
				<path
					key={i}
					d={a.d}
					fill={hex(slices[i].color)}
					stroke="var(--chart-ink2)"
					strokeWidth="1.5"
					style={{ opacity: hi == null || hi === i ? 1 : 0.55, transition: "opacity .12s", cursor: "default" }}
					onMouseMove={(e) => {
						setHi(i);
						const pct = Math.round((slices[i].value / total) * 100);
						showTip(e.clientX, e.clientY, [
							{ text: slices[i].label, color: hex(slices[i].color), weight: 600 },
							{ text: `${fmt(slices[i].value, slices[i].unit)} · ${pct}%`, mono: true, color: HEX.dim },
						]);
					}}
				/>
			))}
			<text x={cx} y={cy - 2} textAnchor="middle" fontFamily="var(--font-family-mono)" fontSize="15" fill={HEX.bone}>
				{center.big}
			</text>
			<text x={cx} y={cy + 12} textAnchor="middle" fontSize="10" fill={HEX.dimmer}>
				{center.small}
			</text>
		</svg>
	);
}

// ── variable-radius pie for agent comparison ────────────────────────────────
export function Pie({
	slices,
	size = 150,
	scale = true,
	unit,
}: {
	slices: Slice[];
	size?: number;
	scale?: boolean;
	unit?: string;
}) {
	const [hi, setHi] = useState<number | null>(null);
	const total = slices.reduce((s, x) => s + x.value, 0) || 1;
	const max = Math.max(...slices.map((s) => s.value), 1);
	const r = size / 2,
		cx = r,
		cy = r,
		gap = 0.018;
	const rMax = size * 0.46,
		rMin = size * 0.28;
	const outer = (v: number) => (scale ? rMin + Math.sqrt(v / max) * (rMax - rMin) : rMax);

	let a0 = -Math.PI / 2;
	const arcs = slices.map((s) => {
		const a1 = a0 + (s.value / total) * Math.PI * 2;
		const rad = outer(s.value),
			mid = (a0 + a1) / 2;
		const P = (ang: number, k = 1) => [cx + Math.cos(ang) * rad * k, cy + Math.sin(ang) * rad * k];
		const [x0, y0] = P(a0 + gap),
			[x1, y1] = P(a1 - gap);
		const large = a1 - a0 - 2 * gap > Math.PI ? 1 : 0;
		a0 = a1;
		return { d: `M${cx},${cy} L${x0},${y0} A${rad},${rad} 0 ${large} 1 ${x1},${y1} Z`, mid, rad };
	});

	return (
		<div className="chart-pie-wrap">
			<svg
				className="chart-svg"
				width={size}
				height={size}
				viewBox={`0 0 ${size} ${size}`}
				onMouseLeave={() => {
					setHi(null);
					hideTip();
				}}
			>
				<defs>
					{slices.map((s, i) => (
						<radialGradient key={i} id={`pie-${i}`} cx="50%" cy="50%" r="75%">
							<stop offset="0%" stopColor={hex(s.color)} stopOpacity="0.72" />
							<stop offset="100%" stopColor={hex(s.color)} stopOpacity="1" />
						</radialGradient>
					))}
				</defs>
				{arcs.map((a, i) => {
					const [tx, ty] = [
						cx + Math.cos(a.mid) * (hi === i ? 5 : 0),
						cy + Math.sin(a.mid) * (hi === i ? 5 : 0),
					];
					return (
						<path
							key={i}
							d={a.d}
							fill={`url(#pie-${i})`}
							stroke="var(--chart-ink2)"
							strokeWidth="1.5"
							transform={`translate(${tx - cx},${ty - cy})`}
							style={{
								opacity: hi == null || hi === i ? 1 : 0.5,
								transition: "opacity .12s, transform .12s",
								cursor: "default",
							}}
							onMouseMove={(e) => {
								setHi(i);
								const pct = Math.round((slices[i].value / total) * 100);
								showTip(e.clientX, e.clientY, [
									{ text: slices[i].label, color: hex(slices[i].color), weight: 600 },
									{
										text: `${fmt(slices[i].value, slices[i].unit ?? unit)} · ${pct}%`,
										mono: true,
										color: HEX.dim,
									},
								]);
							}}
						/>
					);
				})}
			</svg>
			<Legend items={slices.map((s) => ({ color: s.color, label: s.label }))} />
		</div>
	);
}

// ── line chart with crosshair + index tooltip ───────────────────────────────
export function LineChart({
	data,
	series,
	footer,
	height = 130,
}: {
	data: Record<string, number>[];
	series: { key: string; label: string; color: string }[];
	footer?: (row: Record<string, number>) => TipLine[];
	height?: number;
}) {
	const ref = useRef<SVGSVGElement>(null);
	const [hi, setHi] = useState<number | null>(null);
	if (!data.length) return <svg viewBox={`0 0 300 ${height}`} width="100%" height={height} />;
	const W = 300,
		H = height,
		pad = 8;
	const xs = data.map((_, i) => pad + (i / Math.max(data.length - 1, 1)) * (W - 2 * pad));
	const allV = data.flatMap((d) => series.map((s) => d[s.key] ?? 0));
	const maxV = Math.max(...allV, 1);
	const y = (v: number) => H - pad - (v / maxV) * (H - 2 * pad);

	const onMove = (e: React.MouseEvent) => {
		const rect = ref.current!.getBoundingClientRect();
		const mx = ((e.clientX - rect.left) / rect.width) * W;
		let idx = 0,
			bd = Infinity;
		xs.forEach((x, i) => {
			const d = Math.abs(x - mx);
			if (d < bd) {
				bd = d;
				idx = i;
			}
		});
		setHi(idx);
		const row = data[idx];
		const lines: TipLine[] = series
			.map((s) => ({ s, v: row[s.key] ?? 0 }))
			.sort((a, b) => b.v - a.v)
			.map(({ s, v }) => ({ text: `${s.label}  ${fmt(v, "$")}`, mono: true, color: hex(s.color) }));
		if (footer) lines.push(...footer(row));
		showTip(e.clientX, e.clientY, lines);
	};

	const area = (key: string) =>
		`M${xs[0]},${H - pad} ` +
		data.map((d, i) => `L${xs[i]},${y(d[key] ?? 0)}`).join(" ") +
		` L${xs[data.length - 1]},${H - pad} Z`;

	return (
		<svg
			ref={ref}
			className="chart-svg"
			viewBox={`0 0 ${W} ${H}`}
			width="100%"
			height={height}
			onMouseMove={onMove}
			onMouseLeave={() => {
				setHi(null);
				hideTip();
			}}
		>
			<defs>
				{series.map((s) => (
					<linearGradient key={s.key} id={`area-${s.key}`} x1="0" y1="0" x2="0" y2="1">
						<stop offset="0%" stopColor={hex(s.color)} stopOpacity="0.22" />
						<stop offset="100%" stopColor={hex(s.color)} stopOpacity="0" />
					</linearGradient>
				))}
			</defs>
			{series
				.filter((s) => s.key !== "uncached")
				.map((s) => (
					<path key={s.key + "-a"} fill={`url(#area-${s.key})`} stroke="none" d={area(s.key)} />
				))}
			{series.map((s) => (
				<path
					key={s.key}
					fill="none"
					stroke={hex(s.color)}
					strokeWidth="1.75"
					strokeLinecap="round"
					strokeLinejoin="round"
					strokeDasharray={s.key === "uncached" ? "3 3" : undefined}
					d={data.map((d, i) => `${i ? "L" : "M"}${xs[i]},${y(d[s.key] ?? 0)}`).join(" ")}
				/>
			))}
			{hi != null && (
				<>
					<line x1={xs[hi]} y1={pad} x2={xs[hi]} y2={H - pad} stroke={HEX.line2} strokeWidth="1" />
					{series.map((s) => (
						<circle key={s.key} cx={xs[hi]} cy={y(data[hi][s.key] ?? 0)} r="3" fill={hex(s.color)} />
					))}
				</>
			)}
		</svg>
	);
}

function fmt(v: number, unit?: string): string {
	if (unit === "$") return `$${v.toFixed(2)}`;
	if (unit === "tokens") return v >= 1e6 ? `${(v / 1e6).toFixed(2)}M` : v >= 1e3 ? `${(v / 1e3).toFixed(0)}K` : `${v}`;
	return unit ? `${v} ${unit}` : `${v}`;
}
