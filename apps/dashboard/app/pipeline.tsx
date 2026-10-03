"use client";

import { Badge } from "@/components/ui/badge";
import { motion, useReducedMotion } from "motion/react";
import type { Agent } from "./agents";

const labels: Record<string, string> = {
  coordinator: "Coordinator",
  "search-agent": "Search",
  "analysis-agent": "Analysis",
  "synthesis-agent": "Synthesis",
  "report-agent": "Report",
};

export function agentLabel(id: string) {
  return labels[id] ?? id;
}

function tone(state: string) {
  if (state === "running") return "info" as const;
  if (state === "done") return "success" as const;
  if (state === "failed") return "destructive" as const;
  if (state.endsWith("finished")) return "warning" as const;
  return "secondary" as const;
}

function frame(state: string) {
  if (state === "running") return "march";
  if (state === "done") return "border border-solid border-success/50";
  if (state === "failed") return "border border-dashed border-danger";
  if (state.endsWith("finished")) return "border border-dashed border-warning";
  return "border border-dashed border-muted-foreground/40";
}

export function Pipeline({
  agents,
  states,
  selected,
  onSelect,
}: {
  agents: Agent[];
  states: string[];
  selected: string;
  onSelect: (id: string) => void;
}) {
  const reduce = useReducedMotion();

  return (
    <div className="relative">
      <div
        className="pointer-events-none absolute top-8 right-[10%] left-[10%] hidden border-t border-dashed border-muted-foreground/40 md:block"
        aria-hidden="true"
      />
      <ol className="grid grid-cols-1 gap-2 md:grid-cols-5">
        {agents.map((agent, index) => {
          const state = states[index] ?? "not started";
          const active = selected === agent.id;
          const live = state === "running";
          return (
            <motion.li
              key={agent.id}
              initial={reduce ? false : { opacity: 0, y: 12 }}
              whileInView={{ opacity: 1, y: 0 }}
              whileHover={reduce ? undefined : { y: -3 }}
              viewport={{ once: true, amount: 0.6 }}
              transition={{ type: "spring", stiffness: 380, damping: 28, delay: index * 0.04 }}
            >
              <button
                type="button"
                onClick={() => onSelect(agent.id)}
                aria-pressed={active}
                className={`relative w-full rounded-2xl bg-card/80 px-4 py-4 text-left transition-colors duration-500 ease-[cubic-bezier(0.16,1,0.3,1)] active:scale-[0.98] ${frame(state)} ${
                  active ? "shadow-[var(--shadow)]" : ""
                } ${live ? "shimmer" : ""}`}
              >
                <Badge variant={tone(state)} className="mb-3">
                  {live ? <span className="size-1.5 animate-pulse rounded-full bg-info" /> : null}
                  {state.charAt(0).toUpperCase() + state.slice(1)}
                </Badge>
                <span className="block text-lg tracking-tight text-foreground">{agentLabel(agent.id)}</span>
              </button>
            </motion.li>
          );
        })}
      </ol>
    </div>
  );
}
