// One shared tooltip DOM node for all three chart surfaces. Ported verbatim from
// web/src/hover.ts — opacity-only fade; never transition left/top.
// pointer-events:none. The var(--*) colors it references are the chart palette
// defined in styles.css.

export type TipLine = { text: string; color?: string; mono?: boolean; weight?: number };

let el: HTMLDivElement | null = null;
const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

function ensure(): HTMLDivElement {
	if (el) return el;
	el = document.createElement("div");
	el.setAttribute("role", "status");
	el.style.cssText = [
		"position:fixed",
		"z-index:1000",
		"pointer-events:none",
		"background:var(--chart-ink3)",
		"border:1px solid var(--chart-line2)",
		"border-radius:4px",
		"padding:9px 11px",
		"max-width:270px",
		"font-size:11.5px",
		"line-height:1.7",
		"opacity:0",
		"left:0",
		"top:0",
		reduce ? "transition:none" : "transition:opacity .1s ease",
	].join(";");
	document.body.appendChild(el);
	return el;
}

export function showTip(clientX: number, clientY: number, lines: TipLine[]) {
	const t = ensure();
	t.innerHTML = lines
		.map((l) => {
			const s = [
				l.color ? `color:${l.color}` : "color:var(--chart-bone)",
				l.mono ? "font-family:var(--font-family-mono)" : "font-family:var(--font-family-base)",
				`font-weight:${l.weight ?? 400}`,
			].join(";");
			return `<div style="${s}">${escape(l.text)}</div>`;
		})
		.join("");

	const W = window.innerWidth,
		H = window.innerHeight;
	const rect = t.getBoundingClientRect();
	const w = rect.width || 260,
		h = rect.height || 92;
	// flip to opposite side of cursor near edges, else cursor+(14,14), clamped
	let left = clientX + 14;
	if (clientX + 14 + w > W - 8) left = Math.max(8, clientX - 14 - w);
	left = Math.min(left, Math.max(8, W - w - 8));
	let top = clientY + 14;
	if (clientY + 14 + h > H - 8) top = Math.max(8, clientY - 14 - h);
	t.style.left = `${left}px`;
	t.style.top = `${top}px`;
	t.style.opacity = "1";
	if (reduce) t.style.transition = "none";
}

export function hideTip() {
	if (!el) return;
	if (!reduce) el.style.transition = "opacity .08s ease";
	el.style.opacity = "0";
}

const escape = (s: string) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
