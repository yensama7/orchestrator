import { createFileRoute } from "@tanstack/react-router";
import { ViewPlaceholder } from "@/components/ViewPlaceholder";

// Board in Expert, Simple summary in Simple mode — branch lands in Phase 3/4.
export const Route = createFileRoute("/_shell/")({
	component: () => <ViewPlaceholder name="Board" />,
});
