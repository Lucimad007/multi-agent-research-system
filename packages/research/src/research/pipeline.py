from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from research.analysis import run_analysis
from research.search import AgentRunError, run_search


class ResearchState(TypedDict, total=False):
    topic: str
    sources: dict | None
    analysis: dict | None
    error: str | None


def _search_node(state: ResearchState) -> ResearchState:
    try:
        return {"sources": run_search(state["topic"]), "error": None}
    except AgentRunError as exc:
        return {"sources": None, "error": str(exc)}
    except Exception as exc:
        return {"sources": None, "error": f"search: {exc}"}


def _analyze_node(state: ResearchState) -> ResearchState:
    try:
        return {"analysis": run_analysis(state["sources"] or {})}
    except AgentRunError as exc:
        return {"analysis": None, "error": str(exc)}
    except Exception as exc:
        return {"analysis": None, "error": f"analysis: {exc}"}


def _route(state: ResearchState) -> str:
    if state.get("error") or not state.get("sources"):
        return "end"
    return "analyze"


def build_research_pipeline() -> CompiledStateGraph:
    """Search, then analyze. A search error skips analysis."""
    graph = StateGraph(ResearchState)
    graph.add_node("search", _search_node)
    graph.add_node("analyze", _analyze_node)
    graph.add_edge(START, "search")
    graph.add_conditional_edges("search", _route, {"analyze": "analyze", "end": END})
    graph.add_edge("analyze", END)
    return graph.compile()


def run_research(topic: str) -> ResearchState:
    return build_research_pipeline().invoke({"topic": topic})
