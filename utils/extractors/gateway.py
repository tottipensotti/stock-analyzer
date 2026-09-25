"""KpiGateway — cascada Finviz → Stooq → yfinance → ExtractResult."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass

from utils.extractors.base import Source, merge_fields
from utils.extractors.finviz import FinvizSource
from utils.extractors.stooq import StooqSource
from utils.extractors.yfinance import YFinanceSource
from utils.models import KPI_FIELDS, TickerKpis

logger = logging.getLogger(__name__)

DEFAULT_CHAIN: tuple[type[Source], ...] = (FinvizSource, StooqSource, YFinanceSource)


@dataclass(frozen=True)
class ExtractResult:
    kpis: TickerKpis
    sources: tuple[str, ...]


class KpiGateway:
    """
    Dispatcher: prueba sources en orden de prioridad.
    Cada source aporta un dict de campos; se mergean rellenando huecos.
    Al final un solo parseo a TickerKpis + provenance.
    """

    def __init__(self, sources: Sequence[Source] | None = None) -> None:
        self.sources: list[Source] = (
            list(sources) if sources is not None else [cls() for cls in DEFAULT_CHAIN]
        )

    def extract(
        self,
        ticker: str,
        *,
        required_fields: Sequence[str] | None = None,
    ) -> ExtractResult:
        """
        required_fields: corta la cascada cuando esos campos ya están.
        None → todos los KPI_FIELDS (analysis).
        """
        symbol = ticker.upper().strip()
        if not symbol:
            raise ValueError("Ticker vacío")

        needed = tuple(required_fields) if required_fields is not None else KPI_FIELDS
        fields: dict = {}
        used: list[str] = []
        for src in self.sources:
            try:
                got = src.pull(symbol)
            except Exception as err:  # noqa: BLE001 — una source no tumba la cascada
                logger.warning("%s falló para %s: %s", src.name, symbol, err)
                continue
            if not got:
                logger.debug("%s sin datos para %s", src.name, symbol)
                continue
            before = len(fields)
            fields = merge_fields(fields, got)
            if len(fields) > before:
                used.append(src.name)
                logger.info("%s → %s (+%s campos)", src.name, symbol, len(fields) - before)
            if needed and all(fields.get(k) is not None for k in needed):
                break

        if not fields:
            names = ", ".join(s.name for s in self.sources)
            raise ValueError(f"Sin KPIs para {symbol} (sources: {names})")

        kpis = TickerKpis.from_mapping(symbol, fields)
        if kpis.populated_count() == 0:
            raise ValueError(f"Parse vacío para {symbol} vía {used or 'ninguna'}")
        logger.info("KPIs %s desde %s", symbol, " → ".join(used) or "?")
        return ExtractResult(kpis=kpis, sources=tuple(used))
