"use client";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Separator } from "@/components/ui/separator";
import { ArrowRight } from "@phosphor-icons/react";
import Image from "next/image";
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
  const finished = events.filter((event) => event.kind === "ok").length;
  if (last.kind === "delegate") return running ? "running" : "failed";
  if (last.kind === "fail") return "failed";
  if (running && finished > 0) return `${finished} finished`;
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
        <section id="desk" className="mx-auto max-w-3xl px-4 pt-24">
          <h1 className="text-4xl leading-tight font-medium tracking-tight text-balance text-[var(--ink)] md:text-5xl">
            Put the question here.
          </h1>
          <p className="mt-4 max-w-[46ch] text-lg leading-relaxed text-[var(--muted)]">
            The steps below run by themselves. The report opens underneath.
          </p>
          <form onSubmit={onSearch} className="mt-8">
            <label htmlFor="research-query" className="text-sm text-[var(--ink)]">
              Your question
            </label>
            <div className="mt-2 flex flex-col gap-3 sm:flex-row sm:items-center">
              <Input
                id="research-query"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Write the question in this box"
                autoComplete="off"
                className="h-12 rounded-2xl border-dashed bg-card px-4 text-base md:text-base"
              />
              <Button
                type="submit"
                size="lg"
                disabled={!hydrated || running || words < 3}
                suppressHydrationWarning
                variant={words >= 3 ? "default" : "outline"}
                className={`h-12 rounded-full pr-2 pl-5 ${words >= 3 ? "" : "border-dashed"}`}
              >
                <span>{running ? "Running" : "Research"}</span>
                <span className="grid size-8 place-items-center rounded-full bg-primary-foreground/15 transition-transform duration-500 ease-[cubic-bezier(0.16,1,0.3,1)] group-hover/button:translate-x-0.5">
                  <ArrowRight size={16} weight="light" />
                </span>
              </Button>
            </div>
            <p className={`mt-2 text-sm ${words >= 3 ? "text-success" : "text-muted-foreground"}`} aria-live="polite">
              {words >= 3 ? "This is enough to start." : `Add ${3 - words} more ${3 - words === 1 ? "word" : "words"}.`}
            </p>
            {runError ? <p className="mt-2 text-sm text-danger">{runError}</p> : null}
            <Separator className="my-4 h-px bg-transparent data-horizontal:border-t data-horizontal:border-dashed" decorative />
            <div className="flex flex-col gap-2 sm:flex-row">
              {examples.map((example) => (
                <Button
                  key={example}
                  type="button"
                  variant="outline"
                  onClick={() => {
                    setQuery(example);
                    document.getElementById("research-query")?.focus();
                  }}
                  className="h-auto justify-start rounded-2xl border-dashed px-4 py-3 text-left whitespace-normal"
                >
                  {example}
                </Button>
              ))}
            </div>
          </form>
        </section>

        <section id="method" className="mx-auto max-w-[1400px] scroll-mt-24 px-4 pt-16 pb-8">
          <h2 className="max-w-xl text-4xl leading-tight font-medium tracking-tight text-balance text-[var(--ink)] md:text-5xl">
            Progress shows here.
          </h2>
          <p className="mt-4 max-w-[48ch] text-lg leading-relaxed text-[var(--muted)]">
            {asked ? asked : "You do not assign these steps. They start after you submit the question."}
          </p>
          <div className="mt-12">
            <Pipeline agents={agents} states={states} selected={selected} onSelect={setSelected} />
          </div>
          <div className="mt-8 grid items-start gap-8 lg:grid-cols-12">
            <Card className="border border-dashed bg-card/80 shadow-none ring-0 lg:col-span-7">
            <CardContent>
              <h3 className="text-3xl tracking-tight text-[var(--ink)]">{agentLabel(detail.id)}</h3>
              <p className="mt-3 max-w-[62ch] text-base leading-relaxed text-[var(--muted)]">
                {detail.role}. {detail.when}.
              </p>
              <p className="mt-3 max-w-[62ch] text-base leading-relaxed text-[var(--ink)]">{detail.output}.</p>
              <p className="mt-3 max-w-[62ch] text-base leading-relaxed text-[var(--ink)]">
                Does not: {detail.refuses}.
              </p>
              {liveTasks.length > 0 ? (
                <div className="mt-8">
                  <h4 className="text-lg text-[var(--ink)]">This run</h4>
                  <ul className="mt-3 space-y-2">
                    {liveTasks.map((task) => (
                      <li key={task} className="text-sm leading-6 text-[var(--muted)]">
                        {task}
                      </li>
                    ))}
                  </ul>
                </div>
              ) : (
                <p className="mt-8 text-sm leading-6 text-[var(--muted)]">
                  Click a step to read it. Work from the question shows up in this panel.
                </p>
              )}
              <details className="mt-6">
                <summary className="cursor-pointer text-sm text-[var(--ink)]">What this step does</summary>
                <ul className="mt-4 grid gap-3 sm:grid-cols-2">
                  {detail.steps.map((step) => (
                    <li key={step} className="text-sm leading-6 text-[var(--muted)]">
                      {step}
                    </li>
                  ))}
                </ul>
              </details>
            </CardContent>
            </Card>
            <div className="lg:col-span-5">
              <div className="rounded-[1.75rem] bg-[var(--bezel)] p-2 ring-1 ring-[var(--line)]">
                <div className="relative aspect-[4/3] overflow-hidden rounded-[1.35rem]">
                  <Image
                    src="/paper-layers.jpg"
                    alt="Stacked sheets with a thin green light between the layers"
                    fill
                    priority
                    sizes="(min-width: 1024px) 36vw, 100vw"
                    className="object-cover"
                  />
                </div>
              </div>
            </div>
          </div>
        </section>

        <section id="report" className="mx-auto max-w-[1400px] scroll-mt-28 px-4 py-16">
          <h2 className="text-4xl font-medium tracking-tight text-[var(--ink)] md:text-5xl">The report opens here.</h2>
          {report ? (
            <ReportView markdown={report} />
          ) : (
            <Card className="mt-6 border border-dashed bg-transparent shadow-none ring-0">
              <CardContent>
                <p className="max-w-[48ch] text-lg leading-relaxed text-muted-foreground">
                  {running
                    ? "Still working. The summary, findings, conflicts, limits, and sources will replace this note."
                    : "Nothing here yet. After the last step, the cited report fills this space."}
                </p>
              </CardContent>
            </Card>
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
