"""Run the coordinator and print delegations, then one JSON result line."""

import json
import os

from research.coordinator import create_coordinator


def main() -> None:
    request = os.environ.get("RESEARCH_QUERY", "").strip()
    if not request:
        print("__RESULT__" + json.dumps({"error": "empty query", "answer": None, "handoffs": []}))
        return
    state = create_coordinator().invoke({"request": request, "reports": [], "handoffs": []})
    payload = {
        "answer": state.get("answer"),
        "handoffs": state.get("handoffs") or [],
        "error": state.get("error"),
    }
    print("__RESULT__" + json.dumps(payload, ensure_ascii=False))


if __name__ == "__main__":
    main()
