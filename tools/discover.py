"""discover — Tool: screener Finviz y peers de industria."""

from __future__ import annotations

import itertools
import logging
import re
import time
from collections.abc import Sequence
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from tools.registry import tool
from utils.config import cfg
from utils.helpers import CATALOG_PATH, fetch_url
from utils.models import MARKET_BENCHMARK, FilterKind, ScreenerSpec, TickerDiscoveryMeta

logger = logging.getLogger(__name__)

SCREENER_URL = "https://finviz.com/screener.ashx?v=111&f={filters}&o={order}&r={offset}"
PAGE_SIZE = int(cfg("discover", "page_size", default=20))
DEFAULT_LIMIT = int(cfg("discover", "default_limit", default=100))
DEFAULT_PEER_COUNT = int(cfg("discover", "default_peer_count", default=10))
PEER_SORT_ORDER = str(cfg("discover", "peer_sort_order", default="-perf52w"))
REQUEST_PAUSE_SECONDS = float(cfg("discover", "request_pause_seconds", default=0.8))

_SECTIONS: dict[FilterKind, str] = {
    "sector": "sectors",
    "industry": "industries",
    "theme": "themes",
    "subtheme": "subthemes",
    "market_cap": "market_caps",
}


@lru_cache(maxsize=1)
def load_catalog(path: str | None = None) -> dict[str, Any]:
    catalog_path = Path(path) if path else CATALOG_PATH
    raw = yaml.safe_load(catalog_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"Catálogo inválido: {catalog_path}")
    return raw


def default_market_cap(path: str | None = None) -> str:
    return str(load_catalog(path).get("default_market_cap") or "largeover")


def catalog_items(kind: FilterKind, path: str | None = None) -> tuple[dict[str, Any], ...]:
    items = load_catalog(path).get(_SECTIONS[kind])
    if not isinstance(items, list) or not items:
        raise ValueError(f"Catálogo sin {_SECTIONS[kind]}")
    return tuple(items)


def filter_map(kind: FilterKind, path: str | None = None) -> dict[str, str]:
    return {str(item["key"]): str(item["filter"]) for item in catalog_items(kind, path)}


def resolve_filter(kind: FilterKind, key: str, path: str | None = None) -> str:
    normalized = key.strip().lower()
    mapping = filter_map(kind, path)
    if normalized in mapping:
        return mapping[normalized]
    hint = ", ".join(sorted(mapping)[:8])
    raise ValueError(f"{kind} desconocido: {key!r}. Usá --list. Ej: {hint}, ...")


def _norm_label(value: str) -> str:
    return value.strip().lower().replace("&", "and").replace("/", " ").replace("-", " ")


def key_from_label(kind: FilterKind, label: str, path: str | None = None) -> str | None:
    needle = _norm_label(label)
    if not needle:
        return None
    for item in catalog_items(kind, path):
        if (
            _norm_label(str(item.get("key", ""))) == needle
            or _norm_label(str(item.get("label", ""))) == needle
        ):
            return str(item.get("key", "")) or None
    return None


def format_catalog_list(query: str | None = None) -> str:
    needle = (query or "").strip().lower()
    lines: list[str] = []
    sections: list[tuple[str, FilterKind, bool]] = [
        ("MARKET CAP", "market_cap", True),
        ("SECTORES", "sector", True),
        ("INDUSTRIES", "industry", False),
        ("THEMES", "theme", False),
        ("SUBTHEMES", "subtheme", False),
    ]
    for title, kind, show_extra in sections:
        items = catalog_items(kind)
        matched = [
            item
            for item in items
            if not needle
            or needle in str(item.get("key", "")).lower()
            or needle in str(item.get("label", "")).lower()
            or needle in str(item.get("filter", "")).lower()
        ]
        lines.append(f"=== {title} ({len(matched)}) ===")
        if not matched:
            lines.append("(sin matches)")
        else:
            width = 28 if kind in {"market_cap", "sector"} else 44
            for item in matched:
                extra = f"  etf={item['etf']}" if show_extra and item.get("etf") else ""
                lines.append(f"  {item['key']:<{width}} {item['filter']:<36}{extra}")
        lines.append("")
    lines.append("Uso: --market-cap KEY --sector KEY --industry KEY --theme KEY --subtheme KEY")
    return "\n".join(lines)


def _known_benchmarks() -> frozenset[str]:
    return frozenset({MARKET_BENCHMARK, *{str(i["etf"]) for i in catalog_items("sector") if i.get("etf")}})


def parse_screener_tickers(html: str) -> list[str]:
    table_match = re.search(r'class="[^"]*screener_table.*?</table>', html, re.IGNORECASE | re.DOTALL)
    if not table_match:
        return []
    ordered, seen = [], set()
    for ticker in re.findall(r'data-boxover-ticker="([A-Z0-9.\-]+)"', table_match.group(0)):
        if ticker not in seen:
            seen.add(ticker)
            ordered.append(ticker)
    return ordered


def _or_filter_group(prefix: str, codes: Sequence[str]) -> str | None:
    if not codes:
        return None
    if len(codes) == 1:
        return codes[0]
    return f"{prefix}_{'|'.join(code.split('_', 1)[1] for code in codes)}"


def build_screener_specs(
    *,
    sectors: Sequence[str],
    industries: Sequence[str],
    themes: Sequence[str],
    subthemes: Sequence[str],
    market_cap: str | None,
) -> list[ScreenerSpec]:
    cap_key = (market_cap or default_market_cap()).strip().lower()
    cap_code = resolve_filter("market_cap", cap_key)
    sub_codes = [resolve_filter("subtheme", key) for key in subthemes]
    sub_filter = _or_filter_group("subtheme", sub_codes)
    sub_label = " | ".join(subthemes) if subthemes else ""
    specs: list[ScreenerSpec] = []
    for sector_key, industry_key, theme_key in itertools.product(
        list(sectors) or [None], list(industries) or [None], list(themes) or [None]
    ):
        parts, label_bits, theme_label = (
            ["geo_usa", cap_code, "fa_pe_profitable"],
            [f"cap:{cap_key}"],
            "",
        )
        if sector_key:
            parts.append(resolve_filter("sector", sector_key))
            label_bits.append(f"sec:{sector_key}")
        if industry_key:
            parts.append(resolve_filter("industry", industry_key))
            label_bits.append(f"ind:{industry_key}")
        if theme_key:
            parts.append(resolve_filter("theme", theme_key))
            label_bits.append(f"theme:{theme_key}")
            theme_label = theme_key
        if sub_filter:
            parts.append(sub_filter)
            label_bits.append(f"sub:{sub_label}")
        specs.append(ScreenerSpec(" ".join(label_bits), ",".join(parts), theme_label, sub_label, cap_key))
    return specs


def discover_tickers(spec: ScreenerSpec, limit: int, pause: float, *, order: str = "") -> list[str]:
    collected, seen, offset = [], set(), 1
    while len(collected) < limit:
        html = fetch_url(SCREENER_URL.format(filters=spec.filters, order=order, offset=offset), timeout=25)
        page = parse_screener_tickers(html)
        fresh = [ticker for ticker in page if ticker not in seen]
        if not fresh:
            break
        for ticker in fresh:
            seen.add(ticker)
            collected.append(ticker)
            if len(collected) >= limit:
                break
        if len(page) < PAGE_SIZE:
            break
        offset += PAGE_SIZE
        time.sleep(pause)
    return collected


def fetch_industry_peers(
    sector: str | None,
    industry: str | None,
    *,
    exclude: set[str],
    limit: int = DEFAULT_PEER_COUNT,
    pause: float = REQUEST_PAUSE_SECONDS,
    market_cap: str | None = None,
) -> list[str]:
    if not sector or not industry or limit <= 0:
        return []
    sector_key, industry_key = key_from_label("sector", sector), key_from_label("industry", industry)
    if not sector_key or not industry_key:
        logger.warning("Sin mapping de catálogo para peers sector=%r industry=%r", sector, industry)
        return []
    screened = discover_tickers(
        build_screener_specs(
            sectors=[sector_key],
            industries=[industry_key],
            themes=[],
            subthemes=[],
            market_cap=market_cap,
        )[0],
        limit + len(exclude) + 5,
        pause,
        order=PEER_SORT_ORDER,
    )
    blocked = {ticker.upper() for ticker in exclude} | set(_known_benchmarks())
    peers: list[str] = []
    for ticker in screened:
        if ticker not in blocked:
            peers.append(ticker)
        if len(peers) >= limit:
            break
    return peers


def collect_new_tickers(
    *,
    sectors: Sequence[str],
    industries: Sequence[str],
    themes: Sequence[str],
    subthemes: Sequence[str],
    market_cap: str | None,
    limit: int,
    pause: float,
    known: set[str],
) -> tuple[list[str], dict[str, TickerDiscoveryMeta]]:
    collected, meta_by_ticker = [], {}
    blocked = set(known) | set(_known_benchmarks())
    for spec in build_screener_specs(
        sectors=sectors,
        industries=industries,
        themes=themes,
        subthemes=subthemes,
        market_cap=market_cap,
    ):
        screened = discover_tickers(spec, limit, pause)
        fresh = [ticker for ticker in screened if ticker not in blocked]
        logger.info("Screener %s: %s nombres, %s nuevos", spec.label, len(screened), len(fresh))
        for ticker in fresh:
            blocked.add(ticker)
            collected.append(ticker)
            meta_by_ticker[ticker] = TickerDiscoveryMeta(spec.theme, spec.subtheme, spec.market_cap)
    return collected, meta_by_ticker


def collect_peers_for_documents(
    documents: Sequence[dict],
    *,
    peer_count: int = DEFAULT_PEER_COUNT,
    pause: float = REQUEST_PAUSE_SECONDS,
) -> list[str]:
    peers, seen = [], set()
    subjects = {str(doc.get("ticker", "")).upper() for doc in documents}
    for document in documents:
        ticker = str(document.get("ticker", "")).upper()
        if not ticker:
            continue
        found = fetch_industry_peers(
            document.get("sector"),
            document.get("industry"),
            exclude=subjects,
            limit=peer_count,
            pause=pause,
        )
        logger.info("Peers %s: %s", ticker, ", ".join(found) if found else "(ninguno)")
        for peer in found:
            if peer not in seen:
                seen.add(peer)
                peers.append(peer)
    return peers


@tool(
    "discover",
    "Screen Finviz for tickers, list catalog keys, or collect industry peers",
    {
        "type": "object",
        "properties": {
            "list": {"type": "string"},
            "sectors": {"type": "array", "items": {"type": "string"}},
            "industries": {"type": "array", "items": {"type": "string"}},
            "themes": {"type": "array", "items": {"type": "string"}},
            "subthemes": {"type": "array", "items": {"type": "string"}},
            "market_cap": {"type": "string"},
            "limit": {"type": "integer", "default": DEFAULT_LIMIT},
            "known": {"type": "array", "items": {"type": "string"}},
            "pause": {"type": "number", "default": REQUEST_PAUSE_SECONDS},
            "peer_documents": {"type": "array"},
            "peer_count": {"type": "integer", "default": DEFAULT_PEER_COUNT},
        },
    },
)
def discover_tool(inputs: dict) -> dict:
    try:
        if "list" in inputs:
            return {"ok": True, "data": {"listing": format_catalog_list(inputs.get("list") or None)}}
        pause = float(inputs.get("pause") or REQUEST_PAUSE_SECONDS)
        if inputs.get("peer_documents"):
            peers = collect_peers_for_documents(
                inputs["peer_documents"],
                peer_count=int(inputs.get("peer_count") or DEFAULT_PEER_COUNT),
                pause=pause,
            )
            return {"ok": True, "data": {"tickers": peers}}
        tickers, meta = collect_new_tickers(
            sectors=inputs.get("sectors") or [],
            industries=inputs.get("industries") or [],
            themes=inputs.get("themes") or [],
            subthemes=inputs.get("subthemes") or [],
            market_cap=inputs.get("market_cap"),
            limit=int(inputs.get("limit") or DEFAULT_LIMIT),
            pause=pause,
            known=set(inputs.get("known") or []),
        )
        return {
            "ok": True,
            "data": {
                "tickers": tickers,
                "meta": {key: item.__dict__ for key, item in meta.items()},
                "market_cap": inputs.get("market_cap") or default_market_cap(),
            },
        }
    except Exception as err:  # noqa: BLE001 — boundary de tool
        return {"ok": False, "error": str(err)}
