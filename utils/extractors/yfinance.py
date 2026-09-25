"""YFinanceSource — info + history → campos KPI."""

from __future__ import annotations

import json
import logging
from typing import Any

import yfinance as yf
from curl_cffi import requests as cffi_requests
from curl_cffi.requests.exceptions import RequestException as CurlRequestException
from yfinance.exceptions import YFException

from utils.extractors.base import Source
from utils.helpers import technicals_from_ohlc
from utils.models import values_from_source

logger = logging.getLogger(__name__)
logging.getLogger("yfinance").setLevel(logging.CRITICAL)

_ERRORS = (
    YFException,
    CurlRequestException,
    KeyError,
    ValueError,
    OSError,
    RuntimeError,
    TypeError,
    json.JSONDecodeError,
)


class YFinanceSource(Source):
    name = "yfinance"

    def pull(self, ticker: str) -> dict[str, Any] | None:
        session = cffi_requests.Session(impersonate="chrome")
        yf_ticker = yf.Ticker(ticker.upper(), session=session)
        try:
            info = yf_ticker.info or {}
        except _ERRORS as err:
            logger.warning("yfinance info %s: %s", ticker, err)
            info = {}
        history = None
        try:
            history = yf_ticker.history(period="max", auto_adjust=False)
        except _ERRORS as err:
            logger.warning("yfinance history %s: %s", ticker, err)

        fields: dict[str, Any] = dict(values_from_source(info, "yfinance"))
        name = info.get("longName") or info.get("shortName")
        sector = info.get("sector")
        if name:
            fields.setdefault("name", str(name).strip())
        if sector:
            fields.setdefault("sector", str(sector).strip())

        if history is not None and not getattr(history, "empty", True):
            closes = [float(v) for v in history["Close"].dropna().tolist()]
            highs = [float(v) for v in history["High"].dropna().tolist()]
            lows = [float(v) for v in history["Low"].dropna().tolist()]
            tech = technicals_from_ohlc(highs, lows, closes)
            for key, value in tech.items():
                if value is not None:
                    fields.setdefault(key, value)
            if closes and fields.get("current_price") is None:
                fields["current_price"] = closes[-1]

        return fields or None
