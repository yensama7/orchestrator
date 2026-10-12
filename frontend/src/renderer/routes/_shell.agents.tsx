import { createFileRoute } from "@tanstack/react-router";
import { Agents } from "@/components/views/Agents";

export const Route = createFileRoute("/_shell/agents")({ component: Agents });
