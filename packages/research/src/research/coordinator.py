from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from pydantic import ValidationError

from research.agent import resolve_model
from research.analysis import run_analysis
from research.prompts import COORDINATOR_PROMPT
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
    prompt = (
        f"{COORDINATOR_PROMPT}\n"
        "Return 1 to 3 search topics. One topic per subtask. Do not answer the request.\n"
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
            subtasks = ResearchPlan.model_validate(planned).subtasks
            return {"subtasks": [item.strip() for item in subtasks if item.strip()], "error": None}
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
        try:
            sources = run_search(topic, options)
            report["sources"] = sources
        except AgentRunError as exc:
            report["error"] = str(exc)
            reports.append(report)
            continue
        except Exception as exc:
            report["error"] = f"search: {exc}"
            reports.append(report)
            continue
        try:
            report["analysis"] = run_analysis(sources)
            report["agent"] = "analysis-agent"
        except AgentRunError as exc:
            report["error"] = str(exc)
        except Exception as exc:
            report["error"] = f"analysis: {exc}"
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
    try:
        synthesis = run_synthesis(analyses)
    except AgentRunError as exc:
        return {"handoffs": handoffs, "error": str(exc)}
    handoffs.append({"agent": "synthesis-agent", "task": "synthesize every completed analysis"})
    handoffs.append({"agent": "coordinator", "task": "present the synthesis"})
    return {"answer": _present(synthesis), "handoffs": handoffs, "error": None}


def _present(synthesis: dict) -> str:
    conclusions = []
    for item in synthesis.get("conclusions") or []:
        conclusions.append(f"- {item['text']} ({item['confidence']}): {item['why']}")
    conflicts = []
    for item in synthesis.get("conflicts") or []:
        conflicts.append(f"- {item['conflict']} -> {item['resolution']}")
    gaps = "\n".join(f"- {item}" for item in synthesis.get("gaps") or []) or "- none"
    return (
        f"{synthesis.get('picture', '')}\n\n"
        f"Conclusions from synthesis-agent:\n{chr(10).join(conclusions) or '- none'}\n\n"
        f"Conflicts:\n{chr(10).join(conflicts) or '- none'}\n\n"
        f"Gaps:\n{gaps}"
    )
