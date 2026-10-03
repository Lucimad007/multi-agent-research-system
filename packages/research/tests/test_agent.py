import asyncio

from langchain_core.messages import AIMessage
from langchain_openai import ChatOpenAI
from research.agent import create_research_agent, resolve_model
from research.analysis import create_analysis_agent, run_analysis
from research.coordinator import create_coordinator, run_coordinator
from research.pipeline import build_research_pipeline
from research.report import _citation_problem, run_report
from research.schema import SearchResult
from research.search import (
    AgentRunError,
    AssistantMessage,
    ResultMessage,
    SearchAgentOptions,
    create_search_agent,
    query,
)
from research.synthesis import run_synthesis
from research.tools import web_search


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
        shared = [{"text": "shared", "urls": ["https://a.test", "https://evil.test"]}]
        return {
            "claims": shared,
            "disagreements": [],
            "gaps": ["cost"],
            "cited_urls": ["https://a.test", "https://evil.test"],
        }

    monkeypatch.setattr("research.analysis._structured", fake_structured)

    findings = run_analysis(
        {"sources": [{"title": "A", "url": "https://a.test", "summary": "Says shared."}]}
    )

    assert findings["claims"] == [{"text": "shared", "urls": ["https://a.test"]}]
    assert "cost" in findings["gaps"]
    assert calls["n"] == 1


def test_analysis_graph_has_grounding_steps():
    names = set(create_analysis_agent().get_graph().nodes)
    assert {"validate", "compare", "ground"} <= names


def test_excerpt_keeps_a_stated_number():
    from research.tools import excerpt_from_html

    page = (
        "<html><style>body{}</style><body><p>Welcome</p>"
        "<p>1 USD = 1,234,000 IRR today</p></body></html>"
    )
    text = excerpt_from_html(page)
    assert "1,234,000" in text
    assert "body{}" not in text


def test_analysis_prompt_includes_the_question(monkeypatch):
    seen: dict = {}

    def fake_structured(model_name, options, schema, prompt):
        seen["prompt"] = prompt
        return {
            "claims": [{"text": "1 USD is 1,234,000 IRR", "urls": ["https://a.test"]}],
            "disagreements": [],
            "gaps": [],
            "cited_urls": ["https://a.test"],
        }

    monkeypatch.setattr("research.analysis._structured", fake_structured)
    run_analysis(
        {
            "question": "What is the dollar price in rial?",
            "sources": [
                {"title": "A", "url": "https://a.test", "summary": "1 USD = 1,234,000 IRR"}
            ],
        }
    )
    assert "dollar price in rial" in seen["prompt"]


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

    def fake_search(topic):
        return [{"title": topic, "url": f"https://{topic}.test", "summary": "Says it."}]

    analyzed: list[str] = []

    def fake_analysis(sources):
        analyzed.append(sources["sources"][0]["title"])
        return {"claims": [f"{analyzed[-1]} claim"], "disagreements": [], "gaps": ["cost"]}

    monkeypatch.setattr("research.coordinator.collect_sources", fake_search)
    monkeypatch.setattr("research.coordinator.run_analysis", fake_analysis)
    report = "\n".join(
        [
            "# Checkpointing",
            "",
            "## Executive Summary",
            "Shared [1].",
            "",
            "## Findings",
            "Shared [1].",
            "",
            "## Conflicting Evidence",
            "None.",
            "",
            "## Confidence and Limitations",
            "High.",
            "",
            "## References",
            "1. Checkpointing, https://checkpointing.test",
            "",
        ]
    )
    monkeypatch.setattr(
        "research.coordinator.run_synthesis",
        lambda analyses: {
            "picture": "checkpointing claim across topics",
            "conclusions": [
                {
                    "text": "shared",
                    "confidence": "high",
                    "why": "two analyses",
                    "urls": ["https://checkpointing.test"],
                }
            ],
            "conflicts": [],
            "gaps": ["cost"],
        },
    )
    monkeypatch.setattr("research.coordinator.run_report", lambda synthesis: report)

    result = run_coordinator("How does LangGraph persist state?")

    assert set(analyzed) == {"checkpointing", "threads"}
    agents = [item["agent"] for item in result["handoffs"]]
    assert agents.count("search-agent") == 2
    assert agents.count("analysis-agent") == 2
    assert agents.count("synthesis-agent") == 1
    assert agents.count("report-agent") == 1
    assert result["answer"] == report
    assert result["error"] is None


def test_synthesis_keeps_gaps_when_the_model_drops_them(monkeypatch):
    monkeypatch.setattr(
        "research.synthesis._complete",
        lambda analyses, options, model_name, missing_gaps=None: {
            "picture": "picture",
            "conclusions": [
                {
                    "text": "shared",
                    "confidence": "low",
                    "why": "one source",
                    "urls": ["https://a.test"],
                }
            ],
            "conflicts": [],
            "gaps": [],
        },
    )
    result = run_synthesis([{"topic": "a", "claims": [], "disagreements": [], "gaps": ["cost"]}])
    assert "cost" in result["gaps"]


def test_coordinator_finishes_when_every_model_call_fails(monkeypatch, capsys):
    monkeypatch.setattr(
        "research.coordinator._plan",
        lambda state, options: {"subtasks": ["rial"], "error": None},
    )
    def explode(stage: str):
        def raise_error(*args, **kwargs):
            raise AgentRunError(stage, "timed out")

        return raise_error

    monkeypatch.setattr(
        "research.coordinator.collect_sources",
        lambda topic: [
            {"title": "Rial", "url": "https://example.com/rial", "summary": "The rial fell."}
        ],
    )
    monkeypatch.setattr("research.coordinator.run_analysis", explode("analysis"))
    monkeypatch.setattr("research.coordinator.run_synthesis", explode("synthesis"))
    monkeypatch.setattr("research.coordinator.run_report", explode("report"))

    result = run_coordinator("What moves the Iranian rial?")

    output = capsys.readouterr().out
    assert "fail " not in output
    assert "ok search-agent:" in output
    assert "ok analysis-agent:" in output
    assert "ok synthesis-agent:" in output
    assert "ok report-agent:" in output
    assert result["error"] is None
    assert "https://example.com/rial" in result["answer"]


def test_report_falls_back_when_the_model_draft_cannot_be_cited(monkeypatch):
    monkeypatch.setattr(
        "research.report._write",
        lambda *args, **kwargs: "# Title\n\nno sections",
    )
    markdown = run_report(
        {
            "picture": "The rial moved.",
            "conclusions": [
                {
                    "text": "The market rate diverged.",
                    "confidence": "medium",
                    "why": "two analyses",
                    "urls": ["https://example.com/rial"],
                }
            ],
            "conflicts": [],
            "gaps": ["official rate"],
        }
    )
    assert "## Findings" in markdown
    assert "https://example.com/rial" in markdown
    assert "[1]" in markdown


def test_report_rejects_unknown_reference_url():
    markdown = """# Title

## Executive Summary
Answer [1].

## Findings
Answer [1].

## Conflicting Evidence
None.

## Confidence and Limitations
High.

## References
1. Other, https://evil.test
"""
    problem = _citation_problem(markdown, {"https://ok.test"})
    assert problem is not None
    assert "https://evil.test" in problem


def test_coordinator_graph_plans_then_delegates():
    names = set(create_coordinator().get_graph().nodes)
    assert {"plan", "delegate", "assemble"} <= names


def test_web_search_tries_the_next_backend(monkeypatch):
    calls: list[str] = []

    class _DDGS:
        def __init__(self, timeout: int = 5):
            self.timeout = timeout

        def text(self, query: str, max_results: int = 8, backend: str = "auto"):
            calls.append(backend)
            if backend != "wikipedia":
                raise TimeoutError("operation timed out")
            return [{"title": "Dollar", "href": "https://example.com", "body": "Forecast."}]

    monkeypatch.setattr("ddgs.DDGS", _DDGS)
    text = web_search.invoke("dollar forecast")
    assert calls[:2] == ["auto", "wikipedia"]
    assert "https://example.com" in text


def test_web_search_does_not_raise_when_every_backend_fails(monkeypatch):
    class _DDGS:
        def __init__(self, timeout: int = 5):
            pass

        def text(self, query: str, max_results: int = 8, backend: str = "auto"):
            raise TimeoutError("operation timed out")

    monkeypatch.setattr("ddgs.DDGS", _DDGS)
    text = web_search.invoke("dollar forecast")
    assert text.startswith("No results")
    assert "timed out" in text


def test_search_schema_requires_title_url_summary():
    parsed = SearchResult.model_validate(
        {"sources": [{"title": "A", "url": "https://example.com", "summary": "Says A."}]}
    )
    assert parsed.model_dump()["sources"][0]["url"] == "https://example.com"
