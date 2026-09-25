"""Score input builders and sector-median helpers."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from utils.config import cfg
from utils.helpers import (
    infer_category,
    infer_tier,
    is_etf,
    median_numeric,
    median_positive,
    normalize_ratio,
    parse_numeric,
    resolve_upside_52w,
)
from utils.models import (
    MetricGroups,
    RelativeComparison,
    ScoreInputs,
    ScoreStatus,
    SectorMedians,
    Tier,
)


def build_sector_medians(entries: Sequence[dict[str, Any]]) -> dict[str, SectorMedians]:
    buckets: dict[str, dict[str, list[float]]] = {}
    for entry in entries:
        sector = (entry.get("sector") or "").strip()
        if not sector:
            continue
        attrs = entry.get("attributes") or {}
        bucket = buckets.setdefault(
            sector,
            {"pe": [], "fwd_pe": [], "p_fcf": [], "ev_ebitda": [], "ps": [], "oper_margin": []},
        )
        for field in ("pe", "fwd_pe", "p_fcf", "ev_ebitda", "ps"):
            raw = attrs.get(field)
            if raw is not None and isinstance(raw, (int, float)) and float(raw) > 0:
                bucket[field].append(float(raw))
        margin = attrs.get("oper_margin")
        if margin is not None and isinstance(margin, (int, float)):
            bucket["oper_margin"].append(float(margin))
    return {
        sector: SectorMedians(
            pe=median_positive(bucket["pe"]),
            fwd_pe=median_positive(bucket["fwd_pe"]),
            p_fcf=median_positive(bucket["p_fcf"]),
            ev_ebitda=median_positive(bucket["ev_ebitda"]),
            ps=median_positive(bucket["ps"]),
            oper_margin=median_numeric(bucket["oper_margin"]),
        )
        for sector, bucket in buckets.items()
    }


def ratio_vs_median(value: float | None, median: float | None) -> float | None:
    if value is None or median is None or value <= 0 or median <= 0:
        return None
    return value / median


def margin_vs_sector_median(margin: float | None, median_raw: float | None) -> float | None:
    if margin is None or median_raw is None:
        return None
    median = median_raw / 100.0 if abs(median_raw) > 1.5 else median_raw
    if median == 0:
        return None
    return margin / median


def _field_available(field: str, value: Any) -> bool:
    if value is None or not isinstance(value, (int, float)):
        return False
    numeric = float(value)
    if field == "debt_to_equity" and numeric >= 99:
        return False
    if field in {"pe", "fwd_pe", "peg", "p_fcf", "ps", "ev_ebitda"}:
        return numeric > 0
    return True


def count_available_metrics(attributes: dict[str, Any], tier: Tier) -> tuple[int, int, float, ScoreStatus]:
    applicable = list(MetricGroups.tracked())
    if tier == "speculative":
        applicable = [f for f in applicable if f not in ("pe", "fwd_pe", "peg", "p_fcf")]
    available = sum(1 for field in applicable if _field_available(field, attributes.get(field)))
    total = len(applicable)
    pct = (available / total * 100) if total else 0.0
    complete_pct = float(cfg("score", "completeness", "complete_pct", default=80))
    partial_pct = float(cfg("score", "completeness", "partial_pct", default=50))
    if pct >= complete_pct:
        status: ScoreStatus = "complete"
    elif pct >= partial_pct:
        status = "partial"
    else:
        status = "minimal"
    return available, total, round(pct, 1), status


def build_score_inputs(
    entry: dict[str, Any],
    sector_medians: dict[str, SectorMedians],
    rel: RelativeComparison | None,
) -> ScoreInputs | None:
    ticker = str(entry.get("ticker", "")).upper().strip()
    if not ticker:
        return None
    attributes = entry.get("attributes") or {}
    name = entry.get("name")
    sector = entry.get("sector")
    if is_etf(ticker, name, sector):
        return None
    current_price = parse_numeric(attributes.get("current_price")) or 0.0
    eps = parse_numeric(attributes.get("eps"))
    pe = parse_numeric(attributes.get("pe"))
    fwd_pe = parse_numeric(attributes.get("fwd_pe"))
    medians = sector_medians.get(sector or "", SectorMedians())
    return ScoreInputs(
        ticker=ticker,
        category=infer_category(ticker, name, sector),
        tier=infer_tier(eps, pe, fwd_pe),
        sector=sector,
        current_price=current_price,
        upside_52w=resolve_upside_52w(
            current_price,
            parse_numeric(attributes.get("high_52w")),
            parse_numeric(attributes.get("sma_25")),
        ),
        rsi=parse_numeric(attributes.get("rsi")) or 50.0,
        pe=pe,
        fwd_pe=fwd_pe,
        peg=parse_numeric(attributes.get("peg")),
        roe=normalize_ratio(parse_numeric(attributes.get("roe"))),
        roic=normalize_ratio(parse_numeric(attributes.get("roic"))),
        gross_margin=normalize_ratio(parse_numeric(attributes.get("gross_margin"))),
        oper_margin=normalize_ratio(parse_numeric(attributes.get("oper_margin"))),
        profit_margin=normalize_ratio(parse_numeric(attributes.get("profit_margin"))),
        debt_eq=parse_numeric(attributes.get("debt_to_equity")),
        lt_debt_eq=parse_numeric(attributes.get("lt_debt_to_equity")),
        eps_growth=normalize_ratio(parse_numeric(attributes.get("eps_growth"))),
        eps_yoy=normalize_ratio(parse_numeric(attributes.get("eps_yoy"))),
        eps_cagr_3y=normalize_ratio(parse_numeric(attributes.get("eps_cagr_3y"))),
        payout=normalize_ratio(parse_numeric(attributes.get("payout"))),
        beta=parse_numeric(attributes.get("beta")),
        ps=parse_numeric(attributes.get("ps")),
        p_fcf=parse_numeric(attributes.get("p_fcf")),
        ev_ebitda=parse_numeric(attributes.get("ev_ebitda")),
        fcf_yield=normalize_ratio(parse_numeric(attributes.get("fcf_yield"))),
        fcf_to_ni=parse_numeric(attributes.get("fcf_to_ni")),
        sales_growth=normalize_ratio(parse_numeric(attributes.get("sales_growth"))),
        sales_cagr_3y=normalize_ratio(parse_numeric(attributes.get("sales_cagr_3y"))),
        eps_next_y=normalize_ratio(parse_numeric(attributes.get("eps_next_y"))),
        current_ratio=parse_numeric(attributes.get("current_ratio")),
        cash_per_share=parse_numeric(attributes.get("cash_per_share")),
        alpha_year_etf=rel.alpha_year_vs_etf if rel else None,
        alpha_year_spy=rel.alpha_year_vs_spy if rel else None,
        pe_vs_sector=ratio_vs_median(pe, medians.pe),
        p_fcf_vs_sector=ratio_vs_median(parse_numeric(attributes.get("p_fcf")), medians.p_fcf),
        ps_vs_sector=ratio_vs_median(parse_numeric(attributes.get("ps")), medians.ps),
        ev_ebitda_vs_sector=ratio_vs_median(parse_numeric(attributes.get("ev_ebitda")), medians.ev_ebitda),
        oper_margin_vs_sector=margin_vs_sector_median(
            normalize_ratio(parse_numeric(attributes.get("oper_margin"))),
            medians.oper_margin,
        ),
        attributes=attributes,
    )
