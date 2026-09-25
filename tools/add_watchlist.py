"""add_watchlist — Tool: append propuestas confirmadas/dislocadas a docs/watchlist.csv."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from typing import Any

from tools.registry import tool
from utils.helpers import (
    PORTFOLIO_PATH,
    WATCHLIST_PATH,
    append_csv_rows,
    load_known_symbols,
)
from utils.models import WATCHLIST_COLUMNS


def watchlist_row(
    result: dict[str, Any],
    document: dict[str, Any],
    meta: dict[str, Any],
    kind: str,
    today: str,
) -> dict[str, str]:
    attributes = document.get("attributes") or {}
    details: list[str] = []
    pe, fcf_yield = attributes.get("pe"), attributes.get("fcf_yield")
    if isinstance(pe, (int, float)):
        details.append(f"PE {pe:.0f}")
    if isinstance(fcf_yield, (int, float)):
        details.append(f"FCF yield {fcf_yield:.1f}%")
    details.append("fuera de portfolio")
    return {
        "ticker": str(result.get("ticker") or ""),
        "name": str(result.get("name") or document.get("name") or ""),
        "sector": str(result.get("sector") or document.get("sector") or ""),
        "industry": str(document.get("industry") or ""),
        "theme": str(meta.get("theme") or ""),
        "subtheme": str(meta.get("subtheme") or ""),
        "marketcap": str(document.get("market_cap") or meta.get("market_cap") or ""),
        "price": str(attributes.get("current_price") or ""),
        "date": today,
        "kind": kind,
        "score": str(result.get("score") or ""),
        "valuation": str(result.get("bloque_1") or ""),
        "growth": str(result.get("bloque_2") or ""),
        "quality": str(result.get("bloque_3") or ""),
        "balance": str(result.get("bloque_4") or ""),
        "momentum": str(result.get("bloque_5") or ""),
        "relative_strength": str(result.get("relative_strength") or ""),
        "notes": ", ".join(details),
    }


def build_proposals(
    scored: dict[str, Any],
    documents: Sequence[dict[str, Any]],
    *,
    known: set[str] | None = None,
    meta_by_ticker: dict[str, dict] | None = None,
    score_tickers: set[str] | None = None,
) -> list[dict[str, str]]:
    skip = known or set()
    meta = meta_by_ticker or {}
    by_ticker = {str(doc.get("ticker", "")).upper(): doc for doc in documents}
    today, rows = date.today().isoformat(), []
    for kind in ("confirmed", "dislocated"):
        for result in scored.get(kind) or []:
            ticker = str(result.get("ticker") or "").upper()
            if ticker in skip:
                continue
            if score_tickers is not None and ticker not in score_tickers:
                continue
            rows.append(watchlist_row(result, by_ticker.get(ticker, {}), meta.get(ticker, {}), kind, today))
    return rows


@tool(
    "add_watchlist",
    "Build watchlist proposal rows and optionally append to docs/watchlist.csv",
    {
        "type": "object",
        "properties": {
            "scored": {"type": "object"},
            "documents": {"type": "array"},
            "meta_by_ticker": {"type": "object"},
            "score_tickers": {"type": "array", "items": {"type": "string"}},
            "skip_known": {"type": "boolean", "default": True},
            "write": {"type": "boolean", "default": False},
            "path": {"type": "string"},
        },
        "required": ["scored", "documents"],
    },
)
def add_watchlist_tool(inputs: dict) -> dict:
    known: set[str] = set()
    if inputs.get("skip_known", True):
        known = load_known_symbols(PORTFOLIO_PATH) | load_known_symbols(WATCHLIST_PATH)
    score_tickers = inputs.get("score_tickers")
    rows = build_proposals(
        inputs.get("scored") or {},
        inputs.get("documents") or [],
        known=known,
        meta_by_ticker=inputs.get("meta_by_ticker") or {},
        score_tickers={str(t).upper() for t in score_tickers} if score_tickers else None,
    )
    path = inputs.get("path") or str(WATCHLIST_PATH)
    written = 0
    if inputs.get("write") and rows:
        append_csv_rows(path, WATCHLIST_COLUMNS, rows)
        written = len(rows)
    return {
        "ok": True,
        "data": {
            "count": len(rows),
            "written": written,
            "path": path if written else None,
            "rows": rows,
        },
    }
