import json
import re

from langchain_core.language_models import BaseChatModel
from pydantic import ValidationError

from research.agent import resolve_model
from research.prompts import REPORT_AGENT_PROMPT
from research.schema import ReportResult
from research.search import AgentRunError, BudgetExceeded, SearchAgentOptions, _BudgetGuard

_SECTIONS = (
    "## Executive Summary",
    "## Findings",
    "## Conflicting Evidence",
    "## Confidence and Limitations",
    "## References",
)


def run_report(synthesis: dict, options: SearchAgentOptions | None = None) -> str:
    """Write the final Markdown report from one synthesis. Does not search the web."""
    selected = options or SearchAgentOptions()
    allowed = _source_urls(synthesis)
    markdown = _write(synthesis, selected, selected.model)
    problem = _citation_problem(markdown, allowed)
    if problem is None:
        return markdown
    repaired = _write(synthesis, selected, selected.model, problem)
    still = _citation_problem(repaired, allowed)
    if still:
        raise AgentRunError("report", still)
    return repaired


def _write(
    synthesis: dict,
    options: SearchAgentOptions,
    model_name: str,
    problem: str | None = None,
) -> str:
    reminder = f"Fix this and return the full report again:\n{problem}\n" if problem else ""
    prompt = f"{REPORT_AGENT_PROMPT}\n{reminder}{json.dumps(synthesis, indent=2)}"
    names = [model_name]
    if options.fallback_model != model_name:
        names.append(options.fallback_model)
    last_error = "report agent did not complete"
    for name in names:
        guard = _BudgetGuard(name, options.max_budget_usd)
        try:
            chat = resolve_model(name)
            if isinstance(chat, str) or not isinstance(chat, BaseChatModel):
                raise AgentRunError("report", "report requires a chat model instance")
            result = chat.with_structured_output(ReportResult).invoke(
                prompt,
                config={"callbacks": [guard]},
            )
            return ReportResult.model_validate(result).markdown.strip()
        except BudgetExceeded:
            raise
        except AgentRunError:
            raise
        except (ValidationError, Exception) as exc:
            last_error = str(exc)
    raise AgentRunError("report", last_error)


def _source_urls(synthesis: dict) -> set[str]:
    urls: set[str] = set()
    for item in synthesis.get("conclusions") or []:
        urls.update(item.get("urls") or [])
    for item in synthesis.get("conflicts") or []:
        urls.update(item.get("urls") or [])
    return {url for url in urls if url}


def _citation_problem(markdown: str, allowed: set[str]) -> str | None:
    if not markdown.lstrip().startswith("# "):
        return "the report needs a markdown title"
    for section in _SECTIONS:
        if section not in markdown:
            return f"the report is missing {section}"
    body, _, references = markdown.partition("## References")
    cited = _bracket_numbers(body)
    listed = _reference_numbers(references)
    if cited != listed:
        return "every citation must match a reference, and every reference must be cited"
    for url in _urls(references):
        if url not in allowed:
            return f"reference URL was not in the synthesis: {url}"
    return None


def _bracket_numbers(text: str) -> set[int]:
    found: set[int] = set()
    for group in re.findall(r"\[([0-9,\s]+)\]", text):
        for part in group.split(","):
            part = part.strip()
            if part.isdigit():
                found.add(int(part))
    return found


def _reference_numbers(text: str) -> set[int]:
    found: set[int] = set()
    for line in text.splitlines():
        match = re.match(r"\s*(\d+)\.\s+", line)
        if match:
            found.add(int(match.group(1)))
    return found


def _urls(text: str) -> list[str]:
    return re.findall(r"https?://\S+", text)
