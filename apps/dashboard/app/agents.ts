export type Agent = {
  id: string;
  name: string;
  role: string;
  when: string;
  tools: string;
  refuses: string;
  output: string;
  steps: string[];
};

export const agents: Agent[] = [
  {
    id: "coordinator",
    name: "coordinator",
    role: "Delegation and assembly",
    when: "Once, at the start of a request",
    tools: "None. It only calls the other agents.",
    refuses: "Search, analysis, synthesis, and writing the report",
    output: "The report markdown, unchanged",
    steps: [
      "Split the request into one to three search topics.",
      "Send each topic to search-agent.",
      "Send each source list to analysis-agent.",
      "Send every completed analysis to synthesis-agent in one delegation.",
      "Send the full synthesis, URLs included, to report-agent.",
      "Return the report exactly as report-agent wrote it.",
    ],
  },
  {
    id: "search-agent",
    name: "search-agent",
    role: "Web search",
    when: "Once per topic",
    tools: "web_search",
    refuses: "Analysis and conclusions",
    output: "Sources with title, URL, publication date when available, and a two-sentence summary",
    steps: [
      "Search the public web for the assigned topic.",
      "Keep at least five distinct sources.",
      "Record title, URL, date, and summary.",
      "Stop. Do not interpret the sources.",
    ],
  },
  {
    id: "analysis-agent",
    name: "analysis-agent",
    role: "Findings from one source set",
    when: "Once per search result",
    tools: "None",
    refuses: "Web search and resolving disagreements",
    output: "Claims, disagreements, and gaps, each claim tied to source titles and URLs",
    steps: [
      "Read only the sources for one topic.",
      "Tag every claim with the title and URL that support it.",
      "Report disagreements with both positions attributed.",
      "List gaps. Leave conflicts unresolved for synthesis.",
    ],
  },
  {
    id: "synthesis-agent",
    name: "synthesis-agent",
    role: "One picture across analyses",
    when: "Once, after every analysis",
    tools: "None",
    refuses: "Web search and new sources",
    output: "Picture, conclusions with confidence and URLs, resolved conflicts, and every gap",
    steps: [
      "Read every analysis in full.",
      "Prefer corroborated, recent, and primary sources when a conflict can be resolved.",
      "If it cannot be resolved, keep both positions. Do not average numbers.",
      "Mark each conclusion high, medium, or low, and carry every gap forward.",
    ],
  },
  {
    id: "report-agent",
    name: "report-agent",
    role: "Cited Markdown report",
    when: "Once, as the final step",
    tools: "None",
    refuses: "Web search and invented URLs",
    output: "Title, executive summary, findings, conflicting evidence, confidence, and numbered references",
    steps: [
      "Cite only URLs present in the synthesis.",
      "End every finding with a citation such as [1] or [2, 3].",
      "Use every reference number at least once.",
      "Put unsourced claims under limitations instead of inventing a URL.",
    ],
  },
];
