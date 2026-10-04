"use client";

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

function statusLabel(state: string, liveRun: boolean) {
  if (!liveRun && (state === "not started" || state === "waiting")) return "Ready";
  if (state === "running") return "Working";
  if (state === "done") return "Done";
  if (state === "failed") return "Stopped";
  return "Waiting";
}

function mark(state: string) {
  if (state === "running") return "bg-info";
  if (state === "done") return "bg-success";
  if (state === "failed") return "bg-danger";
  return "bg-foreground/15";
}

export function Pipeline({
  agents,
  states,
  selected,
  liveRun,
  onSelect,
}: {
  agents: Agent[];
  states: string[];
  selected: string;
  liveRun: boolean;
  onSelect: (id: string) => void;
}) {
  const reduce = useReducedMotion();
  const done = states.filter((state) => state === "done").length;
  const working = states.filter((state) => state === "running").length;
  const portion = Math.min(1, (done + working * 0.45) / Math.max(agents.length, 1));

  return (
    <div className="overflow-hidden rounded-t-2xl border border-b-0 border-border bg-card">
      <div className="h-1 bg-foreground/10" aria-hidden="true">
        <motion.div
          className="h-full bg-progress"
          initial={false}
          animate={{ width: `${portion * 100}%` }}
          transition={reduce ? { duration: 0 } : { duration: 0.6, ease: [0.16, 1, 0.3, 1] }}
        />
      </div>
      <ol className="grid grid-cols-2 sm:grid-cols-5">
        {agents.map((agent, index) => {
          const state = states[index] ?? "not started";
          const active = selected === agent.id;
          return (
            <li key={agent.id} className="border-border sm:border-r sm:last:border-r-0">
              <button
                type="button"
                onClick={() => onSelect(agent.id)}
                aria-pressed={active}
                className={`flex h-full min-h-24 w-full flex-col justify-between px-4 py-4 text-left transition-colors duration-300 ease-[cubic-bezier(0.16,1,0.3,1)] active:scale-[0.99] ${
                  active ? "bg-background" : "hover:bg-background/50"
                }`}
              >
                <span className={`block h-1 w-8 rounded-full ${mark(state)}`} />
                <span>
                  <span className="mt-4 block text-sm font-medium tracking-tight text-foreground">
                    {agentLabel(agent.id)}
                  </span>
                  <span className="mt-1 block text-xs text-muted-foreground">
                    {statusLabel(state, liveRun)}
                  </span>
                </span>
              </button>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
