import { createFileRoute } from "@tanstack/react-router";
import { Memory } from "@/components/views/Memory";

export const Route = createFileRoute("/_shell/memory")({ component: Memory });
