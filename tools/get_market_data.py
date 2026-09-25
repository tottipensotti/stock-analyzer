"""get_market_data — Tool: KPIs de mercado (analysis) o subset de comparación."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Literal

from tools.registry import tool
from utils.config import cfg
from utils.extractors import get_extractor
from utils.helpers import (
    load_ticker_cache,
    normalize_ticker_list,
    save_ticker_cache,
    utc_now_iso,
)
from utils.models import COMPARISON_FIELDS, MarketDocument, TickerKpis

logger = logging.getLogger(__name__)
DEFAULT_WORKERS = int(cfg("market", "default_workers", default=8))
Mode = Literal["analysis", "comparison"]


def build_document(
    kpis: TickerKpis,
    *,
    sources: Sequence[str] = (),
    mode: Mode = "analysis",
    fetched_at: str | None = None,
) -> dict[str, Any]:
    return MarketDocument.from_kpis(
        kpis,
        fetched_at=fetched_at or utc_now_iso(),
        sources=sources,
        mode=mode,
    ).to_dict()


def _slim_for_comparison(document: dict[str, Any]) -> dict[str, Any]:
    attrs = document.get("attributes") or {}
    slimmed = {key: attrs[key] for key in COMPARISON_FIELDS if attrs.get(key) is not None}
    if slimmed.keys() == attrs.keys():
        return document
    out = dict(document)
    out["attributes"] = slimmed
    return out


def build_batch(documents: Sequence[dict[str, Any]], fetched_at: str | None = None) -> dict[str, Any]:
    return {
        "fetched_at": fetched_at or utc_now_iso(),
        "count": len(documents),
        "tickers": list(documents),
    }


def extract_one(
    ticker: str,
    source: str,
    mode: Mode,
    cache_dir: Path | None = None,
) -> dict[str, Any] | None:
    symbol = ticker.upper().strip()
    if not symbol:
        return None

    cached = load_ticker_cache(cache_dir, symbol)
    if cached is not None:
        return _slim_for_comparison(cached) if mode == "comparison" else cached

    try:
        required = COMPARISON_FIELDS if mode == "comparison" else None
        result = get_extractor(source).extract(symbol, required_fields=required)
        if result.kpis.populated_count() == 0:
            raise ValueError(f"Sin KPIs para {symbol}")
    except Exception as err:  # noqa: BLE001 — un ticker no tumba el batch
        logger.error("No se pudieron obtener KPIs para %s: %s", symbol, err)
        return None

    document = build_document(result.kpis, sources=result.sources, mode="analysis")
    save_ticker_cache(cache_dir, symbol, document)
    return _slim_for_comparison(document) if mode == "comparison" else document


def extract_documents(
    tickers: Sequence[str],
    *,
    source: str = "auto",
    workers: int = DEFAULT_WORKERS,
    mode: Mode = "analysis",
    cache_dir: Path | None = None,
) -> list[dict[str, Any]]:
    symbols = normalize_ticker_list(tickers)
    if not symbols:
        return []
    worker_count = max(1, workers)
    if worker_count == 1 or len(symbols) == 1:
        return [
            doc for symbol in symbols if (doc := extract_one(symbol, source, mode, cache_dir)) is not None
        ]
    logger.info("Extrayendo %s tickers con %s workers (%s)", len(symbols), worker_count, mode)
    by_symbol: dict[str, dict[str, Any] | None] = {symbol: None for symbol in symbols}
    with ThreadPoolExecutor(max_workers=worker_count) as pool:
        futures = {pool.submit(extract_one, symbol, source, mode, cache_dir): symbol for symbol in symbols}
        for future in as_completed(futures):
            by_symbol[futures[future]] = future.result()
    return [doc for symbol in symbols if (doc := by_symbol[symbol]) is not None]


@tool(
    "get_market_data",
    "Fetch market KPIs (mode=analysis) or comparison subset (mode=comparison)",
    {
        "type": "object",
        "properties": {
            "tickers": {"type": "array", "items": {"type": "string"}},
            "mode": {
                "type": "string",
                "enum": ["analysis", "comparison"],
                "default": "analysis",
            },
            "source": {
                "type": "string",
                "enum": ["auto", "finviz", "stooq", "yfinance"],
                "default": "auto",
            },
            "workers": {"type": "integer", "default": DEFAULT_WORKERS},
            "cache_dir": {"type": "string"},
        },
        "required": ["tickers"],
    },
)
def get_market_data_tool(inputs: dict) -> dict:
    mode = inputs.get("mode") or "analysis"
    if mode not in {"analysis", "comparison"}:
        return {"ok": False, "error": f"mode inválido: {mode}"}
    cache_raw = inputs.get("cache_dir")
    cache_dir = Path(cache_raw) if cache_raw else None
    documents = extract_documents(
        inputs.get("tickers") or [],
        source=inputs.get("source") or "auto",
        workers=int(inputs.get("workers") or DEFAULT_WORKERS),
        mode=mode,
        cache_dir=cache_dir,
    )
    return {"ok": True, "data": build_batch(documents)}
