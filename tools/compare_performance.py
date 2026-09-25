"""compare_performance — Tool: alpha vs SPY, ETF de industria y peers."""

from __future__ import annotations

from collections.abc import Sequence
from functools import lru_cache
from typing import Any

import yaml

from tools.registry import tool
from utils.config import cfg
from utils.helpers import CATALOG_PATH, parse_numeric
from utils.models import MARKET_BENCHMARK, RelativeComparison, RelativeStrength

_INDUSTRY_OVERRIDES = cfg("industry_etf_overrides") or {}
INDUSTRY_ETF_OVERRIDES: tuple[tuple[str, str | None], ...] = tuple(
    (str(needle), None if etf is None else str(etf))
    for needle, etf in _INDUSTRY_OVERRIDES.items()
)
PERF_FIELDS = {
    "month": "perf_month",
    "quarter": "perf_quarter",
    "half_y": "perf_half_y",
    "ytd": "perf_ytd",
    "year": "perf_year",
    "3y": "perf_3y",
    "5y": "perf_5y",
}
_NEUTRAL_BAND = float(cfg("relative_strength", "neutral_band_abs", default=2.0))


@lru_cache(maxsize=1)
def _sector_etf_map() -> dict[str, str]:
    raw = yaml.safe_load(CATALOG_PATH.read_text(encoding="utf-8")) or {}
    return {
        str(item["key"]): str(item["etf"])
        for item in (raw.get("sectors") or [])
        if isinstance(item, dict) and item.get("etf")
    }


def _norm_label(value: str) -> str:
    return value.strip().lower().replace("&", "and").replace("/", " ").replace("-", " ")


def resolve_benchmark_etf(sector: str | None, industry: str | None = None) -> str | None:
    industry_name = (industry or "").lower()
    for needle, etf in INDUSTRY_ETF_OVERRIDES:
        if needle in industry_name:
            return etf
    if not sector:
        return None
    needle = _norm_label(sector)
    mapping = _sector_etf_map()
    if needle in mapping:
        return mapping[needle]
    for key, etf in mapping.items():
        if _norm_label(key) == needle:
            return etf
    return mapping.get(sector.strip().lower())


def needed_benchmark_tickers(documents: Sequence[dict[str, Any]]) -> list[str]:
    needed = [MARKET_BENCHMARK]
    seen = {MARKET_BENCHMARK}
    for document in documents:
        etf = resolve_benchmark_etf(document.get("sector"), document.get("industry"))
        if etf and etf not in seen:
            seen.add(etf)
            needed.append(etf)
    return needed


def all_known_benchmark_tickers() -> frozenset[str]:
    return frozenset({MARKET_BENCHMARK, *_sector_etf_map().values()})


def _get_perf(attributes: dict[str, Any], field: str) -> float | None:
    return parse_numeric(attributes.get(field))


def compute_alpha(stock_perf: float | None, benchmark_perf: float | None) -> float | None:
    if stock_perf is None or benchmark_perf is None:
        return None
    return round(stock_perf - benchmark_perf, 2)


def classify_relative_strength(
    alpha_year_etf: float | None,
    alpha_ytd_etf: float | None,
    alpha_year_spy: float | None,
    alpha_ytd_spy: float | None,
) -> RelativeStrength:
    if alpha_year_etf is None and alpha_year_spy is None:
        return "N/A"
    if alpha_year_etf is None:
        if (alpha_year_spy or 0) > 0 and (alpha_ytd_spy or 0) > 0:
            return "LEADING"
        if alpha_year_spy is not None and alpha_year_spy > 0:
            return "STRONG"
        if alpha_year_spy is not None and alpha_year_spy < 0:
            return "WEAK"
        return "NEUTRAL"
    beats_etf_year = alpha_year_etf > 0
    beats_etf_ytd = alpha_ytd_etf is not None and alpha_ytd_etf > 0
    beats_spy_year = alpha_year_spy is not None and alpha_year_spy > 0
    if beats_etf_year and beats_spy_year and beats_etf_ytd:
        return "LEADING"
    if beats_etf_year and beats_spy_year:
        return "STRONG"
    if abs(alpha_year_etf) <= _NEUTRAL_BAND:
        return "NEUTRAL"
    if alpha_year_etf < 0 and alpha_year_spy is not None and alpha_year_spy < 0:
        return "WEAK"
    if alpha_year_etf < 0:
        return "LAGGING"
    if beats_etf_year:
        return "STRONG"
    return "NEUTRAL"


def compare_ticker(
    entry: dict[str, Any],
    perf_index: dict[str, dict[str, float | None]],
    peer_tickers: Sequence[str] | None = None,
) -> dict[str, Any]:
    ticker = str(entry.get("ticker", "")).upper().strip()
    attrs = entry.get("attributes") or {}
    sector_etf = resolve_benchmark_etf(entry.get("sector"), entry.get("industry"))
    stock_year, stock_ytd = _get_perf(attrs, "perf_year"), _get_perf(attrs, "perf_ytd")
    etf_perf = perf_index.get(sector_etf or "", {}) if sector_etf else {}
    spy_perf = perf_index.get(MARKET_BENCHMARK, {})
    alpha_year_etf = compute_alpha(stock_year, etf_perf.get("year"))
    alpha_ytd_etf = compute_alpha(stock_ytd, etf_perf.get("ytd"))
    alpha_year_spy = compute_alpha(stock_year, spy_perf.get("year"))
    alpha_ytd_spy = compute_alpha(stock_ytd, spy_perf.get("ytd"))
    peer_alphas: dict[str, float | None] = {}
    for peer in peer_tickers or []:
        if peer == ticker:
            continue
        peer_perf = perf_index.get(peer, {})
        peer_alphas[peer] = compute_alpha(stock_year, peer_perf.get("year"))
    return RelativeComparison(
        ticker=ticker,
        sector_etf=sector_etf,
        perf_year=stock_year,
        perf_ytd=stock_ytd,
        alpha_year_vs_etf=alpha_year_etf,
        alpha_ytd_vs_etf=alpha_ytd_etf,
        alpha_year_vs_spy=alpha_year_spy,
        alpha_ytd_vs_spy=alpha_ytd_spy,
        relative_strength=classify_relative_strength(
            alpha_year_etf, alpha_ytd_etf, alpha_year_spy, alpha_ytd_spy
        ),
    ).__dict__ | {"alpha_year_vs_peers": peer_alphas}


def build_perf_index(entries: list[dict[str, Any]]) -> dict[str, dict[str, float | None]]:
    index: dict[str, dict[str, float | None]] = {}
    for entry in entries:
        ticker = str(entry.get("ticker", "")).upper().strip()
        if not ticker:
            continue
        attrs = entry.get("attributes") or {}
        index[ticker] = {period: _get_perf(attrs, field_name) for period, field_name in PERF_FIELDS.items()}
    return index


def format_alpha(value: float | None) -> str:
    if value is None:
        return "N/A"
    sign = "+" if value > 0 else ""
    return f"{sign}{value:.1f}%"


@tool(
    "compare_performance",
    "Compare tickers vs SPY, industry ETF and optional peers",
    {
        "type": "object",
        "properties": {
            "entries": {"type": "array"},
            "subjects": {"type": "array", "items": {"type": "string"}},
            "peers": {"type": "array", "items": {"type": "string"}},
            "list_benchmarks": {"type": "boolean"},
        },
        "required": ["entries"],
    },
)
def compare_performance_tool(inputs: dict) -> dict:
    entries = list(inputs.get("entries") or [])
    if inputs.get("list_benchmarks"):
        return {"ok": True, "data": {"tickers": needed_benchmark_tickers(entries)}}
    subjects = {str(t).upper() for t in (inputs.get("subjects") or [])} or None
    peers = [str(t).upper() for t in (inputs.get("peers") or [])]
    perf_index = build_perf_index(entries)
    excluded = set(all_known_benchmark_tickers())
    comparisons: dict[str, Any] = {}
    for entry in entries:
        ticker = str(entry.get("ticker", "")).upper().strip()
        if not ticker or ticker in excluded:
            continue
        if subjects is not None and ticker not in subjects:
            continue
        comparisons[ticker] = compare_ticker(entry, perf_index, peer_tickers=peers)
    return {"ok": True, "data": comparisons}
