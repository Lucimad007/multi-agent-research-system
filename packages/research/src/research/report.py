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
    try:
        markdown = _write(synthesis, selected, selected.model)
    except (AgentRunError, BudgetExceeded):
        return _fallback_report(synthesis)
    problem = _citation_problem(markdown, allowed)
    if problem is None:
        return markdown
    try:
        repaired = _write(synthesis, selected, selected.model, problem)
    except (AgentRunError, BudgetExceeded):
        return _fallback_report(synthesis)
    if _citation_problem(repaired, allowed) is None:
        return repaired
    return _fallback_report(synthesis)


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
    found: set[str] = set()

    def walk(value: object) -> None:
        if isinstance(value, str):
            found.update(_urls(value))
        elif isinstance(value, dict):
            for item in value.values():
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    walk(synthesis)
    return {_clean_url(url) for url in found if url}


def _fallback_report(synthesis: dict) -> str:
    """Build the report from the synthesis when the model draft cannot be cited."""
    refs: list[str] = []
    index: dict[str, int] = {}

    def cite(urls: list[str]) -> str:
        numbers: list[str] = []
        for url in urls:
            cleaned = _clean_url(url)
            if not cleaned:
                continue
            if cleaned not in index:
                index[cleaned] = len(refs) + 1
                refs.append(cleaned)
            numbers.append(str(index[cleaned]))
        return f" [{', '.join(numbers)}]" if numbers else " (unsourced)"

    findings = []
    for item in synthesis.get("conclusions") or []:
        text = item.get("text") or ""
        if not text:
            continue
        findings.append(f"- {text}{cite(item.get('urls') or [])}")
    conflicts = []
    for item in synthesis.get("conflicts") or []:
        conflict = item.get("conflict") or ""
        resolution = item.get("resolution") or ""
        if not conflict and not resolution:
            continue
        conflicts.append(f"- {conflict} {resolution}{cite(item.get('urls') or [])}".strip())
    gaps = [gap for gap in synthesis.get("gaps") or [] if gap]
    picture = synthesis.get("picture") or "The synthesis did not state an overall picture."
    reference_lines = [f"{number}. {url}" for url, number in index.items()] or ["None."]
    gap_lines = "\n".join(f"- {gap}" for gap in gaps) or "- None."
    finding_lines = "\n".join(findings) or "- None."
    conflict_lines = "\n".join(conflicts) or "- None."
    return (
        "# Research report\n\n"
        "## Executive Summary\n"
        f"{picture}\n\n"
        "## Findings\n"
        f"{finding_lines}\n\n"
        "## Conflicting Evidence\n"
        f"{conflict_lines}\n\n"
        "## Confidence and Limitations\n"
        f"{gap_lines}\n\n"
        "## References\n"
        f"{chr(10).join(reference_lines)}\n"
    )


def _citation_problem(markdown: str, allowed: set[str]) -> str | None:
    if not markdown.lstrip().startswith("# "):
        return "the report needs a markdown title"
    folded = markdown.casefold()
    for section in _SECTIONS:
        if section.casefold() not in folded:
            return f"the report is missing {section}"
    body, _, references = markdown.partition("## References")
    cited = _bracket_numbers(body)
    listed = _reference_numbers(references)
    if cited != listed:
        return "every citation must match a reference, and every reference must be cited"
    for url in _urls(references):
        if _clean_url(url) not in allowed:
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
    return [_clean_url(url) for url in re.findall(r"https?://\S+", text)]


def _clean_url(url: str) -> str:
    return url.rstrip(".,);]")
