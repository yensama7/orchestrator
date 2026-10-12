import { createFileRoute } from "@tanstack/react-router";
import { Settings } from "@/components/views/Settings";

export const Route = createFileRoute("/_shell/settings")({ component: Settings });
