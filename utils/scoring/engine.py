"""Score engine: ScoreResult builder, ranking, and batch scoring."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from utils.config import cfg, confirmed_strength, special_categories
from utils.helpers import is_etf
from utils.models import RelativeComparison, ScoreBatch, ScoreInputs, ScoreResult
from utils.scoring.blocks import (
    score_balance_block,
    score_growth_block,
    score_momentum_block,
    score_quality_block,
    score_valuation_block,
)
from utils.scoring.inputs import (
    build_score_inputs,
    build_sector_medians,
    count_available_metrics,
)


def calculate_score(
    inputs: ScoreInputs, name: str | None = None, rel: RelativeComparison | None = None
) -> ScoreResult:
    divergent = (
        inputs.eps_growth is not None
        and inputs.fcf_to_ni is not None
        and inputs.eps_growth > 0.05
        and inputs.fcf_to_ni < 0.5
    )
    b1, mode = score_valuation_block(inputs)
    b2 = score_growth_block(inputs)
    b3, wacc, roic_spread = score_quality_block(inputs, divergent)
    b4 = score_balance_block(inputs, inputs.category in special_categories())
    b5 = score_momentum_block(inputs)
    completeness_attrs = dict(inputs.attributes or {})
    completeness_attrs["upside_52w"] = inputs.upside_52w
    completeness_attrs["alpha_year_etf"] = inputs.alpha_year_etf
    completeness_attrs["alpha_year_spy"] = inputs.alpha_year_spy
    available, total, pct, status = count_available_metrics(completeness_attrs, inputs.tier)
    cycle_eps = float(cfg("score", "cycle_eps", default=0.12))
    cycle_sales = float(cfg("score", "cycle_sales", default=0.15))
    cycle_peak = (
        inputs.eps_next_y is not None
        and inputs.eps_next_y < 0
        and (
            (inputs.eps_growth is not None and inputs.eps_growth >= cycle_eps)
            or (inputs.sales_growth is not None and inputs.sales_growth >= cycle_sales)
        )
    )
    return ScoreResult(
        ticker=inputs.ticker,
        name=name,
        sector=inputs.sector,
        category=inputs.category or "-",
        tier=inputs.tier,
        valuation_mode=mode,
        score=b1.points + b2.points + b3.points + b4.points + b5.points,
        bloque_1=b1.points,
        bloque_2=b2.points,
        bloque_3=b3.points,
        bloque_4=b4.points,
        bloque_5=b5.points,
        completeness_pct=pct,
        score_status=status,
        metrics_available=available,
        metrics_total=total,
        benchmark_etf=rel.sector_etf if rel else None,
        alpha_year_vs_etf=rel.alpha_year_vs_etf if rel else inputs.alpha_year_etf,
        alpha_year_vs_spy=rel.alpha_year_vs_spy if rel else inputs.alpha_year_spy,
        alpha_ytd_vs_etf=rel.alpha_ytd_vs_etf if rel else None,
        relative_strength=rel.relative_strength if rel else "N/A",
        wacc_estimate=round(wacc, 4) if wacc else None,
        roic_spread=round(roic_spread, 4) if roic_spread is not None else None,
        earnings_cash_flag=divergent,
        cycle_peak=cycle_peak,
    )


def ranking_key(item: ScoreResult) -> tuple[int, int]:
    return (0 if item.score_status == "complete" else 1, -item.score)


def select_confirmed(results: Sequence[ScoreResult]) -> list[ScoreResult]:
    min_score = int(cfg("score", "confirmed_min_score", default=70))
    return sorted(
        [
            item
            for item in results
            if item.score_status == "complete"
            and not item.cycle_peak
            and item.score >= min_score
            and item.relative_strength in confirmed_strength()
        ],
        key=ranking_key,
    )


def select_dislocated(results: Sequence[ScoreResult]) -> list[ScoreResult]:
    quality_high = int(cfg("score", "quality_high", default=20))
    balance_high = int(cfg("score", "balance_high", default=10))
    valuation_floor = int(cfg("score", "valuation_floor", default=10))
    strength = str(cfg("score", "dislocated_strength", default="WEAK"))
    return sorted(
        [
            item
            for item in results
            if item.score_status == "complete"
            and not item.cycle_peak
            and item.bloque_3 >= quality_high
            and item.bloque_4 >= balance_high
            and item.bloque_1 >= valuation_floor
            and item.relative_strength == strength
        ],
        key=ranking_key,
    )


def score_all_entries(
    entries: Sequence[dict[str, Any]],
    all_entries: Sequence[dict[str, Any]] | None = None,
    comparisons: dict[str, Any] | None = None,
) -> ScoreBatch:
    full_entries = list(all_entries or entries)
    sector_medians = build_sector_medians(full_entries)
    # comparisons: dict[str, dict] from compare_performance tool, OR dict[str, RelativeComparison]
    rel_map: dict[str, RelativeComparison] = {}
    if comparisons:
        for k, v in comparisons.items():
            key = str(k).upper()
            if isinstance(v, RelativeComparison):
                rel_map[key] = v
            elif isinstance(v, dict):
                payload = {kk: vv for kk, vv in v.items() if kk in RelativeComparison.__dataclass_fields__}
                rel_map[key] = RelativeComparison(**payload)
    core: list[ScoreResult] = []
    speculative: list[ScoreResult] = []
    skipped_etfs: list[str] = []
    skipped_minimal: list[str] = []
    for entry in entries:
        ticker = str(entry.get("ticker", "")).upper().strip()
        if not ticker:
            continue
        if is_etf(ticker, entry.get("name"), entry.get("sector")):
            skipped_etfs.append(ticker)
            continue
        rel = rel_map.get(ticker)
        inputs = build_score_inputs(entry, sector_medians, rel)
        if inputs is None:
            continue
        result = calculate_score(inputs, name=entry.get("name"), rel=rel)
        if result.score_status == "minimal":
            skipped_minimal.append(ticker)
        elif result.tier == "core":
            core.append(result)
        else:
            speculative.append(result)
    core.sort(key=ranking_key)
    speculative.sort(key=ranking_key)
    ranked = [*core, *speculative]
    return ScoreBatch(
        core,
        speculative,
        rel_map,
        skipped_etfs,
        select_confirmed(ranked),
        select_dislocated(ranked),
        skipped_minimal,
    )
