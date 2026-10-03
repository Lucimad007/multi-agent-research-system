from langchain_openai import ChatOpenAI
from research.agent import create_research_agent, resolve_model


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
    assert names == ["researcher", "critic"]
    assert "research" in captured["system_prompt"].lower()


def test_resolve_model_uses_opencode_zen(monkeypatch):
    monkeypatch.setenv("OPENCODE_API_KEY", "test-key")
    monkeypatch.setenv("OPENCODE_BASE_URL", "https://opencode.ai/zen/v1")
    monkeypatch.delenv("RESEARCH_MODEL", raising=False)

    model = resolve_model(None)

    assert isinstance(model, ChatOpenAI)
    assert model.model_name == "deepseek-v4.1-flash"
    assert str(model.openai_api_base).rstrip("/") == "https://opencode.ai/zen/v1"
