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
        raise AgentRunError("synthesis", "synthesis requires at least one analysis")
    payload = _complete(analyses, selected, selected.model)
    missing = _missing_gaps(analyses, payload["gaps"])
    if not missing:
        return payload
    repaired = _complete(analyses, selected, selected.model, missing)
    still_missing = _missing_gaps(analyses, repaired["gaps"])
    if still_missing:
        raise AgentRunError("synthesis", "synthesis dropped unresolved gaps")
    return repaired


def _complete(
    analyses: list[dict],
    options: SearchAgentOptions,
    model_name: str,
    missing_gaps: list[str] | None = None,
) -> dict:
    reminder = ""
    if missing_gaps:
        reminder = "These gaps were dropped. Include each one verbatim:\n" + "\n".join(missing_gaps)
    prompt = (
        f"{SYNTHESIS_AGENT_PROMPT}\n{reminder}\n"
        f"{json.dumps(analyses, indent=2)}"
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
