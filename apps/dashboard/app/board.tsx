"use client";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Separator } from "@/components/ui/separator";
import { RetroGrid } from "@/components/retro-grid";
import { ArrowRight, MagnifyingGlass } from "@phosphor-icons/react";
import { useEffect, useState, type FormEvent } from "react";
import { agents } from "./agents";
import { Field } from "./field";
import { Header } from "./header";
import { agentLabel, Pipeline } from "./pipeline";
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
  if (!last) return "not started";
  if (last.kind === "delegate") return running ? "running" : "failed";
  if (last.kind === "fail") return "failed";
  return "done";
}

function tasksFor(events: Event[]): string[] {
  const tasks = events.filter((event) => event.kind !== "ok" && event.task).map((event) => event.task);
  return [...new Set(tasks)].slice(-6);
}

function wordCount(value: string) {
  const trimmed = value.trim();
  if (!trimmed) return 0;
  return trimmed.split(/\s+/).length;
}

const examples = [
  "Iranian rial exchange rate versus the US dollar",
  "Factors that move the rial against the dollar",
];

export function Board() {
  const [query, setQuery] = useState("");
  const [asked, setAsked] = useState("");
  const [running, setRunning] = useState(false);
  const [log, setLog] = useState("");
  const [report, setReport] = useState("");
  const [runError, setRunError] = useState("");
  const [selected, setSelected] = useState("coordinator");
  const [hydrated, setHydrated] = useState(false);
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    setHydrated(true);
    document.getElementById("research-query")?.focus();
  }, []);

  const events = readEvents(log);
  const words = wordCount(query);
  const states = agents.map((agent) => agentState(events.filter((entry) => entry.agent === agent.id), running));
  const detail = agents.find((item) => item.id === selected) ?? agents[0];
  const liveTasks = tasksFor(events.filter((entry) => entry.agent === detail.id));

  useEffect(() => {
    if (!running) return;
    const started = Date.now();
    const timer = window.setInterval(() => {
      setElapsed(Math.floor((Date.now() - started) / 1000));
    }, 1000);
    return () => window.clearInterval(timer);
  }, [running]);

  useEffect(() => {
    if (!running) return;
    const last = readEvents(log).at(-1);
    if (last) setSelected(last.agent);
  }, [log, running]);

  useEffect(() => {
    if (!report) return;
    document.getElementById("report")?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [report]);

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
    setElapsed(0);
    document.getElementById("method")?.scrollIntoView({ behavior: "smooth", block: "start" });
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
    <>
      <Field />
      <div className="grain" aria-hidden="true" />
      <a href="#desk" className="skip-link">
        Skip to search
      </a>
      <Header />
      <main className="relative z-10">
        <section id="desk" className="relative overflow-hidden px-4 pt-28 pb-16">
          <RetroGrid />
          <div className="relative z-10 mx-auto max-w-3xl text-center">
            <p className="mx-auto w-fit rounded-full border border-border bg-card/80 px-3 py-1 text-xs text-muted-foreground">
              Research desk
            </p>
            <h1 className="mt-6 text-4xl leading-[1.05] font-medium tracking-tight text-balance text-foreground md:text-6xl">
              A cited report from one question.
            </h1>
            <p className="mx-auto mt-4 max-w-[42ch] text-lg leading-relaxed text-muted-foreground">
              Search, analysis, and synthesis run in order. The report keeps every source.
            </p>
            <form
              onSubmit={onSearch}
              className="mx-auto mt-8 max-w-xl rounded-2xl border border-border bg-card p-2 text-left shadow-[var(--shadow)]"
            >
              <label htmlFor="research-query" className="sr-only">
                Your question
              </label>
              <div className="flex items-center gap-2 rounded-xl bg-background/60 px-3">
                <MagnifyingGlass className="shrink-0 text-muted-foreground" size={18} weight="light" />
                <Input
                  id="research-query"
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  placeholder="Ask for a fact, a rate, or a comparison"
                  autoComplete="off"
                  className="h-12 border-0 bg-transparent px-0 text-base shadow-none focus-visible:ring-0 md:text-base"
                />
                <Button
                  type="submit"
                  size="sm"
                  disabled={!hydrated || running || words < 3}
                  suppressHydrationWarning
                  className="rounded-full"
                >
                  {running ? "Working" : "Research"}
                  <ArrowRight size={14} weight="light" />
                </Button>
              </div>
              <Separator className="my-1" />
              <div className="px-1 py-1">
                {examples.map((example) => (
                  <button
                    key={example}
                    type="button"
                    onClick={() => {
                      setQuery(example);
                      document.getElementById("research-query")?.focus();
                    }}
                    className="flex w-full items-center gap-3 rounded-lg px-3 py-2 text-left text-sm text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
                  >
                    <ArrowRight size={14} weight="light" />
                    <span>{example}</span>
                  </button>
                ))}
              </div>
              <div className="flex items-center justify-between px-3 pt-1 pb-2 text-xs text-muted-foreground">
                <span>Enter to research</span>
                <span className={words >= 3 ? "text-success" : ""} aria-live="polite">
                  {words >= 3 ? "Ready" : `${words}/3 words`}
                </span>
              </div>
              {runError ? <p className="px-3 pb-2 text-sm text-danger">{runError}</p> : null}
            </form>
          </div>
        </section>

        <section id="method" className="mx-auto max-w-[1400px] scroll-mt-24 px-4 pt-16 pb-8">
          <div className="flex items-end justify-between gap-6">
            <h2 className="max-w-xl text-4xl leading-tight font-medium tracking-tight text-balance text-[var(--ink)] md:text-5xl">
              {running ? "Working through the steps." : "Five steps, then the report."}
            </h2>
            {running ? (
              <p className="font-mono text-sm text-info tabular-nums" aria-live="polite">
                {Math.floor(elapsed / 60)}:{String(elapsed % 60).padStart(2, "0")}
              </p>
            ) : null}
          </div>
          <p className="mt-4 max-w-[52ch] text-lg leading-relaxed text-[var(--muted)]">
            {asked || "Submit a question and this track shows which step is working."}
          </p>
          <div className="mt-10">
            <Pipeline
              agents={agents}
              states={states}
              selected={selected}
              liveRun={running}
              onSelect={setSelected}
            />
          </div>
          <Card className="rounded-t-none border-border bg-card shadow-none">
            <CardContent className="pt-5">
              <h3 className="text-xl tracking-tight text-foreground">{agentLabel(detail.id)}</h3>
              {running && liveTasks.length === 0 ? (
                <div className="mt-4 space-y-3" aria-hidden="true">
                  <div className="skeleton shimmer h-4 w-4/5" />
                  <div className="skeleton shimmer h-4 w-3/5" />
                </div>
              ) : null}
              {liveTasks.length > 0 ? (
                <ul className="mt-4 space-y-2">
                  {liveTasks.map((task) => (
                    <li key={task} className="text-sm leading-6 text-foreground">
                      {task}
                    </li>
                  ))}
                </ul>
              ) : null}
              {!running ? (
                <p className="mt-2 max-w-[68ch] text-sm leading-6 text-muted-foreground">
                  {detail.role}. {detail.output}.
                </p>
              ) : null}
              <details className="mt-4">
                <summary className="cursor-pointer text-sm text-foreground">What this step does</summary>
                <ul className="mt-3 grid gap-2 sm:grid-cols-2">
                  {detail.steps.map((step) => (
                    <li key={step} className="text-sm leading-6 text-muted-foreground">
                      {step}
                    </li>
                  ))}
                </ul>
              </details>
            </CardContent>
          </Card>
        </section>

        <section id="report" className="mx-auto max-w-[1400px] scroll-mt-28 px-4 py-16">
          <h2 className="text-4xl font-medium tracking-tight text-[var(--ink)] md:text-5xl">
            {running ? "The report is written last." : "The report opens here."}
          </h2>
          {report ? (
            <ReportView markdown={report} />
          ) : running ? (
            <div className="mt-8 max-w-2xl space-y-3" aria-hidden="true">
              <div className="skeleton shimmer h-8 w-2/5" />
              <div className="skeleton shimmer h-4 w-full" />
              <div className="skeleton shimmer h-4 w-11/12" />
              <div className="skeleton shimmer h-4 w-4/5" />
            </div>
          ) : (
            <p className="mt-4 max-w-[48ch] text-lg leading-relaxed text-muted-foreground">
              After the last step, the cited report fills this space.
            </p>
          )}
        </section>

        <footer className="mx-auto max-w-[1400px] px-4 py-16">
          <p className="max-w-[48ch] text-sm leading-6 text-[var(--muted)]">
            Sources in the report come from the search. Nothing else is cited.
          </p>
        </footer>
      </main>
    </>
  );
}
