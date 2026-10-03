import asyncio

from langchain_core.messages import AIMessage
from langchain_openai import ChatOpenAI
from research.agent import create_research_agent, resolve_model
from research.analysis import create_analysis_agent, run_analysis
from research.coordinator import create_coordinator, run_coordinator
from research.pipeline import build_research_pipeline
from research.schema import SearchResult
from research.search import (
    AgentRunError,
    AssistantMessage,
    ResultMessage,
    SearchAgentOptions,
    create_search_agent,
    query,
)


def test_create_research_agent_uses_deep_agents(monkeypatch):
    captured: dict = {}

    def fake_create_deep_agent(**kwargs):
        captured.update(kwargs)
        return {"compiled": True}

    monkeypatch.setattr("research.agent.create_deep_agent", fake_create_deep_agent)

    graph = create_research_agent(model="openai:gpt-4.1", tools=[])

    assert graph == {"compiled": True}
    assert captured["model"] == "openai:gpt-4.1"
    names = [agent["name"] for agent in captured["subagents"]]
    assert names == ["search", "critic"]
    search = captured["subagents"][0]
    assert "search the web" in search["system_prompt"].lower()
    assert "do not analyze" in search["system_prompt"].lower()


def test_resolve_model_uses_opencode_zen(monkeypatch):
    monkeypatch.setenv("OPENCODE_API_KEY", "test-key")
    monkeypatch.setenv("OPENCODE_BASE_URL", "https://opencode.ai/zen/v1")
    monkeypatch.delenv("RESEARCH_MODEL", raising=False)

    model = resolve_model(None)

    assert isinstance(model, ChatOpenAI)
    assert model.model_name == "deepseek-v4.1-flash"
    assert str(model.openai_api_base).rstrip("/") == "https://opencode.ai/zen/v1"


def test_search_agent_options_match_opencode_defaults(monkeypatch):
    captured: dict = {}

    def fake_create_agent(**kwargs):
        captured.update(kwargs)
        return {"compiled": True}

    monkeypatch.setattr("research.search.create_agent", fake_create_agent)
    monkeypatch.setattr("research.search.resolve_model", lambda name: f"model:{name}")

    options = SearchAgentOptions()
    graph = create_search_agent(options)

    assert graph == {"compiled": True}
    assert captured["model"] == "model:deepseek-v4.1-flash"
    assert [tool.name for tool in captured["tools"]] == ["web_search"]
    assert "search the web" in captured["system_prompt"].lower()
    assert options.fallback_model == "deepseek-v4-flash"
    assert options.max_turns == 10
    assert options.max_budget_usd == 0.05
    assert captured["response_format"] is SearchResult


def test_query_streams_text_then_result(monkeypatch):
    class _Graph:
        async def astream(self, payload, config, stream_mode):
            assert payload["messages"][0]["content"] == "topic"
            assert stream_mode == "updates"
            assert config["recursion_limit"] == 21
            yield {"model": {"messages": [AIMessage(content="one source")]}}
            yield {"tools": {"messages": []}}
            yield {"model": {"messages": [AIMessage(content="two sources")]}}

    monkeypatch.setattr("research.search.create_search_agent", lambda *args, **kwargs: _Graph())

    messages = asyncio.run(_collect(query("topic", SearchAgentOptions())))

    assert isinstance(messages[0], AssistantMessage)
    assert messages[0].content[0].text == "one source"
    assert messages[1].content[0].text == "two sources"
    assert isinstance(messages[2], ResultMessage)
    assert messages[2].num_turns == 2
    assert messages[2].total_cost_usd == 0.0


async def _collect(stream):
    return [message async for message in stream]


def test_analysis_graph_grounds_citations(monkeypatch):
    calls = {"n": 0}

    def fake_structured(model_name, options, schema, prompt):
        calls["n"] += 1
        if schema.__name__ == "ClaimSet":
            return {"claims": [{"text": "shared", "urls": ["https://a.test"]}]}
        if calls["n"] == 2:
            return {
                "claims": ["shared"],
                "disagreements": [],
                "gaps": ["cost"],
                "cited_urls": ["https://evil.test"],
            }
        return {
            "claims": ["shared"],
            "disagreements": [],
            "gaps": ["cost"],
            "cited_urls": ["https://a.test"],
        }

    monkeypatch.setattr("research.analysis._structured", fake_structured)

    findings = run_analysis(
        {"sources": [{"title": "A", "url": "https://a.test", "summary": "Says shared."}]}
    )

    assert findings == {"claims": ["shared"], "disagreements": [], "gaps": ["cost"]}
    assert calls["n"] == 3


def test_analysis_graph_has_grounding_steps():
    names = set(create_analysis_agent().get_graph().nodes)
    assert {"validate", "extract", "compare", "ground"} <= names


def test_analysis_rejects_bad_search_output():
    try:
        run_analysis({"sources": [{"title": "only"}]})
    except AgentRunError as exc:
        assert exc.stage == "analysis"
    else:
        raise AssertionError("expected AgentRunError")


def test_pipeline_skips_analysis_when_search_fails(monkeypatch):
    def fail(topic):
        raise AgentRunError("search", "no sources")

    called = {"analysis": False}

    monkeypatch.setattr("research.pipeline.run_search", fail)
    monkeypatch.setattr(
        "research.pipeline.run_analysis",
        lambda sources: called.__setitem__("analysis", True),
    )

    state = build_research_pipeline().invoke({"topic": "topic"})

    assert state["error"] == "search: no sources"
    assert called["analysis"] is False


def test_coordinator_delegates_one_search_per_subtask(monkeypatch):
    monkeypatch.setattr(
        "research.coordinator._plan",
        lambda state, options: {"subtasks": ["checkpointing", "threads"], "error": None},
    )

    def fake_search(topic, options=None):
        return {
            "sources": [{"title": topic, "url": f"https://{topic}.test", "summary": "Says it."}]
        }

    analyzed: list[str] = []

    def fake_analysis(sources):
        analyzed.append(sources["sources"][0]["title"])
        return {"claims": [f"{analyzed[-1]} claim"], "disagreements": [], "gaps": ["cost"]}

    monkeypatch.setattr("research.coordinator.run_search", fake_search)
    monkeypatch.setattr("research.coordinator.run_analysis", fake_analysis)

    result = run_coordinator("How does LangGraph persist state?")

    assert analyzed == ["checkpointing", "threads"]
    agents = [item["agent"] for item in result["handoffs"]]
    assert agents.count("search-agent") == 2
    assert agents.count("analysis-agent") == 2
    assert "checkpointing claim" in result["answer"]
    assert result["error"] is None


def test_coordinator_graph_plans_then_delegates():
    names = set(create_coordinator().get_graph().nodes)
    assert {"plan", "delegate", "assemble"} <= names


def test_search_schema_requires_title_url_summary():
    parsed = SearchResult.model_validate(
        {"sources": [{"title": "A", "url": "https://example.com", "summary": "Says A."}]}
    )
    assert parsed.model_dump()["sources"][0]["url"] == "https://example.com"
