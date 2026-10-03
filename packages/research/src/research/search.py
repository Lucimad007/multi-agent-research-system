"""Search agent options, mapped onto a LangGraph tool loop.

This is the OpenCode equivalent of a Claude Agent SDK options block:
prompt, tool allowlist, budget, model, fallback model, and a turn cap.
"""

from collections.abc import AsyncIterator
from dataclasses import dataclass

from langchain.agents import create_agent
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import LLMResult
from langgraph.graph.state import CompiledStateGraph

from research.agent import DEFAULT_MODEL, resolve_model
from research.prompts import SEARCH_AGENT_PROMPT
from research.schema import SearchResult
from research.tools import web_search

# OpenCode Zen list prices, USD per million tokens: (input, output).
_USD_PER_MILLION = {
    "deepseek-v4.1-flash": (0.30, 1.20),
    "deepseek-v4-flash": (0.14, 0.28),
}

_TOOLS = {"web_search": web_search}


class BudgetExceeded(RuntimeError):
    """Raised when a run's estimated token cost passes the cap."""


class AgentRunError(RuntimeError):
    """A search or analysis run failed and should not continue."""

    def __init__(self, stage: str, message: str) -> None:
        self.stage = stage
        super().__init__(f"{stage}: {message}")


@dataclass(frozen=True)
class TextBlock:
    text: str


@dataclass(frozen=True)
class AssistantMessage:
    content: tuple[TextBlock, ...]


@dataclass(frozen=True)
class ResultMessage:
    num_turns: int
    total_cost_usd: float


@dataclass(frozen=True)
class SearchAgentOptions:
    system_prompt: str = SEARCH_AGENT_PROMPT
    allowed_tools: tuple[str, ...] = ("web_search",)
    max_budget_usd: float = 0.05
    model: str = DEFAULT_MODEL
    fallback_model: str = "deepseek-v4-flash"
    max_turns: int = 10


def _tools_for(names: tuple[str, ...]):
    missing = [name for name in names if name not in _TOOLS]
    if missing:
        raise ValueError(f"unknown tools: {', '.join(missing)}")
    return [_TOOLS[name] for name in names]


def _turn_limit(max_turns: int) -> int:
    """LangGraph counts a model step and a tool step as separate recursions."""
    return max_turns * 2 + 1


class _BudgetGuard(BaseCallbackHandler):
    def __init__(self, model_name: str, max_budget_usd: float) -> None:
        self.model_name = model_name
        self.max_budget_usd = max_budget_usd
        self.spent_usd = 0.0

    def on_llm_end(self, response: LLMResult, **kwargs: object) -> None:
        input_rate, output_rate = _USD_PER_MILLION.get(self.model_name, (0.30, 1.20))
        for generations in response.generations:
            for generation in generations:
                message = getattr(generation, "message", None)
                usage = getattr(message, "usage_metadata", None) or {}
                prompt_tokens = usage.get("input_tokens", 0)
                completion_tokens = usage.get("output_tokens", 0)
                cost = prompt_tokens * input_rate + completion_tokens * output_rate
                self.spent_usd += cost / 1_000_000
        if self.spent_usd > self.max_budget_usd:
            raise BudgetExceeded(
                f"estimated cost ${self.spent_usd:.4f} passed the ${self.max_budget_usd:.2f} cap"
            )


def create_search_agent(
    options: SearchAgentOptions | None = None,
    *,
    model: str | BaseChatModel | None = None,
) -> CompiledStateGraph:
    """Build a LangGraph agent that can only call the allowed search tools."""
    selected = options or SearchAgentOptions()
    chat = model if model is not None else resolve_model(selected.model)
    return create_agent(
        model=chat,
        tools=_tools_for(selected.allowed_tools),
        system_prompt=selected.system_prompt,
        response_format=SearchResult,
        name="search",
    )


def run_search(topic: str, options: SearchAgentOptions | None = None) -> dict:
    """Run the search agent and return a validated source object."""
    selected = options or SearchAgentOptions()
    try:
        return _invoke(topic, selected, selected.model)
    except (BudgetExceeded, AgentRunError):
        raise
    except Exception as exc:
        if selected.fallback_model == selected.model:
            raise AgentRunError("search", str(exc)) from exc
        try:
            return _invoke(topic, selected, selected.fallback_model)
        except (BudgetExceeded, AgentRunError):
            raise
        except Exception as fallback_exc:
            raise AgentRunError("search", str(fallback_exc)) from fallback_exc


async def query(
    prompt: str,
    options: SearchAgentOptions | None = None,
) -> AsyncIterator[AssistantMessage | ResultMessage]:
    """Stream assistant text, then a result with turn count and estimated cost."""
    selected = options or SearchAgentOptions()
    started = False
    try:
        async for message in _stream(prompt, selected, selected.model):
            started = True
            yield message
    except BudgetExceeded:
        raise
    except Exception:
        if started or selected.fallback_model == selected.model:
            raise
        async for message in _stream(prompt, selected, selected.fallback_model):
            yield message


def _text_blocks(message: AIMessage) -> tuple[TextBlock, ...]:
    content = message.content
    if isinstance(content, str):
        text = content.strip()
        return (TextBlock(text),) if text else ()
    blocks: list[TextBlock] = []
    if isinstance(content, list):
        for block in content:
            text = block.get("text", "") if isinstance(block, dict) else str(block)
            text = text.strip()
            if text:
                blocks.append(TextBlock(text))
    return tuple(blocks)


async def _stream(
    prompt: str,
    options: SearchAgentOptions,
    model_name: str,
) -> AsyncIterator[AssistantMessage | ResultMessage]:
    agent = create_search_agent(options, model=resolve_model(model_name))
    guard = _BudgetGuard(model_name, options.max_budget_usd)
    turns = 0
    async for update in agent.astream(
        {"messages": [{"role": "user", "content": prompt}]},
        config={"recursion_limit": _turn_limit(options.max_turns), "callbacks": [guard]},
        stream_mode="updates",
    ):
        for payload in update.values():
            messages = payload.get("messages", []) if isinstance(payload, dict) else []
            for message in messages:
                if not isinstance(message, AIMessage):
                    continue
                turns += 1
                blocks = _text_blocks(message)
                if blocks:
                    yield AssistantMessage(content=blocks)
    yield ResultMessage(num_turns=turns, total_cost_usd=guard.spent_usd)


def _coerce_search_result(result: dict) -> dict:
    payload = result.get("structured_response")
    if payload is None:
        raise AgentRunError("search", "model did not return the source schema")
    try:
        parsed = SearchResult.model_validate(payload)
    except Exception as exc:
        raise AgentRunError("search", "search output failed the source schema") from exc
    if not parsed.sources:
        raise AgentRunError("search", "search output contained no sources")
    return parsed.model_dump()


def _invoke(topic: str, options: SearchAgentOptions, model_name: str) -> dict:
    agent = create_search_agent(options, model=resolve_model(model_name))
    guard = _BudgetGuard(model_name, options.max_budget_usd)
    try:
        result = agent.invoke(
            {"messages": [{"role": "user", "content": topic}]},
            config={"recursion_limit": _turn_limit(options.max_turns), "callbacks": [guard]},
        )
    except (BudgetExceeded, AgentRunError):
        raise
    except Exception as exc:
        raise AgentRunError("search", str(exc)) from exc
    return _coerce_search_result(result)
