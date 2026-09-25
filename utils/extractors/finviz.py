"""FinvizSource — HTML quote → dict de campos KPI."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from utils.extractors.base import Source
from utils.helpers import (
    fetch_url,
    lookup_ci,
    parse_numeric,
    sma_from_distance_pct,
    strip_html,
)
from utils.models import values_from_source

logger = logging.getLogger(__name__)


class FinvizSource(Source):
    name = "finviz"
    _url = "https://finviz.com/quote.ashx?t={ticker}"

    def pull(self, ticker: str) -> dict[str, Any] | None:
        try:
            html = fetch_url(self._url.format(ticker=ticker.upper()), timeout=15)
        except Exception as err:  # noqa: BLE001 — fallos de red → None, sigue cascada
            logger.warning("Finviz fetch %s: %s", ticker, err)
            return None

        snapshot = self._snapshot(html)
        if not snapshot:
            return None

        fields: dict[str, Any] = dict(values_from_source(snapshot, "finviz"))
        fields.update({k: v for k, v in self._meta(html, snapshot).items() if v})
        extras = self._extras(html, snapshot, fields.get("current_price"))
        fields.update({k: v for k, v in extras.items() if v is not None})
        return fields or None

    def _meta(self, html: str, snapshot: dict[str, str]) -> dict[str, Any]:
        name = sector = industry = None
        block = re.search(r"quote-header_ticker-wrapper_company[^>]*>(.*?)</h2>", html, re.IGNORECASE | re.DOTALL)
        if block:
            name = strip_html(block.group(1)) or None
        sec = re.search(r'href="[^"]*f=sec_[^"]*"[^>]*>\s*([^<]+)', html, re.IGNORECASE)
        if sec:
            sector = strip_html(sec.group(1))
        ind = re.search(r'href="[^"]*f=ind_[^"]*"[^>]*>(.*?)</a>', html, re.IGNORECASE | re.DOTALL)
        if ind:
            industry = strip_html(ind.group(1)) or None
        cap = lookup_ci(snapshot, "Market Cap")
        return {
            "name": name,
            "sector": sector,
            "industry": industry,
            "market_cap": str(cap).strip() if cap else None,
        }

    def _extras(self, html: str, snapshot: dict[str, str], price: float | None) -> dict[str, Any]:
        highs, _, _ = self._chart_ohlc(html)
        low_52, high_52 = self._range_52w(snapshot)
        sales = lookup_ci(snapshot, "Sales past 3/5Y")
        eps_past = lookup_ci(snapshot, "EPS past 3/5Y")
        return {
            "ath": round(max(highs), 4) if highs else None,
            "high_52w": high_52,
            "low_52w": low_52,
            "sma_25": sma_from_distance_pct(price, parse_numeric(lookup_ci(snapshot, "SMA20"))),
            "sma_50": sma_from_distance_pct(price, parse_numeric(lookup_ci(snapshot, "SMA50"))),
            "sma_200": sma_from_distance_pct(price, parse_numeric(lookup_ci(snapshot, "SMA200"))),
            "sales_cagr_3y": self._past(sales, 0),
            "eps_cagr_3y": self._past(eps_past, 0),
            "eps_cagr_5y": self._past(eps_past, 1),
            "eps_next_y": parse_numeric(lookup_ci(snapshot, "EPS next Y Percentage")),
            "payout": self._payout(snapshot, html),
        }

    def _snapshot(self, html: str) -> dict[str, str]:
        out: dict[str, str] = {}
        for table in re.findall(
            r'<table[^>]*class="[^"]*snapshot-table2[^"]*"[^>]*>(.*?)</table>', html, re.IGNORECASE | re.DOTALL
        ):
            for row in re.findall(r"<tr[^>]*>(.*?)</tr>", table, re.IGNORECASE | re.DOTALL):
                cells = [
                    strip_html(c).strip()
                    for c in re.findall(r"<td[^>]*>(.*?)</td>", row, re.IGNORECASE | re.DOTALL)
                    if strip_html(c).strip()
                ]
                for i in range(0, len(cells) - 1, 2):
                    label, value = cells[i], cells[i + 1]
                    if not label or not value or value == "-":
                        continue
                    if label == "EPS next Y" and label in out:
                        label = "EPS next Y Percentage"
                    out[label] = value
        for row in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.IGNORECASE | re.DOTALL):
            if "snapshot-td-label" not in row:
                continue
            labels = re.findall(r"snapshot-td-label[^>]*>([^<]+)<", row, re.IGNORECASE)
            contents = re.findall(r"snapshot-td-content[^>]*>(.*?)</div>", row, re.IGNORECASE | re.DOTALL)
            for label, raw in zip(labels, contents, strict=False):
                value = strip_html(raw)
                if label.strip() and value and value != "-":
                    out.setdefault(label.strip(), value)
        for field in ("Payout", "Dividend TTM", "EPS (ttm)"):
            if field not in out:
                value = self._label(html, field)
                if value and value != "-":
                    out[field] = value
        return out

    @staticmethod
    def _label(html: str, label: str) -> str | None:
        match = re.search(
            rf"snapshot-td-label[^>]*>\s*{re.escape(label)}\s*</div></td>.*?"
            r"snapshot-td-content[^>]*>(.*?)</div>",
            html,
            re.IGNORECASE | re.DOTALL,
        )
        return strip_html(match.group(1)) if match else None

    @staticmethod
    def _range_52w(snapshot: dict[str, str]) -> tuple[float | None, float | None]:
        raw = lookup_ci(snapshot, "52W Range")
        if not raw:
            return None, None
        parts = [p.strip() for p in re.split(r"\s*-\s*", str(raw)) if p.strip()]
        if len(parts) < 2:
            return None, None
        return parse_numeric(parts[0]), parse_numeric(parts[-1])

    @staticmethod
    def _past(value: str | None, index: int) -> float | None:
        if not value:
            return None
        parts = value.replace("%", "").split()
        if index >= len(parts) or parts[index] in {"-", ""}:
            return None
        return parse_numeric(parts[index])

    def _payout(self, snapshot: dict[str, str], html: str) -> float | None:
        payout = parse_numeric(lookup_ci(snapshot, "Payout"))
        if payout is not None:
            return payout
        dividend = parse_numeric(lookup_ci(snapshot, "Dividend TTM")) or parse_numeric(
            self._label(html, "Dividend TTM")
        )
        eps = parse_numeric(lookup_ci(snapshot, "EPS (ttm)")) or parse_numeric(self._label(html, "EPS (ttm)"))
        if dividend is not None and eps is not None and eps > 0:
            return round((dividend / eps) * 100, 4)
        return None

    @staticmethod
    def _chart_ohlc(html: str) -> tuple[list[float], list[float], list[float]]:
        start = html.find("var data = ")
        if start < 0:
            return [], [], []
        start += len("var data = ")
        if start >= len(html) or html[start] != "{":
            return [], [], []
        depth = 0
        for index in range(start, len(html)):
            char = html[index]
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    try:
                        payload = json.loads(html[start : index + 1])
                    except json.JSONDecodeError:
                        return [], [], []
                    return (
                        [float(v) for v in payload.get("high", []) if v is not None],
                        [float(v) for v in payload.get("low", []) if v is not None],
                        [float(v) for v in payload.get("close", []) if v is not None],
                    )
        return [], [], []
