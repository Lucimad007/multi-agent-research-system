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
  if (!liveRun && (state === "not started" || state === "waiting")) return "";
  if (state === "running") return "Working";
  if (state === "done") return "Done";
  if (state === "failed") return "Stopped";
  if (state.endsWith("finished")) return state.replace("finished", "done");
  return "Waiting";
}

function tone(state: string) {
  if (state === "running" || state.endsWith("finished")) return "text-info";
  if (state === "done") return "text-success";
  if (state === "failed") return "text-danger";
  return "text-muted-foreground";
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
  const busy = states.some((state) => state === "running" || state.endsWith("finished"));
  const portion = Math.min(1, (done + (busy ? 0.35 : 0)) / Math.max(agents.length, 1));

  return (
    <div>
      <div className="h-1 overflow-hidden rounded-full bg-foreground/10" aria-hidden="true">
        <motion.div
          className="h-full origin-left bg-info"
          initial={false}
          animate={{ scaleX: portion }}
          transition={reduce ? { duration: 0 } : { duration: 0.6, ease: [0.16, 1, 0.3, 1] }}
          style={{ width: "100%" }}
        />
      </div>
      <ol className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-5">
        {agents.map((agent, index) => {
          const state = states[index] ?? "not started";
          const active = selected === agent.id;
          const label = statusLabel(state, liveRun);
          return (
            <li key={agent.id}>
              <button
                type="button"
                onClick={() => onSelect(agent.id)}
                aria-pressed={active}
                className={`w-full rounded-xl px-3 py-3 text-left transition-colors duration-300 ease-[cubic-bezier(0.16,1,0.3,1)] active:scale-[0.98] ${
                  active ? "bg-card" : "hover:bg-card/60"
                }`}
              >
                <span className="block text-sm tracking-tight text-foreground">{agentLabel(agent.id)}</span>
                {label ? (
                  <span className={`mt-1 block font-mono text-[11px] ${tone(state)}`}>{label}</span>
                ) : (
                  <span className="mt-1 block h-4" />
                )}
              </button>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
