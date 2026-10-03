import json

from langchain_core.language_models import BaseChatModel
from pydantic import ValidationError

from research.agent import resolve_model
from research.prompts import SYNTHESIS_AGENT_PROMPT
from research.schema import SynthesisResult
from research.search import AgentRunError, BudgetExceeded, SearchAgentOptions, _BudgetGuard

_CONFIDENCE = {"high", "medium", "low"}


def run_synthesis(analyses: list[dict], options: SearchAgentOptions | None = None) -> dict:
    """Synthesize every completed analysis in one pass. Does not search the web."""
    selected = options or SearchAgentOptions()
    if not analyses:
        return _fallback_synthesis(
            [{"claims": [], "disagreements": [], "gaps": ["No analysis was available."]}]
        )
    try:
        payload = _complete(analyses, selected, selected.model)
    except (AgentRunError, BudgetExceeded, Exception):
        return _fallback_synthesis(analyses)
    missing = _missing_gaps(analyses, payload["gaps"])
    if missing:
        return _with_gaps(payload, missing)
    return payload


def _with_gaps(payload: dict, missing: list[str]) -> dict:
    gaps = list(payload.get("gaps") or [])
    for gap in missing:
        if gap not in gaps:
            gaps.append(gap)
    payload["gaps"] = gaps
    return payload


def _fallback_synthesis(analyses: list[dict]) -> dict:
    """Keep every claim, disagreement, and gap when the model pass cannot finish."""
    gaps: list[str] = []
    conclusions: list[dict] = []
    conflicts: list[dict] = []
    for analysis in analyses:
        for gap in analysis.get("gaps") or []:
            if gap and gap not in gaps:
                gaps.append(gap)
        for claim in analysis.get("claims") or []:
            if isinstance(claim, str):
                conclusions.append(
                    {
                        "text": claim,
                        "confidence": "low",
                        "why": "Carried from one analysis.",
                        "urls": [],
                    }
                )
                continue
            text = claim.get("text") or ""
            if not text:
                continue
            conclusions.append(
                {
                    "text": text,
                    "confidence": "low",
                    "why": "Carried from the analysis.",
                    "urls": [url for url in claim.get("urls") or [] if url],
                }
            )
        for item in analysis.get("disagreements") or []:
            if isinstance(item, str) and item:
                conflicts.append(
                    {
                        "conflict": item,
                        "resolution": "Both positions remain because the sources do not agree.",
                        "urls": [],
                    }
                )
                continue
            text = item.get("text") or ""
            if not text:
                continue
            conflicts.append(
                {
                    "conflict": text,
                    "resolution": "Both positions remain because the sources do not agree.",
                    "urls": [url for url in item.get("urls") or [] if url],
                }
            )
    if not conclusions:
        conclusions.append(
            {
                "text": "The run did not produce a sourced conclusion.",
                "confidence": "low",
                "why": "No claim was available to carry forward.",
                "urls": [],
            }
        )
    return SynthesisResult.model_validate(
        {
            "picture": "The completed analyses were combined directly.",
            "conclusions": conclusions,
            "conflicts": conflicts,
            "gaps": gaps,
        }
    ).model_dump()


def _complete(
    analyses: list[dict],
    options: SearchAgentOptions,
    model_name: str,
    missing_gaps: list[str] | None = None,
) -> dict:
    reminder = ""
    if missing_gaps:
        reminder = "These gaps were dropped. Include each one verbatim:\n" + "\n".join(missing_gaps)
    question = next((item.get("question") for item in analyses if item.get("question")), "")
    prompt = (
        f"The user asked: {question}\n"
        "The picture and the first conclusion must answer that question. "
        "If the analyses state a figure, include that figure. "
        "Do not answer by only listing websites.\n"
        f"{SYNTHESIS_AGENT_PROMPT}\n{reminder}\n"
        f"{json.dumps(analyses)}"
    )
    names = [model_name]
    if options.fallback_model != model_name:
        names.append(options.fallback_model)
    last_error = "synthesis agent did not complete"
    for name in names:
        guard = _BudgetGuard(name, options.max_budget_usd)
        try:
            chat = resolve_model(name)
            if isinstance(chat, str) or not isinstance(chat, BaseChatModel):
                raise AgentRunError("synthesis", "synthesis requires a chat model instance")
            result = chat.with_structured_output(SynthesisResult).invoke(
                prompt,
                config={"callbacks": [guard]},
            )
            parsed = SynthesisResult.model_validate(result)
        except BudgetExceeded:
            raise
        except AgentRunError:
            raise
        except (ValidationError, Exception) as exc:
            last_error = str(exc)
            continue
        unknown = [
            item.confidence for item in parsed.conclusions if item.confidence not in _CONFIDENCE
        ]
        if unknown:
            last_error = "confidence must be high, medium, or low"
            continue
        return parsed.model_dump()
    raise AgentRunError("synthesis", last_error)


def _missing_gaps(analyses: list[dict], carried: list[str]) -> list[str]:
    expected = [gap for analysis in analyses for gap in analysis.get("gaps") or [] if gap]
    carried_text = "\n".join(carried)
    return [gap for gap in expected if gap not in carried_text]
