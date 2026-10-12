import { createFileRoute } from "@tanstack/react-router";
import { ViewPlaceholder } from "@/components/ViewPlaceholder";

export const Route = createFileRoute("/_shell/settings")({
	component: () => <ViewPlaceholder name="Settings" />,
});
