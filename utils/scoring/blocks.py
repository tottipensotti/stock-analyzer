"""Scoring ladders and per-block scorers."""

from __future__ import annotations

from collections.abc import Callable, Sequence

from utils.config import score_block_max
from utils.helpers import estimate_wacc, is_financial_sector, positive
from utils.models import BlockScore, MetricScore, ScoreInputs, ValuationMode


def _ladder(value: float, rungs: Sequence[tuple[float, int]], *, higher: bool, default: int = 0) -> int:
    for limit, pts in rungs:
        if value >= limit if higher else value <= limit:
            return pts
    return default


def _lte(rungs: Sequence[tuple[float, int]], default: int = 0):
    def _score(value: float) -> int:
        return _ladder(value, rungs, higher=False, default=default)

    return _score


def _gt(rungs: Sequence[tuple[float, int]], default: int = 0):
    def _score(value: float) -> int:
        return _ladder(value, rungs, higher=True, default=default)

    return _score


def normalize_block(metrics: list[MetricScore], block_max: int) -> BlockScore:
    available = [item for item in metrics if item.available]
    if not available:
        return BlockScore(0, block_max, metrics)
    earned = sum(item.points for item in available)
    possible = sum(item.max_points for item in available)
    scaled = round(earned / possible * block_max) if possible else 0
    return BlockScore(min(scaled, block_max), block_max, metrics)


def metric(
    name: str,
    value: float | None,
    scorer: Callable[[float], int],
    max_points: int,
    *,
    valid: Callable[[float | None], bool] = lambda v: v is not None,
) -> MetricScore:
    if not valid(value):
        return MetricScore(name, 0, max_points, False)
    return MetricScore(name, scorer(value), max_points, True)  # type: ignore[arg-type]


def s_margin(value: float, high: float, mid: float) -> int:
    if value >= high:
        return 4 if high >= 0.20 else 3
    return 2 if value >= mid else 1 if value > 0 else 0


def s_rate(value: float) -> int:
    return _ladder(value, ((0.20, 4), (0.10, 3), (0.05, 2)), higher=True, default=1 if value > 0 else 0)


def s_cagr(value: float) -> int:
    return _ladder(value, ((0.15, 2), (0.08, 1)), higher=True, default=1 if value > 0 else 0)


def s_roe(value: float) -> int:
    return _ladder(value, ((0.18, 5), (0.10, 3)), higher=True, default=1 if value > 0 else 0)


def s_sales_val(value: float) -> int:
    return _ladder(value, ((0.25, 4), (0.15, 3), (0.05, 2)), higher=True, default=1 if value > 0 else 0)


def _debt_ok(value: float | None) -> bool:
    return value is not None and value < 90


def _payout_ok(value: float | None) -> bool:
    return value is not None and value >= 0


def score_valuation_block(inputs: ScoreInputs) -> tuple[BlockScore, ValuationMode]:
    cheap = _lte(((0.75, 3), (0.95, 2), (1.1, 1)))
    if inputs.tier == "core":
        return normalize_block(
            [
                metric("fwd_pe", inputs.fwd_pe, _lte(((15, 7), (25, 5)), 2), 7, valid=positive),
                metric("pe", inputs.pe, _lte(((15, 4), (25, 2)), 1), 4, valid=positive),
                metric("peg", inputs.peg, _lte(((1, 4), (1.8, 2))), 4, valid=positive),
                metric("p_fcf", inputs.p_fcf, _lte(((15, 4), (30, 2)), 1), 4, valid=positive),
                metric("ev_ebitda", inputs.ev_ebitda, _lte(((12, 3), (20, 2), (35, 1))), 3, valid=positive),
                metric("pe_vs_sector", inputs.pe_vs_sector, cheap, 3, valid=positive),
                metric("p_fcf_vs_sector", inputs.p_fcf_vs_sector, cheap, 2, valid=positive),
            ],
            score_block_max("valuation"),
        ), "earnings"
    return normalize_block(
        [
            metric("ps", inputs.ps, _lte(((8, 5), (20, 3), (40, 1))), 5, valid=positive),
            metric("sales_growth", inputs.sales_growth, s_sales_val, 4),
            metric("eps_next_y", inputs.eps_next_y, _gt(((0.20, 3), (0.10, 2)), 1), 3, valid=positive),
            metric("ps_vs_sector", inputs.ps_vs_sector, cheap, 3, valid=positive),
            metric("ev_ebitda_vs_sector", inputs.ev_ebitda_vs_sector, cheap, 2, valid=positive),
        ],
        score_block_max("valuation"),
    ), "growth"


def score_growth_block(inputs: ScoreInputs) -> BlockScore:
    block = normalize_block(
        [
            metric("sales_growth", inputs.sales_growth, s_rate, 7),
            metric("eps_growth", inputs.eps_growth, s_rate, 5),
            metric("eps_yoy", inputs.eps_yoy, s_rate, 3),
            metric("sales_cagr_3y", inputs.sales_cagr_3y, s_cagr, 2, valid=positive),
            metric("eps_cagr_3y", inputs.eps_cagr_3y, s_cagr, 3, valid=positive),
        ],
        score_block_max("growth"),
    )
    if inputs.eps_next_y is not None and inputs.eps_next_y < 0:
        block.points //= 2
    return block


def score_quality_block(
    inputs: ScoreInputs, divergent: bool
) -> tuple[BlockScore, float | None, float | None]:
    wacc = estimate_wacc(inputs.beta)
    financial = is_financial_sector(inputs.sector)
    roic_spread = (inputs.roic - wacc) if inputs.roic is not None else None
    roic_ok = roic_spread is not None and not financial
    roic_metric = MetricScore(
        "roic_spread",
        _ladder(roic_spread, ((0.10, 8), (0.05, 6), (0.0, 4), (-0.05, 2)), higher=True) if roic_ok else 0,
        8,
        roic_ok,
    )
    oper = (
        metric(
            "oper_margin_vs_sector",
            inputs.oper_margin_vs_sector,
            _gt(((1.15, 4), (0.90, 2), (0.70, 1))),
            4,
        )
        if inputs.oper_margin_vs_sector is not None
        else metric("oper_margin", inputs.oper_margin, lambda v: s_margin(v, 0.20, 0.10), 4)
    )
    fcf_pts = 0
    if inputs.fcf_to_ni is not None and not divergent:
        fcf_pts = _ladder(
            inputs.fcf_to_ni,
            ((0.9, 4), (0.7, 3), (0.5, 2)),
            higher=True,
            default=1 if inputs.fcf_to_ni > 0 else 0,
        )
    metrics = [
        metric("roe", inputs.roe, s_roe, 5),
        roic_metric,
        metric("gross_margin", inputs.gross_margin, lambda v: s_margin(v, 0.40, 0.25), 4),
        oper,
        metric("profit_margin", inputs.profit_margin, lambda v: s_margin(v, 0.15, 0.08), 3),
        MetricScore("fcf_to_ni", fcf_pts, 4, inputs.fcf_to_ni is not None),
        metric("fcf_yield", inputs.fcf_yield, _gt(((0.06, 2), (0.03, 1))), 2, valid=positive),
    ]
    if inputs.tier == "speculative" and inputs.current_ratio is not None:
        metrics.append(
            metric("liquidity_spec", inputs.current_ratio, _gt(((1.5, 2), (1.0, 1))), 2, valid=positive)
        )
    return normalize_block(metrics, score_block_max("quality")), wacc, roic_spread


def score_balance_block(inputs: ScoreInputs, is_special: bool) -> BlockScore:
    if is_special:
        max_pts = score_block_max("balance")
        return BlockScore(max_pts, max_pts, [])
    liq = _gt(((1.5, 2), (1.0, 1)))
    payout = _lte(((0.5, 3), (0.7, 2)))
    lt_debt = _lte(((0.6, 3), (1.0, 2)), 1)
    if is_financial_sector(inputs.sector):
        return normalize_block(
            [
                metric("lt_debt_eq", inputs.lt_debt_eq, lt_debt, 3, valid=_debt_ok),
                metric("payout", inputs.payout, payout, 3, valid=_payout_ok),
                metric("current_ratio", inputs.current_ratio, liq, 2, valid=positive),
            ],
            score_block_max("balance"),
        )
    return normalize_block(
        [
            metric("debt_eq", inputs.debt_eq, _lte(((0.8, 5), (1.5, 3)), 1), 5, valid=_debt_ok),
            metric("lt_debt_eq", inputs.lt_debt_eq, lt_debt, 3, valid=_debt_ok),
            metric("ev_ebitda", inputs.ev_ebitda, _lte(((15, 2), (25, 1))), 2, valid=positive),
            metric("payout", inputs.payout, payout, 3, valid=_payout_ok),
            metric("current_ratio", inputs.current_ratio, liq, 2, valid=positive),
        ],
        score_block_max("balance"),
    )


def score_momentum_block(inputs: ScoreInputs) -> BlockScore:
    return normalize_block(
        [
            metric("rsi", inputs.rsi, lambda v: 2 if v <= 35 else 1 if v <= 55 else 0, 2),
            metric("upside_52w", inputs.upside_52w, lambda v: 1 if v <= 0.30 else 0, 1),
            metric("beta", inputs.beta, lambda v: 1 if v <= 1.1 else 0, 1, valid=positive),
            metric("alpha_year_etf", inputs.alpha_year_etf, _gt(((15, 3), (5, 2), (0, 1), (-10, 0))), 3),
            metric("alpha_year_spy", inputs.alpha_year_spy, _gt(((15, 3), (5, 2), (0, 1), (-10, 0))), 3),
        ],
        score_block_max("momentum"),
    )
