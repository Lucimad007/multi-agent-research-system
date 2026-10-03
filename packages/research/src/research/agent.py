import os
from collections.abc import Sequence
from typing import Any

from deepagents import create_deep_agent
from dotenv import load_dotenv
from langchain_core.language_models import BaseChatModel
from langchain_core.tools import BaseTool
from langchain_openai import ChatOpenAI
from langgraph.graph.state import CompiledStateGraph

from research.prompts import CRITIC_PROMPT, LEAD_PROMPT, RESEARCHER_PROMPT

ZEN_BASE_URL = "https://opencode.ai/zen/v1"
DEFAULT_MODEL = "deepseek-v4.1-flash"

Tool = BaseTool | dict[str, Any]


def research_subagents(tools: Sequence[Tool] | None = None) -> list[dict[str, Any]]:
    shared_tools = list(tools or [])
    return [
        {
            "name": "researcher",
            "description": "Investigate a question and return sourced findings.",
            "system_prompt": RESEARCHER_PROMPT,
            "tools": shared_tools,
        },
        {
            "name": "critic",
            "description": "Check a draft for gaps, weak claims, and missing sources.",
            "system_prompt": CRITIC_PROMPT,
            "tools": shared_tools,
        },
    ]


def resolve_model(model: str | BaseChatModel | None) -> str | BaseChatModel:
    """Use OpenCode Zen when the model id is not a provider:model string."""
    if isinstance(model, BaseChatModel):
        return model

    load_dotenv()
    name = model or os.environ.get("RESEARCH_MODEL", DEFAULT_MODEL)
    if ":" in name:
        return name

    api_key = os.environ.get("OPENCODE_API_KEY")
    if not api_key:
        raise RuntimeError("set OPENCODE_API_KEY for the OpenCode Zen endpoint")

    return ChatOpenAI(
        model=name,
        api_key=api_key,
        base_url=os.environ.get("OPENCODE_BASE_URL", ZEN_BASE_URL),
    )


def create_research_agent(
    *,
    model: str | BaseChatModel | None = None,
    tools: Sequence[Tool] | None = None,
    system_prompt: str | None = None,
) -> CompiledStateGraph:
    """Build the research lead on the Deep Agents harness.

    LangGraph is the runtime underneath `create_deep_agent`. Pass a
    `provider:model` string or a LangChain chat model.
    """
    selected = resolve_model(model)
    selected_tools = list(tools or [])
    return create_deep_agent(
        model=selected,
        tools=selected_tools,
        system_prompt=system_prompt or LEAD_PROMPT,
        subagents=research_subagents(selected_tools),
    )
