import { Moon, Sun } from "lucide-react";
import type { ReactNode } from "react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { useUiStore, type Mode } from "@/stores/ui-store";

const MODES: Mode[] = ["simple", "expert"];

// Title + spend-rail slot + Simple/Expert + theme toggle. Faithful to the
// reference's one app topbar, minus the Electron window chrome.
export function ShellTopbar({ title, spendRail }: { title: string; spendRail?: ReactNode }) {
	const mode = useUiStore((s) => s.mode);
	const setMode = useUiStore((s) => s.setMode);
	const theme = useUiStore((s) => s.theme);
	const toggleTheme = useUiStore((s) => s.toggleTheme);

	return (
		<header className="flex h-12 shrink-0 items-center gap-4 border-b border-border px-4">
			<h1 className="text-sm font-medium">{title}</h1>
			<div className="ml-auto flex items-center gap-3">
				{spendRail}
				{/* Simple/Expert segmented toggle. */}
				<div className="flex items-center rounded-md bg-muted p-0.5">
					{MODES.map((m) => (
						<button
							key={m}
							type="button"
							onClick={() => setMode(m)}
							aria-pressed={mode === m}
							className={cn(
								"rounded-sm px-2.5 py-1 text-xs capitalize transition-colors",
								mode === m
									? "bg-background text-foreground shadow-sm"
									: "text-muted-foreground hover:text-foreground",
							)}
						>
							{m}
						</button>
					))}
				</div>
				<Button
					variant="ghost"
					size="icon-sm"
					onClick={toggleTheme}
					aria-label={`Switch to ${theme === "light" ? "dark" : "light"} theme`}
				>
					{theme === "light" ? <Moon /> : <Sun />}
				</Button>
			</div>
		</header>
	);
}
