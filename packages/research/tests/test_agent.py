import asyncio

from langchain_core.messages import AIMessage
from langchain_openai import ChatOpenAI
from research.agent import create_research_agent, resolve_model
from research.search import (
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
