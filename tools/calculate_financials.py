"""calculate_financials — Tool: métricas derivadas / estimaciones sobre KPIs crudos."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from tools.registry import tool
from utils.helpers import EQUITY_RISK_PREMIUM, RISK_FREE_RATE, estimate_wacc
from utils.models import TickerKpis

__all__ = ["apply_derived", "derive_fcf_metrics", "enrich_document", "estimate_wacc"]


def derive_fcf_metrics(pe: float | None, p_fcf: float | None) -> tuple[float | None, float | None]:
    if p_fcf is None or p_fcf <= 0:
        return None, None
    fcf_to_ni = (pe / p_fcf) if pe is not None and pe > 0 else None
    return 100.0 / p_fcf, fcf_to_ni


def apply_derived(kpis: TickerKpis) -> TickerKpis:
    fcf_yield, fcf_to_ni = derive_fcf_metrics(kpis.pe, kpis.p_fcf)
    return replace(
        kpis,
        fcf_yield=kpis.fcf_yield if kpis.fcf_yield is not None else fcf_yield,
        fcf_to_ni=kpis.fcf_to_ni if kpis.fcf_to_ni is not None else fcf_to_ni,
    )


def enrich_document(document: dict[str, Any]) -> dict[str, Any]:
    kpis = apply_derived(TickerKpis.from_document(document))
    out = dict(document)
    out["attributes"] = kpis.attributes()
    for key in ("name", "sector", "industry", "market_cap"):
        value = getattr(kpis, key)
        if value:
            out[key] = value
    return out


@tool(
    "calculate_financials",
    "Derive FCF metrics and related estimates from raw market KPIs",
    {
        "type": "object",
        "properties": {"documents": {"type": "array"}},
        "required": ["documents"],
    },
)
def calculate_financials_tool(inputs: dict) -> dict:
    documents = [enrich_document(doc) for doc in (inputs.get("documents") or [])]
    return {
        "ok": True,
        "data": {
            "count": len(documents),
            "tickers": documents,
            "assumptions": {
                "risk_free_rate": RISK_FREE_RATE,
                "equity_risk_premium": EQUITY_RISK_PREMIUM,
            },
        },
    }
