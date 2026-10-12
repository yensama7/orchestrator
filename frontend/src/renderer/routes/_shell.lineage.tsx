import { createFileRoute } from "@tanstack/react-router";
import { Lineage } from "@/components/views/Lineage";

export const Route = createFileRoute("/_shell/lineage")({ component: Lineage });
