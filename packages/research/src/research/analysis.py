import json
from dataclasses import dataclass
from typing import TypedDict

from langchain_core.language_models import BaseChatModel
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from pydantic import BaseModel, ValidationError

from research.agent import resolve_model
from research.prompts import ANALYSIS_AGENT_PROMPT
from research.schema import AnalysisResult, ClaimSet, Comparison, SearchResult
from research.search import AgentRunError, BudgetExceeded, SearchAgentOptions, _BudgetGuard


@dataclass(frozen=True)
class AnalysisAgentOptions(SearchAgentOptions):
    system_prompt: str = ANALYSIS_AGENT_PROMPT
    allowed_tools: tuple[str, ...] = ()
    max_turns: int = 3


class AnalysisState(TypedDict, total=False):
    sources: list[dict]
    claims: list[dict]
    comparison: dict | None
    findings: dict | None
    error: str | None
    repairs: int
    model_name: str


def create_analysis_agent(
    options: AnalysisAgentOptions | None = None,
    *,
    model: str | BaseChatModel | None = None,
) -> CompiledStateGraph:
    """LangGraph analysis pass: validate, extract, compare, then ground citations."""
    selected = options or AnalysisAgentOptions()
    if selected.allowed_tools:
        raise AgentRunError("analysis", "analysis agent cannot use tools")
    if model is not None:
        raise AgentRunError("analysis", "pass the model through AnalysisAgentOptions")

    graph = StateGraph(AnalysisState)
    graph.add_node("validate", _validate_node)
    graph.add_node("extract", lambda state: _extract_node(state, selected))
    graph.add_node("compare", lambda state: _compare_node(state, selected))
    graph.add_node("ground", _ground_node)
    graph.add_edge(START, "validate")
    graph.add_conditional_edges("validate", _after_validate, {"extract": "extract", "end": END})
    graph.add_conditional_edges("extract", _after_extract, {"compare": "compare", "end": END})
    graph.add_conditional_edges("compare", _after_compare, {"ground": "ground", "end": END})
    graph.add_conditional_edges("ground", _after_ground, {"repair": "compare", "end": END})
    return graph.compile()


def run_analysis(sources: dict, options: AnalysisAgentOptions | None = None) -> dict:
    """Run the analysis graph on a search-agent source object."""
    selected = options or AnalysisAgentOptions()
    graph = create_analysis_agent(selected)
    state = graph.invoke(
        {
            "sources": sources.get("sources", []),
            "claims": [],
            "comparison": None,
            "findings": None,
            "error": None,
            "repairs": 0,
            "model_name": selected.model,
        },
        config={"recursion_limit": selected.max_turns + 4},
    )
    if state.get("error"):
        raise AgentRunError("analysis", state["error"])
    findings = state.get("findings")
    if not findings:
        raise AgentRunError("analysis", "analysis agent did not complete")
    return findings


def _after_validate(state: AnalysisState) -> str:
    return "end" if state.get("error") else "extract"


def _after_extract(state: AnalysisState) -> str:
    return "end" if state.get("error") else "compare"


def _after_compare(state: AnalysisState) -> str:
    return "end" if state.get("error") else "ground"


def _after_ground(state: AnalysisState) -> str:
    if state.get("error") == "ungrounded":
        return "repair"
    return "end"


def _validate_node(state: AnalysisState) -> AnalysisState:
    try:
        parsed = SearchResult.model_validate({"sources": state.get("sources", [])})
    except ValidationError:
        return {"error": "sources do not match the search schema"}
    seen: set[str] = set()
    sources: list[dict] = []
    for source in parsed.sources:
        if source.url in seen:
            continue
        seen.add(source.url)
        sources.append(source.model_dump())
    if not sources:
        return {"error": "sources do not match the search schema"}
    return {"sources": sources, "error": None}


def _extract_node(state: AnalysisState, options: AnalysisAgentOptions) -> AnalysisState:
    prompt = (
        f"{options.system_prompt}\n"
        "Extract atomic claims. Each claim must cite one or more source URLs from the input.\n"
        f"{json.dumps({'sources': state['sources']}, indent=2)}"
    )
    try:
        payload = _structured(state["model_name"], options, ClaimSet, prompt)
    except AgentRunError as exc:
        return {"error": str(exc).removeprefix("analysis: ")}
    return {"claims": payload["claims"], "error": None}


def _compare_node(state: AnalysisState, options: AnalysisAgentOptions) -> AnalysisState:
    note = ""
    if state.get("repairs"):
        note = "Drop any URL that was not in the source list. Cite only the given URLs.\n"
    prompt = (
        f"{options.system_prompt}\n"
        f"{note}"
        "claims: statements supported by more than one source.\n"
        "disagreements: points where sources conflict.\n"
        "gaps: questions the sources do not answer.\n"
        "cited_urls: every URL you relied on.\n"
        f"{json.dumps({'sources': state['sources'], 'claims': state.get('claims', [])}, indent=2)}"
    )
    try:
        payload = _structured(state["model_name"], options, Comparison, prompt)
    except AgentRunError as exc:
        return {"error": str(exc).removeprefix("analysis: ")}
    return {"comparison": payload, "error": None}


def _ground_node(state: AnalysisState) -> AnalysisState:
    comparison = state.get("comparison") or {}
    allowed = {source["url"] for source in state.get("sources", [])}
    cited = comparison.get("cited_urls") or []
    unknown = sorted({url for url in cited if url not in allowed})
    if unknown:
        if state.get("repairs", 0) < 1:
            return {"error": "ungrounded", "repairs": state.get("repairs", 0) + 1}
        return {"error": f"findings cited unknown urls: {', '.join(unknown)}", "findings": None}
    try:
        findings = AnalysisResult.model_validate(
            {
                "claims": comparison.get("claims", []),
                "disagreements": comparison.get("disagreements", []),
                "gaps": comparison.get("gaps", []),
            }
        ).model_dump()
    except ValidationError:
        return {"error": "analysis output failed schema validation", "findings": None}
    return {"findings": findings, "error": None}


def _structured(
    model_name: str,
    options: AnalysisAgentOptions,
    schema: type[BaseModel],
    prompt: str,
) -> dict:
    names = [model_name]
    if options.fallback_model != model_name:
        names.append(options.fallback_model)
    last_error = "model did not return findings"
    for name in names:
        guard = _BudgetGuard(name, options.max_budget_usd)
        try:
            chat = resolve_model(name)
            if isinstance(chat, str):
                raise AgentRunError("analysis", "analysis requires a chat model instance")
            structured = chat.with_structured_output(schema)
            result = structured.invoke(
                prompt,
                config={"callbacks": [guard]},
            )
            parsed = schema.model_validate(result)
            return parsed.model_dump()
        except BudgetExceeded:
            raise
        except AgentRunError:
            raise
        except Exception as exc:
            last_error = str(exc)
    raise AgentRunError("analysis", last_error)
