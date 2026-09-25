"""Extractors: sources + gateway (cascada → ExtractResult)."""

from __future__ import annotations

from utils.extractors.base import Source, merge_fields
from utils.extractors.finviz import FinvizSource
from utils.extractors.gateway import DEFAULT_CHAIN, ExtractResult, KpiGateway
from utils.extractors.stooq import StooqSource
from utils.extractors.yfinance import YFinanceSource

__all__ = [
    "DEFAULT_CHAIN",
    "ExtractResult",
    "FinvizSource",
    "KpiGateway",
    "Source",
    "StooqSource",
    "YFinanceSource",
    "get_extractor",
    "merge_fields",
]


def get_extractor(name: str = "auto") -> KpiGateway:
    """Compat: 'auto' = cascada completa; otro nombre = una sola source."""
    if name in {"auto", ""}:
        return KpiGateway()
    mapping: dict[str, type[Source]] = {
        FinvizSource.name: FinvizSource,
        StooqSource.name: StooqSource,
        YFinanceSource.name: YFinanceSource,
    }
    cls = mapping.get(name)
    if cls is None:
        raise ValueError(f"Source desconocida: {name}. Opciones: auto, {', '.join(sorted(mapping))}")
    return KpiGateway(sources=[cls()])
