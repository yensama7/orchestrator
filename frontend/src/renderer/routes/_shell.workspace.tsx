import { createFileRoute } from "@tanstack/react-router";
import { Workspace } from "@/components/views/Workspace";

export const Route = createFileRoute("/_shell/workspace")({ component: Workspace });
