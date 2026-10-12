import { useRun } from "@/hooks/use-run";
import { cn } from "@/lib/utils";

// Bottom activity strip — the live SSE ticker feed. Replaces the old <footer
// className="ticker">. Dims + shows a "reconnecting" marker while the stream is
// down (the REST fallback poll is still carrying state underneath).
export function Ticker() {
	const { events, stale } = useRun();
	return (
		<footer
			className={cn(
				"flex h-8 shrink-0 items-center gap-5 overflow-x-auto border-t border-border bg-sidebar px-4 text-xs whitespace-nowrap",
				stale && "opacity-60",
			)}
		>
			<span
				className="size-2 shrink-0 rounded-full bg-primary motion-safe:animate-status-pulse"
				aria-hidden
			/>
			{stale && (
				<span className="text-muted-foreground">
					<span className="mr-1.5 italic text-passive">reconnecting</span>
				</span>
			)}
			{events.map((e, i) => (
				<span key={i} className="text-muted-foreground">
					<span className="mr-1.5 italic text-passive">{e.key}</span>
					{e.text}
				</span>
			))}
		</footer>
	);
}
