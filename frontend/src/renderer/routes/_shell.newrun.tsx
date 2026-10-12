import { createFileRoute } from "@tanstack/react-router";
import { NewRun } from "@/components/views/NewRun";

export const Route = createFileRoute("/_shell/newrun")({ component: NewRun });
