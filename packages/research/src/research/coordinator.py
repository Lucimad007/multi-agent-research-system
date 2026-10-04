from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from pydantic import ValidationError

from research.agent import resolve_model
from research.analysis import run_analysis
from research.report import _fallback_report, run_report
from research.schema import ResearchPlan
from research.search import AgentRunError, BudgetExceeded, SearchAgentOptions
from research.synthesis import _fallback_synthesis, run_synthesis
from research.tools import collect_sources


class CoordinatorState(TypedDict, total=False):
    request: str
    subtasks: list[str]
    index: int
    have_sources: bool
    sources: dict | None
    analyses: list[dict]
    synthesis: dict | None
    answer: str | None
    handoffs: list[dict]
    reports: list[dict]
    error: str | None


def create_coordinator(options: SearchAgentOptions | None = None) -> CompiledStateGraph:
    """Coordinator node routes every handoff. Specialists only answer the coordinator."""
    selected = options or SearchAgentOptions()
    graph = StateGraph(CoordinatorState)
    graph.add_node("coordinator", lambda state: _coordinator(state, selected))
    graph.add_node("search", _search)
    graph.add_node("analysis", _analysis)
    graph.add_node("synthesis", _synthesis)
    graph.add_node("report", _report)
    graph.add_edge(START, "coordinator")
    graph.add_conditional_edges(
        "coordinator",
        _route,
        {
            "search": "search",
            "analysis": "analysis",
            "synthesis": "synthesis",
            "report": "report",
            "end": END,
        },
    )
    for specialist in ("search", "analysis", "synthesis", "report"):
        graph.add_edge(specialist, "coordinator")
    return graph.compile()


def run_coordinator(request: str, options: SearchAgentOptions | None = None) -> dict:
    state = create_coordinator(options).invoke({"request": request, "reports": [], "handoffs": []})
    if state.get("error") and not state.get("answer"):
        raise AgentRunError("coordinator", state["error"])
    return {
        "answer": state.get("answer"),
        "handoffs": state.get("handoffs") or [],
        "reports": state.get("reports") or [],
        "error": state.get("error"),
    }


def _route(state: CoordinatorState) -> str:
    """The coordinator chooses the next specialist. Specialists never choose."""
    subtasks = state.get("subtasks") or []
    index = state.get("index", 0)
    analyses = state.get("analyses") or []
    if index < len(subtasks) and len(analyses) == index:
        return "analysis" if state.get("have_sources") else "search"
    if not state.get("synthesis"):
        return "synthesis"
    if not state.get("answer"):
        return "report"
    return "end"


def _coordinator(state: CoordinatorState, options: SearchAgentOptions) -> CoordinatorState:
    if state.get("subtasks"):
        return {}
    planned = _plan(state, options)
    return {
        "subtasks": planned.get("subtasks") or [],
        "index": 0,
        "analyses": [],
        "have_sources": False,
        "sources": None,
    }


def _plan(state: CoordinatorState, options: SearchAgentOptions) -> CoordinatorState:
    request = state["request"].strip() or "research question"
    if len(request.split()) < 3:
        return _planned([request])
    prompt = (
        "Return 1 or 2 short web search queries that can retrieve the fact asked. "
        "If the request asks for a price, rate, or other number, "
        "the first query must look up that figure. "
        "Do not answer the request. Do not prefix a query with the word search.\n"
        f"Request:\n{request}"
    )
    names = [options.model]
    if options.fallback_model != options.model:
        names.append(options.fallback_model)
    for name in names:
        try:
            chat = resolve_model(name)
            if isinstance(chat, str):
                raise AgentRunError("coordinator", "coordinator requires a chat model instance")
            planned = chat.with_structured_output(ResearchPlan).invoke(prompt)
            raw = ResearchPlan.model_validate(planned).subtasks
            subtasks = [item for item in (_topic(item) for item in raw) if item][:2]
            if subtasks:
                return _planned(subtasks)
        except (BudgetExceeded, ValidationError, AgentRunError, Exception):
            continue
    return _planned([request])


def _search(state: CoordinatorState) -> CoordinatorState:
    topic = state["subtasks"][state.get("index", 0)]
    _print("search-agent", topic)
    sources = _sources_for(topic)
    print(f"ok search-agent: {topic}", flush=True)
    handoffs = _note(state, "search-agent", topic)
    return {"sources": sources, "have_sources": True, "handoffs": handoffs}


def _analysis(state: CoordinatorState) -> CoordinatorState:
    topic = state["subtasks"][state.get("index", 0)]
    task = f"analyze sources for {topic}"
    _print("analysis-agent", task)
    analysis = _analysis_for(topic, state.get("sources") or {}, state.get("request") or "")
    print(f"ok analysis-agent: {task}", flush=True)
    analyses = list(state.get("analyses") or [])
    analyses.append(
        {"topic": topic, "question": state.get("request") or "", **analysis}
    )
    handoffs = _note(state, "analysis-agent", task)
    return {
        "analyses": analyses,
        "sources": None,
        "have_sources": False,
        "index": state.get("index", 0) + 1,
        "handoffs": handoffs,
    }


def _synthesis(state: CoordinatorState) -> CoordinatorState:
    task = "synthesize every completed analysis"
    _print("synthesis-agent", task)
    synthesis = _synthesis_for(state.get("analyses") or [])
    print(f"ok synthesis-agent: {task}", flush=True)
    return {"synthesis": synthesis, "handoffs": _note(state, "synthesis-agent", task)}


def _report(state: CoordinatorState) -> CoordinatorState:
    task = "write the research report from the full synthesis"
    _print("report-agent", task)
    synthesis = state.get("synthesis") or {}
    try:
        markdown = run_report(synthesis)
    except Exception:
        markdown = _fallback_report(synthesis)
    print(f"ok report-agent: {task}", flush=True)
    print("ok coordinator: return the report unchanged", flush=True)
    handoffs = _note(state, "report-agent", task)
    handoffs.append({"agent": "coordinator", "task": "return the report unchanged"})
    reports = [
        {"topic": item.get("topic"), "analysis": item}
        for item in state.get("analyses") or []
    ]
    return {"answer": markdown, "handoffs": handoffs, "reports": reports, "error": None}


def _note(state: CoordinatorState, agent: str, task: str) -> list[dict]:
    handoffs = list(state.get("handoffs") or [])
    handoffs.append({"agent": agent, "task": task})
    return handoffs


def _planned(subtasks: list[str]) -> CoordinatorState:
    _print("coordinator", "split the request into search subtasks")
    for topic in subtasks:
        _print("coordinator", f"planned search: {topic}")
    print("ok coordinator: split the request into search subtasks", flush=True)
    return {"subtasks": subtasks, "error": None}


def _sources_for(topic: str) -> dict:
    trimmed = []
    for source in collect_sources(topic)[:5]:
        trimmed.append(
            {
                "title": (source.get("title") or "Untitled")[:120],
                "url": source.get("url") or "",
                "summary": (source.get("summary") or "")[:480],
            }
        )
    return {"sources": [item for item in trimmed if item["url"]]}


def _analysis_for(topic: str, sources: dict, question: str) -> dict:
    payload = {**sources, "question": question}
    if sources.get("sources"):
        try:
            return run_analysis(payload)
        except Exception:
            return _analysis_from_sources(topic, sources)
    return _analysis_from_sources(topic, sources)


def _analysis_from_sources(topic: str, sources: dict) -> dict:
    claims = []
    for source in sources.get("sources") or []:
        text = source.get("summary") or source.get("title") or ""
        url = source.get("url") or ""
        if text and url:
            claims.append({"text": text, "urls": [url]})
    gaps = []
    if not claims:
        gaps.append(f"No public sources were retrieved for {topic}.")
    else:
        gaps.append("The comparison step kept each source summary as its own claim.")
    return {"claims": claims, "disagreements": [], "gaps": gaps}


def _synthesis_for(analyses: list[dict]) -> dict:
    if not analyses:
        return _fallback_synthesis(
            [{"claims": [], "disagreements": [], "gaps": ["No analysis was available."]}]
        )
    try:
        return run_synthesis(analyses)
    except Exception:
        return _fallback_synthesis(analyses)


def _topic(text: str) -> str:
    cleaned = text.strip()
    lowered = cleaned.lower()
    if lowered.startswith("search:"):
        return cleaned.split(":", 1)[1].strip()
    if lowered.startswith("search "):
        return cleaned[7:].strip()
    return cleaned


def _print(agent: str, task: str) -> None:
    print(f"delegate {agent}: {task}", flush=True)
