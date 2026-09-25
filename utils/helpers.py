"""Helpers comunes: parseo, HTTP, técnicos, archivos y paths."""

from __future__ import annotations

import csv
import json
import re
import statistics
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

from utils.config import cfg
from utils.models import ScoreStatus, Tier

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "outputs"
DOCS_DIR = PROJECT_ROOT / "docs"
WATCHLIST_PATH = DOCS_DIR / "watchlist.csv"
PORTFOLIO_PATH = DOCS_DIR / "portfolio.txt"
CATALOG_PATH = DOCS_DIR / "catalog.yml"
CONFIG_PATH = DOCS_DIR / "config.yml"

RSI_PERIOD = int(cfg("technicals", "rsi_period", default=14))
TRADING_DAYS_52W = int(cfg("technicals", "trading_days_52w", default=252))

_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def parse_numeric(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        numeric = float(value)
        return None if numeric != numeric else numeric
    text = str(value).strip()
    if not text or text in {"-", "N/A", "None", "nan"}:
        return None
    match = re.search(r"-?\d[\d,]*\.?\d*", text.replace(",", ""))
    if not match:
        return None
    try:
        return float(match.group())
    except ValueError:
        return None


def normalize_ratio_as_percent(value: float | None) -> float | None:
    if value is None:
        return None
    if abs(value) <= 1.0:
        return round(value * 100.0, 4)
    return round(value, 4)


def lookup_ci(data: dict[str, Any], key: str | tuple[str, ...]) -> Any:
    for label in key if isinstance(key, tuple) else (key,):
        if label in data:
            return data[label]
        needle = label.lower()
        for candidate, value in data.items():
            if str(candidate).lower() == needle:
                return value
    return None


def strip_html(raw_html: str) -> str:
    return re.sub(r"<[^>]+>", "", raw_html).strip()


def fetch_url(
    url: str,
    *,
    timeout: int = 20,
    headers: dict[str, str] | None = None,
    accept: str | None = None,
) -> str:
    """GET de texto. Único helper HTTP para callers que no usan un cliente propio."""
    merged = {"User-Agent": _USER_AGENT, **(headers or {})}
    if accept:
        merged["Accept"] = accept
    with urlopen(Request(url, headers=merged), timeout=timeout) as response:
        return response.read().decode("utf-8", errors="replace")


def compute_sma(closes: Sequence[float], period: int) -> float | None:
    if len(closes) < period:
        return None
    window = closes[-period:]
    return round(sum(window) / period, 4)


def compute_rsi(closes: Sequence[float], period: int = RSI_PERIOD) -> float | None:
    if len(closes) < period + 1:
        return None
    deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    gains = [d if d > 0 else 0.0 for d in deltas]
    losses = [-d if d < 0 else 0.0 for d in deltas]
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for index in range(period, len(gains)):
        avg_gain = ((avg_gain * (period - 1)) + gains[index]) / period
        avg_loss = ((avg_loss * (period - 1)) + losses[index]) / period
    if avg_loss == 0:
        return 100.0
    return round(100.0 - (100.0 / (1.0 + avg_gain / avg_loss)), 4)


def technicals_from_ohlc(
    highs: Sequence[float], lows: Sequence[float], closes: Sequence[float]
) -> dict[str, float | None]:
    empty = {key: None for key in ("ath", "high_52w", "low_52w", "sma_25", "sma_50", "sma_200", "rsi")}
    if not closes:
        return empty
    window = min(len(closes), TRADING_DAYS_52W)
    recent_highs = highs[-window:] if highs else []
    recent_lows = lows[-window:] if lows else []
    return {
        "ath": round(max(highs), 4) if highs else None,
        "high_52w": round(max(recent_highs), 4) if recent_highs else None,
        "low_52w": round(min(recent_lows), 4) if recent_lows else None,
        "sma_25": compute_sma(closes, 25),
        "sma_50": compute_sma(closes, 50),
        "sma_200": compute_sma(closes, 200),
        "rsi": compute_rsi(closes),
    }


def sma_from_distance_pct(price: float | None, distance_pct: float | None) -> float | None:
    if price is None or distance_pct is None:
        return None
    return round(price / (1 + distance_pct / 100), 4)


def normalize_ticker_list(tickers: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    normalized: list[str] = []
    for ticker in tickers:
        symbol = ticker.upper().strip()
        if not symbol or symbol in seen:
            continue
        seen.add(symbol)
        normalized.append(symbol)
    return normalized


def ticker_from_raw(raw: str) -> str | None:
    symbol = raw.split("#", 1)[0].strip()
    if not symbol:
        return None
    if ":" in symbol:
        symbol = symbol.rsplit(":", 1)[-1].strip()
    return symbol.upper() or None


def iter_tickers_from_file(path: Path) -> list[str]:
    if not path.is_file():
        raise ValueError(f"No existe el archivo de tickers: {path}")
    raw_tickers: list[str] = []
    if path.suffix.lower() == ".csv":
        with path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            if not reader.fieldnames:
                return []
            field_map = {name.lower().strip(): name for name in reader.fieldnames}
            ticker_key = field_map.get("ticker")
            if ticker_key is None:
                raise ValueError(f"El CSV debe tener columna 'ticker': {path}")
            for row in reader:
                symbol = ticker_from_raw(str(row.get(ticker_key) or ""))
                if symbol:
                    raw_tickers.append(symbol)
    else:
        for line in path.read_text(encoding="utf-8").splitlines():
            symbol = ticker_from_raw(line)
            if symbol:
                raw_tickers.append(symbol)
    return normalize_ticker_list(raw_tickers)


def load_tickers_from_file(path: Path) -> list[str]:
    tickers = iter_tickers_from_file(path)
    if not tickers:
        raise ValueError(f"El archivo de tickers está vacío: {path}")
    return tickers


def load_known_symbols(path: Path) -> set[str]:
    if not path.is_file():
        return set()
    try:
        return set(iter_tickers_from_file(path))
    except ValueError:
        return set()


def resolve_path(path: str | Path) -> Path:
    file_path = Path(path)
    return file_path if file_path.is_absolute() else PROJECT_ROOT / file_path


def make_run_stamp(now: datetime | None = None) -> str:
    moment = now or datetime.now()
    return moment.strftime("%Y%m%d%H%M") + f"{moment.microsecond // 1000:03d}"


def make_run_dir(base: Path | None = None, now: datetime | None = None) -> Path:
    run_dir = (base or DEFAULT_OUTPUT_DIR) / f"run_{make_run_stamp(now)}"
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def resolve_run_dir(run: str | Path | None = None) -> Path:
    """Reusa la carpeta indicada; si no hay `--run`, crea `outputs/run_*`."""
    if run is None or not str(run).strip():
        return make_run_dir()
    path = resolve_path(run)
    if path.suffix.lower() in {".json", ".csv", ".txt"}:
        path = path.parent
    if path.resolve() in {DEFAULT_OUTPUT_DIR.resolve(), PROJECT_ROOT.resolve()}:
        return make_run_dir()
    path.mkdir(parents=True, exist_ok=True)
    return path


def list_run_dirs(base: Path | None = None) -> list[Path]:
    root = base or DEFAULT_OUTPUT_DIR
    if not root.is_dir():
        return []
    return sorted(
        (path for path in root.glob("run_*") if path.is_dir()),
        key=lambda path: path.name,
        reverse=True,
    )


def latest_kpi_document_path(base: Path | None = None) -> Path | None:
    for run_dir in list_run_dirs(base):
        candidate = run_dir / "kpis.json"
        if candidate.is_file():
            return candidate
    legacy = (base or DEFAULT_OUTPUT_DIR) / "kpis.json"
    return legacy if legacy.is_file() else None


def dump_json(payload: Any, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def ticker_cache_path(cache_dir: Path, ticker: str) -> Path:
    return cache_dir / f"{ticker.upper()}.json"


def load_ticker_cache(cache_dir: Path | None, ticker: str) -> dict[str, Any] | None:
    if cache_dir is None:
        return None
    path = ticker_cache_path(cache_dir, ticker)
    if not path.is_file():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else None


def save_ticker_cache(cache_dir: Path | None, ticker: str, document: dict[str, Any]) -> None:
    if cache_dir is None:
        return
    dump_json(document, ticker_cache_path(cache_dir, ticker))


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def write_csv_rows(path: Path, columns: Sequence[str], rows: Sequence[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(columns))
        writer.writeheader()
        for row in rows:
            writer.writerow({col: row.get(col, "") for col in columns})


def append_csv_rows(path: Path, columns: Sequence[str], rows: Sequence[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    existing: list[dict[str, str]] = []
    if path.is_file() and path.stat().st_size > 0:
        with path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                existing.append({col: row.get(col, "") or "" for col in columns})
    write_csv_rows(path, columns, [*existing, *rows])


# --- Scoring / finance helpers (normalizations, formats, inferences) ---

RISK_FREE_RATE = float(cfg("finance", "risk_free_rate", default=0.045))
EQUITY_RISK_PREMIUM = float(cfg("finance", "equity_risk_premium", default=0.055))


def estimate_wacc(beta: float | None) -> float:
    beta_value = beta if beta is not None and beta > 0 else 1.0
    return RISK_FREE_RATE + beta_value * EQUITY_RISK_PREMIUM


def normalize_ratio(value: float | None) -> float | None:
    if value is None:
        return None
    if abs(value) > 1.5:
        return value / 100.0
    return value


def positive(value: float | None) -> bool:
    return value is not None and value > 0


def compute_upside(current_price: float | None, target_price: float | None) -> float:
    if current_price is None or target_price is None or current_price <= 0:
        return 0.0
    return (target_price - current_price) / current_price


def resolve_upside_52w(
    current_price: float | None,
    high_52w: float | None,
    sma_25: float | None,
) -> float:
    upside_52w = compute_upside(current_price, high_52w)
    if upside_52w == 0.0:
        return compute_upside(current_price, sma_25)
    return upside_52w


def median_positive(values: list[float]) -> float | None:
    positives = [value for value in values if value is not None and value > 0]
    if not positives:
        return None
    return statistics.median(positives)


def median_numeric(values: list[float]) -> float | None:
    usable = [value for value in values if value is not None and value == value]
    if not usable:
        return None
    return statistics.median(usable)


def format_completeness(status: ScoreStatus) -> str:
    if status == "complete":
        return " "
    if status == "partial":
        return "p"
    return "m"


def format_alpha(value: float | None) -> str:
    if value is None:
        return "N/A"
    sign = "+" if value > 0 else ""
    return f"{sign}{value:.1f}%"


def is_etf(ticker: str, name: str | None, sector: str | None) -> bool:
    markers = [str(m).upper() for m in (cfg("classification", "etf", "name_markers") or [])]
    tickers = {str(t).upper() for t in (cfg("classification", "etf", "tickers") or [])}
    sector_keywords = [str(k).lower() for k in (cfg("classification", "etf", "sector_keywords") or [])]
    upper_name = (name or "").upper()
    if any(marker in upper_name for marker in markers):
        return True
    if ticker.upper() in tickers:
        return True
    sector_l = (sector or "").lower()
    return any(keyword in sector_l for keyword in sector_keywords)


def infer_category(ticker: str, name: str | None, sector: str | None) -> str:
    prefixes = [str(p).upper() for p in (cfg("classification", "crypto", "name_prefixes") or [])]
    markers = [str(m).upper() for m in (cfg("classification", "crypto", "name_markers") or [])]
    sectors = {str(s).lower() for s in (cfg("classification", "crypto", "sectors") or [])}
    tickers = {str(t).upper() for t in (cfg("classification", "crypto", "tickers") or [])}
    upper_name = (name or "").upper()
    if any(upper_name.startswith(prefix) for prefix in prefixes):
        return "Crypto"
    if any(marker in upper_name for marker in markers):
        return "Crypto"
    if (sector or "").lower() in sectors:
        return "Crypto"
    if ticker.upper() in tickers:
        return "Crypto"
    return ""


def infer_tier(eps: float | None, pe: float | None, fwd_pe: float | None) -> Tier:
    if eps is not None and eps > 0 and positive(pe or fwd_pe):
        return "core"
    return "speculative"


def is_financial_sector(sector: str | None) -> bool:
    labels = {str(s).lower() for s in (cfg("classification", "financial_sectors") or ["financial"])}
    return (sector or "").strip().lower() in labels
