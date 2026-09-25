"""Dataclasses y catálogo de métricas (nombres en inglés en extract)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import asdict, dataclass, field, fields
from typing import Any, Literal

FilterKind = Literal["sector", "industry", "theme", "subtheme", "market_cap"]
ScoreStatus = Literal["complete", "partial", "minimal"]
Tier = Literal["core", "speculative"]
ValuationMode = Literal["earnings", "growth"]
RelativeStrength = Literal["LEADING", "STRONG", "NEUTRAL", "LAGGING", "WEAK", "N/A"]


def _market_benchmark() -> str:
    from utils.config import cfg

    return str(cfg("market", "benchmark", default="SPY"))


MARKET_BENCHMARK = _market_benchmark()
META_FIELDS = ("ticker", "name", "sector", "industry", "market_cap")
# Campos suficientes para alpha vs SPY/ETF y medianas sectoriales (mode=comparison).
COMPARISON_FIELDS = (
    "pe",
    "fwd_pe",
    "p_fcf",
    "ps",
    "ev_ebitda",
    "oper_margin",
    "perf_month",
    "perf_quarter",
    "perf_half_y",
    "perf_ytd",
    "perf_year",
    "perf_3y",
    "perf_5y",
)

WATCHLIST_COLUMNS = (
    "ticker",
    "name",
    "sector",
    "industry",
    "theme",
    "subtheme",
    "marketcap",
    "price",
    "date",
    "kind",
    "score",
    "valuation",
    "growth",
    "quality",
    "balance",
    "momentum",
    "relative_strength",
    "notes",
)


@dataclass(frozen=True)
class MetricSpec:
    """Mapeo de un KPI a fuentes y etiqueta de impresión."""

    key: str
    finviz: str | tuple[str, ...] | None = None
    yfinance: str | None = None
    yf_as_percent: bool = False
    label: str = ""
    as_percent: bool = False

    def source_key(self, source: str) -> str | tuple[str, ...] | None:
        if source == "finviz":
            return self.finviz
        if source == "yfinance":
            return self.yfinance
        return None

    def print_label(self) -> str:
        return self.label or self.key


METRICS: tuple[MetricSpec, ...] = (
    MetricSpec("current_price", "Price", "currentPrice", label="Price"),
    MetricSpec("ath", label="ATH"),
    MetricSpec("high_52w", yfinance="fiftyTwoWeekHigh", label="52w High"),
    MetricSpec("low_52w", yfinance="fiftyTwoWeekLow", label="52w Low"),
    MetricSpec("sma_25", label="SM25"),
    MetricSpec("sma_50", label="SM50"),
    MetricSpec("sma_200", label="SM200"),
    MetricSpec("rsi", "RSI (14)", label="RSI"),
    MetricSpec("pe", "P/E", "trailingPE", label="PE"),
    MetricSpec("fwd_pe", "Forward P/E", "forwardPE", label="Fwd PE"),
    MetricSpec("peg", "PEG", "pegRatio", label="PEG"),
    MetricSpec("roe", "ROE", "returnOnEquity", True, "ROE", True),
    MetricSpec("debt_to_equity", "Debt/Eq", "debtToEquity", label="Debt/Equity"),
    MetricSpec("eps", ("EPS (ttm)",), "trailingEps", label="EPS"),
    MetricSpec("payout", "Payout", "payoutRatio", True, "Payout", True),
    MetricSpec("beta", "Beta", "beta", label="Beta"),
    MetricSpec("eps_growth", "EPS this Y", "earningsGrowth", True, "EPS Growth", True),
    MetricSpec("ps", "P/S", "priceToSalesTrailing12Months", label="P/S"),
    MetricSpec("sales_growth", "Sales Y/Y TTM", "revenueGrowth", True, "Sales Growth", True),
    MetricSpec("sales_cagr_3y", label="Sales CAGR 3Y", as_percent=True),
    MetricSpec("eps_next_y", label="EPS Next Y", as_percent=True),
    MetricSpec("p_fcf", "P/FCF", "priceToFreeCashFlows", label="P/FCF"),
    MetricSpec("ev_ebitda", "EV/EBITDA", "enterpriseToEbitda", label="EV/EBITDA"),
    MetricSpec("roic", "ROIC", label="ROIC", as_percent=True),
    MetricSpec("gross_margin", "Gross Margin", label="Gross Margin", as_percent=True),
    MetricSpec("oper_margin", "Oper. Margin", "operatingMargins", True, "Oper Margin", True),
    MetricSpec("profit_margin", "Profit Margin", "profitMargins", True, "Profit Margin", True),
    MetricSpec("eps_cagr_3y", label="EPS CAGR 3Y", as_percent=True),
    MetricSpec("eps_cagr_5y", label="EPS CAGR 5Y", as_percent=True),
    MetricSpec("eps_yoy", "EPS Y/Y TTM", label="EPS Y/Y", as_percent=True),
    MetricSpec("fcf_yield", label="FCF Yield", as_percent=True),
    MetricSpec("fcf_to_ni", label="FCF/NI"),
    MetricSpec("lt_debt_to_equity", "LT Debt/Eq", label="LT Debt/Eq"),
    MetricSpec("current_ratio", "Current Ratio", "currentRatio", label="Current Ratio"),
    MetricSpec("quick_ratio", "Quick Ratio", "quickRatio", label="Quick Ratio"),
    MetricSpec("cash_per_share", "Cash/sh", label="Cash/sh"),
    MetricSpec("perf_month", "Perf Month", label="Perf 1M", as_percent=True),
    MetricSpec("perf_quarter", "Perf Quarter", label="Perf 3M", as_percent=True),
    MetricSpec("perf_half_y", "Perf Half Y", label="Perf 6M", as_percent=True),
    MetricSpec("perf_ytd", "Perf YTD", label="Perf YTD", as_percent=True),
    MetricSpec("perf_year", "Perf Year", label="Perf 1Y", as_percent=True),
    MetricSpec("perf_3y", "Perf 3Y", label="Perf 3Y", as_percent=True),
    MetricSpec("perf_5y", "Perf 5Y", label="Perf 5Y", as_percent=True),
)

METRIC_BY_KEY = {spec.key: spec for spec in METRICS}


class MetricGroups:
    """Bloques de métricas usados en scoring y completeness."""

    valuation = ("pe", "fwd_pe", "peg", "p_fcf", "ev_ebitda", "ps")
    growth = ("sales_growth", "eps_growth", "sales_cagr_3y", "eps_cagr_3y", "eps_yoy")
    quality = (
        "roe",
        "roic",
        "gross_margin",
        "oper_margin",
        "profit_margin",
        "fcf_to_ni",
        "fcf_yield",
    )
    balance = ("debt_to_equity", "lt_debt_to_equity", "ev_ebitda", "payout", "current_ratio")
    momentum = ("rsi", "upside_52w", "beta", "alpha_year_etf", "alpha_year_spy")

    @classmethod
    def tracked(cls) -> tuple[str, ...]:
        return (*cls.valuation, *cls.growth, *cls.quality, *cls.balance, *cls.momentum)


@dataclass
class TickerKpis:
    ticker: str
    name: str | None = None
    sector: str | None = None
    industry: str | None = None
    market_cap: str | None = None
    current_price: float | None = None
    ath: float | None = None
    high_52w: float | None = None
    low_52w: float | None = None
    sma_25: float | None = None
    sma_50: float | None = None
    sma_200: float | None = None
    rsi: float | None = None
    pe: float | None = None
    fwd_pe: float | None = None
    peg: float | None = None
    roe: float | None = None
    debt_to_equity: float | None = None
    eps: float | None = None
    eps_growth: float | None = None
    ps: float | None = None
    sales_growth: float | None = None
    sales_cagr_3y: float | None = None
    eps_next_y: float | None = None
    p_fcf: float | None = None
    ev_ebitda: float | None = None
    roic: float | None = None
    gross_margin: float | None = None
    oper_margin: float | None = None
    profit_margin: float | None = None
    eps_cagr_3y: float | None = None
    eps_cagr_5y: float | None = None
    eps_yoy: float | None = None
    fcf_yield: float | None = None
    fcf_to_ni: float | None = None
    lt_debt_to_equity: float | None = None
    current_ratio: float | None = None
    quick_ratio: float | None = None
    cash_per_share: float | None = None
    perf_month: float | None = None
    perf_quarter: float | None = None
    perf_half_y: float | None = None
    perf_ytd: float | None = None
    perf_year: float | None = None
    perf_3y: float | None = None
    perf_5y: float | None = None
    payout: float | None = None
    beta: float | None = None

    @classmethod
    def from_mapping(cls, ticker: str, values: dict[str, Any]) -> TickerKpis:
        allowed = {f.name for f in fields(cls)} - {"ticker"}
        return cls(ticker=ticker, **{key: val for key, val in values.items() if key in allowed})

    def merge(self, patch: TickerKpis) -> TickerKpis:
        data = asdict(self)
        for f in fields(self):
            if f.name != "ticker" and data[f.name] is None:
                data[f.name] = getattr(patch, f.name)
        return TickerKpis(**data)

    def attributes(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in KPI_FIELDS}

    def populated_count(self) -> int:
        return sum(1 for name in KPI_FIELDS if getattr(self, name) is not None)

    @classmethod
    def from_document(cls, document: dict[str, Any]) -> TickerKpis:
        """Ignora claves desconocidas del documento (p.ej. sources, fetched_at)."""
        attrs = document.get("attributes") or {}
        values = {key: document.get(key) for key in META_FIELDS[1:]}
        values.update({name: attrs.get(name) for name in KPI_FIELDS if name in attrs})
        return cls.from_mapping(str(document.get("ticker", "")).upper(), values)


@dataclass
class MarketDocument:
    ticker: str
    fetched_at: str
    attributes: dict[str, Any]
    name: str | None = None
    sector: str | None = None
    industry: str | None = None
    market_cap: str | None = None
    sources: list[str] = field(default_factory=list)  # provenance: e.g. ["finviz","stooq"]

    def to_dict(self) -> dict[str, Any]:
        document: dict[str, Any] = {
            "ticker": self.ticker,
            "fetched_at": self.fetched_at,
            "attributes": dict(self.attributes),
            "sources": list(self.sources),
        }
        for key in META_FIELDS[1:]:
            value = getattr(self, key)
            if value:
                document[key] = value
        return document

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MarketDocument:
        return cls(
            ticker=str(data.get("ticker", "")).upper(),
            fetched_at=str(data.get("fetched_at") or ""),
            attributes=dict(data.get("attributes") or {}),
            name=data.get("name"),
            sector=data.get("sector"),
            industry=data.get("industry"),
            market_cap=data.get("market_cap"),
            sources=[str(item) for item in (data.get("sources") or [])],
        )

    @classmethod
    def from_kpis(
        cls,
        kpis: TickerKpis,
        *,
        fetched_at: str,
        sources: Sequence[str],
        mode: str = "analysis",
    ) -> MarketDocument:
        if mode == "comparison":
            attrs = kpis.attributes()
            attributes = {key: attrs[key] for key in COMPARISON_FIELDS if attrs.get(key) is not None}
        else:
            attributes = kpis.attributes()
        return cls(
            ticker=kpis.ticker,
            fetched_at=fetched_at,
            attributes=attributes,
            name=kpis.name,
            sector=kpis.sector,
            industry=kpis.industry,
            market_cap=kpis.market_cap,
            sources=list(sources),
        )


KPI_FIELDS = tuple(f.name for f in fields(TickerKpis) if f.name not in META_FIELDS)
TECHNICAL_FIELDS = ("ath", "sma_25", "sma_50", "sma_200", "rsi", "high_52w", "low_52w")


@dataclass
class MetricScore:
    name: str
    points: int
    max_points: int
    available: bool


@dataclass
class BlockScore:
    points: int
    max_points: int
    metrics: list[MetricScore]


@dataclass
class SectorMedians:
    pe: float | None = None
    fwd_pe: float | None = None
    p_fcf: float | None = None
    ev_ebitda: float | None = None
    ps: float | None = None
    oper_margin: float | None = None


@dataclass
class RelativeComparison:
    ticker: str
    sector_etf: str | None
    perf_year: float | None
    perf_ytd: float | None
    alpha_year_vs_etf: float | None
    alpha_ytd_vs_etf: float | None
    alpha_year_vs_spy: float | None
    alpha_ytd_vs_spy: float | None
    relative_strength: RelativeStrength


@dataclass
class ScoreInputs:
    ticker: str
    category: str
    tier: Tier
    sector: str | None
    current_price: float
    upside_52w: float
    rsi: float
    pe: float | None
    fwd_pe: float | None
    peg: float | None
    roe: float | None
    roic: float | None
    gross_margin: float | None
    oper_margin: float | None
    profit_margin: float | None
    debt_eq: float | None
    lt_debt_eq: float | None
    eps_growth: float | None
    eps_yoy: float | None
    eps_cagr_3y: float | None
    payout: float | None
    beta: float | None
    ps: float | None
    p_fcf: float | None
    ev_ebitda: float | None
    fcf_yield: float | None
    fcf_to_ni: float | None
    sales_growth: float | None
    sales_cagr_3y: float | None
    eps_next_y: float | None
    current_ratio: float | None
    cash_per_share: float | None
    alpha_year_etf: float | None = None
    alpha_year_spy: float | None = None
    pe_vs_sector: float | None = None
    p_fcf_vs_sector: float | None = None
    ps_vs_sector: float | None = None
    ev_ebitda_vs_sector: float | None = None
    oper_margin_vs_sector: float | None = None
    attributes: dict[str, Any] | None = None


@dataclass
class ScoreResult:
    ticker: str
    name: str | None
    sector: str | None
    category: str
    tier: Tier
    valuation_mode: ValuationMode
    score: int
    bloque_1: int
    bloque_2: int
    bloque_3: int
    bloque_4: int
    bloque_5: int
    completeness_pct: float
    score_status: ScoreStatus
    metrics_available: int
    metrics_total: int
    benchmark_etf: str | None = None
    alpha_year_vs_etf: float | None = None
    alpha_year_vs_spy: float | None = None
    alpha_ytd_vs_etf: float | None = None
    relative_strength: str = "N/A"
    wacc_estimate: float | None = None
    roic_spread: float | None = None
    earnings_cash_flag: bool = False
    cycle_peak: bool = False


@dataclass
class ScoreBatch:
    core: list[ScoreResult]
    speculative: list[ScoreResult]
    comparisons: dict[str, RelativeComparison]
    skipped_etfs: list[str]
    confirmed: list[ScoreResult]
    dislocated: list[ScoreResult]
    skipped_minimal: list[str]


@dataclass(frozen=True)
class ScreenerSpec:
    label: str
    filters: str
    theme: str
    subtheme: str
    market_cap: str


@dataclass
class TickerDiscoveryMeta:
    theme: str = ""
    subtheme: str = ""
    market_cap: str = ""


def values_from_source(data: dict[str, Any], source: str) -> dict[str, float]:
    """Aplica el catálogo METRICS sobre un dict crudo de la fuente."""
    from utils.helpers import lookup_ci, normalize_ratio_as_percent, parse_numeric

    values: dict[str, float] = {}
    for spec in METRICS:
        raw_key = spec.source_key(source)
        if not raw_key:
            continue
        numeric = parse_numeric(lookup_ci(data, raw_key))
        if numeric is None:
            continue
        if source == "yfinance" and spec.yf_as_percent:
            numeric = normalize_ratio_as_percent(numeric)
            if numeric is None:
                continue
        values[spec.key] = numeric
    return values
