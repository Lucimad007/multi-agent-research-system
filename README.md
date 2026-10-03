# multi-agent research system

Python monorepo for a research system built on [Deep Agents](https://docs.langchain.com/oss/python/deepagents/overview). LangGraph is the graph runtime under that harness.

## layout

- `packages/research` — lead agent, a web search agent, and a critic

## setup

```bash
uv sync
cp .env.example .env
```

```python
from research import create_research_agent

agent = create_research_agent()
agent.invoke({"messages": "What changed in LangGraph checkpointing?"})
```

The default model is DeepSeek V4.1 Flash on OpenCode Zen (`https://opencode.ai/zen/v1`). Put the Zen key in `OPENCODE_API_KEY`. A `provider:model` string such as `openai:gpt-4.1` still goes through the matching LangChain provider.

## checks

```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest
```

## commits

lowercase, one line, conventional:

```
feat: add research lead agent
fix: pass tools through to subagents
```

types: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`.
