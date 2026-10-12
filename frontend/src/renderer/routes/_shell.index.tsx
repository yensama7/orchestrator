import { createFileRoute } from "@tanstack/react-router";
import { useUiStore } from "@/stores/ui-store";
import { SimpleRun } from "@/components/views/SimpleRun";
import { Board } from "@/components/Board";

// Simple mode → the brief→progress→result summary. Expert mode → the live Kanban
// board (§P4).
function Index() {
	const mode = useUiStore((s) => s.mode);
	return mode === "simple" ? <SimpleRun /> : <Board />;
}

export const Route = createFileRoute("/_shell/")({ component: Index });
