import { useEffect } from "react";
import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useRunStore } from "@/stores/run-store";

// Per-run detail replaces the old `?run=` selection: visiting /run/:id pins that
// run into the store so the shell + every view scope to it, then lands on the
// board. A richer standalone detail page lands with the Board in Phase 4.
export const Route = createFileRoute("/_shell/run/$runId")({
	component: RunRedirect,
});

function RunRedirect() {
	const { runId } = Route.useParams();
	const setSelectedRun = useRunStore((s) => s.setSelectedRun);
	const navigate = useNavigate();
	useEffect(() => {
		setSelectedRun(runId);
		navigate({ to: "/" });
	}, [runId, setSelectedRun, navigate]);
	return null;
}
