import { createFileRoute } from "@tanstack/react-router";
import { useUiStore } from "@/stores/ui-store";
import { SimpleRun } from "@/components/views/SimpleRun";
import { ViewPlaceholder } from "@/components/ViewPlaceholder";

// Simple mode → the brief→progress→result summary. Expert mode → the Board,
// which lands in Phase 4; until then a placeholder keeps the route runnable.
function Index() {
	const mode = useUiStore((s) => s.mode);
	return mode === "simple" ? <SimpleRun /> : <ViewPlaceholder name="Board" />;
}

export const Route = createFileRoute("/_shell/")({ component: Index });
