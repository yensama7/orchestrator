import { createFileRoute } from "@tanstack/react-router";
import { ViewPlaceholder } from "@/components/ViewPlaceholder";

// Per-run detail, replaces the old `?run=` selection. Real view in Phase 3.
export const Route = createFileRoute("/_shell/run/$runId")({
	component: () => {
		const { runId } = Route.useParams();
		return <ViewPlaceholder name={`Run ${runId}`} />;
	},
});
