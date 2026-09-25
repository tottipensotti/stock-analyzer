"""calculate_score — Tool: Investment Quality Score (0–100)."""

from dataclasses import asdict

from tools.registry import tool
from utils.scoring import render_summary, score_all_entries


@tool(
    "calculate_score",
    "Calculate Investment Quality Score",
    {
        "type": "object",
        "properties": {
            "entries": {"type": "array"},
            "universe": {"type": "array"},
            "comparisons": {"type": "object"},
        },
        "required": ["entries"],
    },
)
def calculate_score_tool(inputs: dict) -> dict:
    batch = score_all_entries(
        inputs["entries"],
        all_entries=inputs.get("universe"),
        comparisons=inputs.get("comparisons"),
    )
    keys = ("core", "speculative", "confirmed", "dislocated")
    payload = {key: [asdict(item) for item in getattr(batch, key)] for key in keys}
    payload["skipped_etfs"] = batch.skipped_etfs
    payload["skipped_minimal"] = batch.skipped_minimal
    payload["summary"] = render_summary(batch)
    return {"ok": True, "data": payload}
