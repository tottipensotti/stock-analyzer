"""StooqSource — CSV OHLC → técnicos (ath, SMA, RSI)."""

from __future__ import annotations

import logging
from typing import Any

from utils.extractors.base import Source
from utils.helpers import fetch_url, technicals_from_ohlc

logger = logging.getLogger(__name__)

_URLS = (
    "https://stooq.com/q/d/l/?s={symbol}.us&i=d",
    "https://stooq.pl/q/d/l/?s={symbol}.us&i=d",
)


class StooqSource(Source):
    name = "stooq"

    def pull(self, ticker: str) -> dict[str, Any] | None:
        highs, lows, closes = self._ohlc(ticker)
        if not closes:
            return None
        fields = technicals_from_ohlc(highs, lows, closes)
        fields["current_price"] = round(closes[-1], 4)
        return {k: v for k, v in fields.items() if v is not None} or None

    def _ohlc(self, symbol: str) -> tuple[list[float], list[float], list[float]]:
        for template in _URLS:
            csv_text = self._download(template.format(symbol=symbol.lower()), symbol)
            if not csv_text:
                continue
            highs, lows, closes = self._parse_csv(csv_text)
            if closes:
                return highs, lows, closes
        logger.warning("Stooq sin CSV válido para %s", symbol)
        return [], [], []

    def _download(self, url: str, symbol: str) -> str | None:
        try:
            text = fetch_url(
                url,
                timeout=20,
                headers={"Referer": f"https://stooq.com/q/?s={symbol.lower()}.us"},
                accept="text/csv,text/plain,*/*",
            )
        except Exception as err:  # noqa: BLE001 — fallos de red → None, sigue cascada
            logger.debug("Stooq fetch %s: %s", symbol, err)
            return None
        return text if self._valid(text) else None

    @staticmethod
    def _valid(csv_text: str) -> bool:
        stripped = csv_text.lstrip()
        if not stripped or stripped.startswith("<"):
            return False
        first = stripped.split("\n", 1)[0].lower()
        return "date" in first or "symbol" in first

    @staticmethod
    def _parse_csv(csv_text: str) -> tuple[list[float], list[float], list[float]]:
        highs: list[float] = []
        lows: list[float] = []
        closes: list[float] = []
        for line in csv_text.strip().split("\n"):
            parts = line.split(",")
            if len(parts) < 6 or parts[0].lower() in {"date", "symbol"}:
                continue
            try:
                if len(parts) >= 8:
                    high, low, close = float(parts[4]), float(parts[5]), float(parts[6])
                else:
                    high, low, close = float(parts[2]), float(parts[3]), float(parts[4])
            except ValueError:
                continue
            highs.append(high)
            lows.append(low)
            closes.append(close)
        return highs, lows, closes
