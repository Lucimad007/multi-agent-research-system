"use client";

import { useEffect, useState, type FormEvent } from "react";
import { agents } from "./agents";
import { ReportView } from "./report-view";

type Event = { kind: "delegate" | "ok" | "fail"; agent: string; task: string };

function readEvents(log: string): Event[] {
  const kinds = ["delegate", "ok", "fail"] as const;
  return log.split(/\r?\n/).flatMap((line) => {
    const kind = kinds.find((item) => line.startsWith(`${item} `));
    if (!kind) return [];
    const rest = line.slice(kind.length + 1);
    const split = rest.indexOf(": ");
    if (split === -1) return [{ kind, agent: rest, task: "" }];
    return [{ kind, agent: rest.slice(0, split), task: rest.slice(split + 2) }];
  });
}

function agentState(events: Event[], running: boolean): string {
  const last = events.at(-1);
  if (!last) return "waiting";
  const finished = events.filter((event) => event.kind === "ok").length;
  if (last.kind === "delegate") return running ? "running" : "failed";
  if (last.kind === "fail") return "failed";
  if (running && finished > 0) return `${finished} finished`;
  return "done";
}

export function Board() {
  const [query, setQuery] = useState("");
  const [asked, setAsked] = useState("");
  const [running, setRunning] = useState(false);
  const [log, setLog] = useState("");
  const [report, setReport] = useState("");
  const [runError, setRunError] = useState("");
  const [selected, setSelected] = useState("coordinator");
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => {
    setHydrated(true);
  }, []);

  const events = readEvents(log);
  const started = running || log.length > 0 || report.length > 0 || runError.length > 0;
  const detail = agents.find((item) => item.id === selected) ?? agents[0];

  async function onSearch(event: FormEvent) {
    event.preventDefault();
    const question = query.trim();
    if (!question) return;
    setAsked(question);
    setRunning(true);
    setLog("");
    setReport("");
    setRunError("");
    setSelected("coordinator");
    try {
      const response = await fetch("/api/research", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: question }),
      });
      if (!response.ok || !response.body) {
        setRunError("The research run did not start.");
        return;
      }
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let text = "";
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        text += decoder.decode(value, { stream: true });
        const marker = text.indexOf("__RESULT__");
        setLog(marker === -1 ? text : text.slice(0, marker));
      }
      const marker = text.indexOf("__RESULT__");
      if (marker !== -1) {
        const payload = JSON.parse(text.slice(marker + "__RESULT__".length));
        setReport(payload.answer ?? "");
        setRunError(payload.error ?? "");
      }
    } catch (error) {
      setRunError(error instanceof Error ? error.message : "The research run failed.");
    } finally {
      setRunning(false);
    }
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-3xl flex-col px-6 py-16">
      <p className="font-mono text-[11px] tracking-[0.18em] text-[#a89880] uppercase">Research desk</p>
      <h1 className="mt-3 font-serif text-5xl leading-none text-[#f3eadc]">Search</h1>
      <form onSubmit={onSearch} className="mt-8 flex flex-col gap-3 sm:flex-row">
        <label className="sr-only" htmlFor="research-query">
          Research question
        </label>
        <input
          id="research-query"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="What should the team research?"
          autoComplete="off"
          className="min-w-0 flex-1 rounded-2xl border border-[#3a3228] bg-[#1b1713] px-4 py-3 text-[#f3eadc] outline-none"
        />
        <button
          type="submit"
          disabled={!hydrated || running || query.trim().length === 0}
          suppressHydrationWarning
          className="rounded-2xl bg-[#e2a15a] px-5 py-3 text-sm text-[#14120e] disabled:opacity-50"
        >
          {running ? "Running" : "Search"}
        </button>
      </form>

      {started ? (
        <section className="mt-12">
          <h2 className="font-serif text-3xl text-[#f3eadc]">Agents</h2>
          {asked ? <p className="mt-2 text-sm text-[#cbbba6]">{asked}</p> : null}
          <ol className="mt-6 space-y-3">
            {agents.map((item, index) => {
              const mine = events.filter((entry) => entry.agent === item.id);
              const tasks = mine.filter((entry) => entry.kind !== "ok").map((entry) => entry.task);
              const state = agentState(mine, running);
              return (
                <li key={item.id}>
                  <button
                    type="button"
                    onClick={() => setSelected(item.id)}
                    className={`w-full rounded-2xl border px-4 py-4 text-left ${
                      selected === item.id ? "border-[#e2a15a] bg-[#221c16]" : "border-[#3a3228] bg-[#1b1713]"
                    }`}
                  >
                    <div className="flex items-baseline justify-between gap-4">
                      <h3 className="font-serif text-2xl text-[#f3eadc]">
                        <span className="mr-2 font-mono text-sm text-[#e2a15a]">0{index + 1}</span>
                        {item.name}
                      </h3>
                      <span className="font-mono text-xs text-[#a89880] uppercase">{state}</span>
                    </div>
                    <p className="mt-1 text-sm text-[#cbbba6]">{item.role}</p>
                    {tasks.length > 0 ? (
                      <ul className="mt-3 space-y-1 text-sm text-[#f3eadc]">
                        {tasks.map((task) => (
                          <li key={task}>{task}</li>
                        ))}
                      </ul>
                    ) : null}
                  </button>
                </li>
              );
            })}
          </ol>
          {selected ? (
            <p className="mt-4 text-sm text-[#cbbba6]">
              {detail.name} returns {detail.output}. It will not do this: {detail.refuses}.
            </p>
          ) : null}
        </section>
      ) : null}

      {report ? (
        <section className="mt-12">
          <h2 className="font-serif text-3xl text-[#f3eadc]">Report</h2>
          <p className="mt-2 font-mono text-xs tracking-[0.16em] text-[#e2a15a] uppercase">report-agent</p>
          <ReportView markdown={report} />
        </section>
      ) : null}
      {runError ? <p className="mt-6 text-sm text-[#e2a15a]">{runError}</p> : null}
    </main>
  );
}
