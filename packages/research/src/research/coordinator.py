from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from pydantic import ValidationError

from research.agent import resolve_model
from research.analysis import run_analysis
from research.prompts import COORDINATOR_PROMPT
from research.report import run_report
from research.schema import ResearchPlan
from research.search import AgentRunError, BudgetExceeded, SearchAgentOptions, run_search
from research.synthesis import run_synthesis


class CoordinatorState(TypedDict, total=False):
    request: str
    subtasks: list[str]
    reports: list[dict]
    answer: str | None
    handoffs: list[dict]
    error: str | None


def create_coordinator(options: SearchAgentOptions | None = None) -> CompiledStateGraph:
    """Plan subtasks, delegate search and analysis, then assemble the answer."""
    selected = options or SearchAgentOptions()
    graph = StateGraph(CoordinatorState)
    graph.add_node("plan", lambda state: _plan(state, selected))
    graph.add_node("delegate", lambda state: _delegate(state, selected))
    graph.add_node("assemble", _assemble)
    graph.add_edge(START, "plan")
    graph.add_conditional_edges("plan", _after_plan, {"delegate": "delegate", "end": END})
    graph.add_edge("delegate", "assemble")
    graph.add_edge("assemble", END)
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


def _after_plan(state: CoordinatorState) -> str:
    return "end" if state.get("error") else "delegate"


def _plan(state: CoordinatorState, options: SearchAgentOptions) -> CoordinatorState:
    request = state["request"].strip()
    if len(request.split()) < 3:
        _print("coordinator", "need a research question, not a greeting or a single word")
        print("fail coordinator: need a research question", flush=True)
        return {"error": "need a research question, not a greeting or a single word"}
    prompt = (
        f"{COORDINATOR_PROMPT}\n"
        "Return 1 to 3 short topics. Do not prefix a topic with the word search.\n"
        "Do not answer the request.\n"
        f"Request:\n{state['request']}"
    )
    names = [options.model]
    if options.fallback_model != options.model:
        names.append(options.fallback_model)
    last_error = "coordinator could not plan subtasks"
    for name in names:
        try:
            chat = resolve_model(name)
            if isinstance(chat, str):
                raise AgentRunError("coordinator", "coordinator requires a chat model instance")
            planned = chat.with_structured_output(ResearchPlan).invoke(prompt)
            raw = ResearchPlan.model_validate(planned).subtasks
            subtasks = [_topic(item) for item in raw]
            subtasks = [item for item in subtasks if item]
            _print("coordinator", "split the request into search subtasks")
            for topic in subtasks:
                _print("coordinator", f"planned search: {topic}")
            print("ok coordinator: split the request into search subtasks", flush=True)
            return {"subtasks": subtasks, "error": None}
        except BudgetExceeded:
            raise
        except (ValidationError, AgentRunError, Exception) as exc:
            last_error = str(exc)
    return {"error": last_error}


def _delegate(state: CoordinatorState, options: SearchAgentOptions) -> CoordinatorState:
    reports: list[dict] = []
    for topic in state.get("subtasks") or []:
        report: dict = {
            "topic": topic,
            "agent": "search-agent",
            "sources": None,
            "analysis": None,
            "error": None,
        }
        _print("search-agent", topic)
        try:
            sources = run_search(topic, options)
            report["sources"] = sources
            print(f"ok search-agent: {topic}", flush=True)
        except AgentRunError as exc:
            report["error"] = str(exc)
            print(f"fail search-agent: {exc}", flush=True)
            reports.append(report)
            continue
        except Exception as exc:
            report["error"] = f"search: {exc}"
            print(f"fail search-agent: {exc}", flush=True)
            reports.append(report)
            continue
        task = f"analyze sources for {topic}"
        _print("analysis-agent", task)
        try:
            report["analysis"] = run_analysis(sources)
            report["agent"] = "analysis-agent"
            print(f"ok analysis-agent: {task}", flush=True)
        except AgentRunError as exc:
            report["error"] = str(exc)
            print(f"fail analysis-agent: {exc}", flush=True)
        except Exception as exc:
            report["error"] = f"analysis: {exc}"
            print(f"fail analysis-agent: {exc}", flush=True)
        reports.append(report)
    if not any(report.get("analysis") for report in reports):
        return {"reports": reports, "error": "no analysis completed"}
    return {"reports": reports, "error": None}


def _assemble(state: CoordinatorState) -> CoordinatorState:
    handoffs: list[dict] = [
        {"agent": "coordinator", "task": "split the request into search subtasks"}
    ]
    analyses: list[dict] = []
    for report in state.get("reports") or []:
        handoffs.append({"agent": "search-agent", "task": report["topic"]})
        if not report.get("analysis"):
            continue
        handoffs.append(
            {"agent": "analysis-agent", "task": f"analyze sources for {report['topic']}"}
        )
        analyses.append({"topic": report["topic"], **report["analysis"]})
    if not analyses:
        return {"handoffs": handoffs, "error": state.get("error") or "no analysis completed"}
    task = "synthesize every completed analysis"
    _print("synthesis-agent", task)
    try:
        synthesis = run_synthesis(analyses)
        print(f"ok synthesis-agent: {task}", flush=True)
    except AgentRunError as exc:
        print(f"fail synthesis-agent: {exc}", flush=True)
        return {"handoffs": handoffs, "error": str(exc)}
    handoffs.append({"agent": "synthesis-agent", "task": "synthesize every completed analysis"})
    task = "write the research report from the full synthesis"
    _print("report-agent", task)
    try:
        markdown = run_report(synthesis)
        print(f"ok report-agent: {task}", flush=True)
    except AgentRunError as exc:
        print(f"fail report-agent: {exc}", flush=True)
        return {"handoffs": handoffs, "error": str(exc)}
    handoffs.append(
        {"agent": "report-agent", "task": "write the research report from the full synthesis"}
    )
    handoffs.append({"agent": "coordinator", "task": "return the report unchanged"})
    _print("coordinator", "return the report unchanged")
    return {"answer": markdown, "handoffs": handoffs, "error": None}


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
