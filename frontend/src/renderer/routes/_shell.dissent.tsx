import { createFileRoute } from "@tanstack/react-router";
import { Dissent } from "@/components/views/Dissent";

export const Route = createFileRoute("/_shell/dissent")({ component: Dissent });
