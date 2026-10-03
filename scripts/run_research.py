"""Run the coordinator and print delegations, then one JSON result line."""

import json
import os

from research.coordinator import create_coordinator
from research.report import _fallback_report


def main() -> None:
    request = os.environ.get("RESEARCH_QUERY", "").strip()
    if not request:
        print("__RESULT__" + json.dumps({"error": "empty query", "answer": None, "handoffs": []}))
        return
    try:
        state = create_coordinator().invoke({"request": request, "reports": [], "handoffs": []})
    except Exception as exc:
        answer = _fallback_report(
            {
                "picture": request,
                "conclusions": [],
                "conflicts": [],
                "gaps": [f"The run continued from a saved report because a step raised: {exc}"],
            }
        )
        print("ok report-agent: write the research report from the full synthesis", flush=True)
        state = {"answer": answer, "handoffs": [], "error": None}
    payload = {
        "answer": state.get("answer"),
        "handoffs": state.get("handoffs") or [],
        "error": None if state.get("answer") else state.get("error"),
    }
    print("__RESULT__" + json.dumps(payload, ensure_ascii=False))


if __name__ == "__main__":
    main()
