"""Text rendering for score batch summaries."""

from __future__ import annotations

from utils.config import cfg
from utils.helpers import format_alpha, format_completeness
from utils.models import ScoreBatch, ScoreResult


def render_tier_table(results: list[ScoreResult], title: str) -> list[str]:
    if not results:
        return [title, "(sin tickers)", ""]
    lines = [
        title,
        (
            f"{'#':<4} {'Tk':<6} {'Nombre':<24} {'Sc':>4} {'Val':>3} {'Grw':>3} {'Qua':>3} "
            f"{'Bal':>3} {'Mom':>3}  {'ETF':<4} {'αETF':>7} {'αSPY':>7} {'Str':<8} {'Flg':<3}"
        ),
        "-" * 108,
    ]
    for index, result in enumerate(results, start=1):
        marks = format_completeness(result.score_status).strip()
        marks += "!" if result.earnings_cash_flag else ""
        marks += "c" if result.cycle_peak else ""
        lines.append(
            f"{index:<4} {result.ticker:<6} {(result.name or '')[:24]:<24} {f'{result.score}{marks}':>4} "
            f"{result.bloque_1:>3} {result.bloque_2:>3} {result.bloque_3:>3} "
            f"{result.bloque_4:>3} {result.bloque_5:>3}  {(result.benchmark_etf or '-'):<4} "
            f"{format_alpha(result.alpha_year_vs_etf):>7} {format_alpha(result.alpha_year_vs_spy):>7} "
            f"{(result.relative_strength or 'N/A')[:8]:<8} {result.score_status:<3}"
        )
    return lines + [""]


def _cross_lines(results: list[ScoreResult]) -> list[str]:
    if not results:
        return ["(ninguna)"]
    return [
        f"  {item.ticker:<6} {item.score:>3}  {item.relative_strength:<8} "
        f"Val {item.bloque_1:>2}  Qua {item.bloque_3:>2}  Bal {item.bloque_4:>2}"
        for item in results
    ]


def render_summary(batch: ScoreBatch) -> str:
    if not batch.core and not batch.speculative:
        return "No hay acciones para puntuar (solo ETFs o datos inválidos)."
    score_max = int(cfg("score", "max", default=100))
    confirmed_min = int(cfg("score", "confirmed_min_score", default=70))
    quality_high = int(cfg("score", "quality_high", default=20))
    balance_high = int(cfg("score", "balance_high", default=10))
    valuation_floor = int(cfg("score", "valuation_floor", default=10))
    lines = [
        *render_tier_table(batch.core, f"=== CORE ({len(batch.core)}) ==="),
        *render_tier_table(batch.speculative, f"=== SPECULATIVE ({len(batch.speculative)}) ==="),
        "Bloques: Val | Grw | Qua (ROIC-WACC, márgenes, FCF/NI) | Bal | Mom (incl. αETF/αSPY)",
        "=== CONFIRMADAS ===",
        *_cross_lines(batch.confirmed),
        "",
        "=== DISLOCADAS ===",
        *_cross_lines(batch.dislocated),
        "",
        f"Flags: p=partial, !=earnings↑ caja↓, c=año pico | Score máx: {score_max}",
        (
            f"Cruces: confirmada >={confirmed_min} LEADING/STRONG; "
            f"dislocada Qua>={quality_high} Bal>={balance_high} Val>={valuation_floor} WEAK."
        ),
    ]
    if batch.skipped_minimal:
        lines.append(f"Minimal omitidos: {', '.join(batch.skipped_minimal)}")
    if batch.skipped_etfs:
        lines.append(f"ETFs omitidos: {', '.join(batch.skipped_etfs)}")
    return "\n".join(lines)
