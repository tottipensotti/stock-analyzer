"""cli.py — argparse y validación de modos CLI."""

from __future__ import annotations

import argparse

from tools.registry import tool_default


def validate_mode_args(args: argparse.Namespace) -> str | None:
    if args.list is not None:
        return None
    has_ticker, has_discovery = bool(args.ticker), bool(args.discovery)
    has_filters = bool(args.sector or args.industry or args.theme or args.subtheme or args.market_cap)
    if has_ticker and has_discovery:
        return "Usá --ticker o --discovery, no ambos"
    if has_ticker and has_filters:
        return "Con --ticker no aplican filtros de screener"
    if has_ticker or (has_discovery and has_filters):
        return None
    if has_discovery:
        return "Con --discovery pasá al menos un filtro (o --list)"
    if has_filters:
        return "Para usar filtros de screener agregá --discovery"
    return "Pasá --ticker TICKER... o --discovery con filtros (o --list)"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Pipeline: --ticker o --discovery → KPIs → score → watchlist."
    )
    parser.add_argument("--ticker", nargs="+", default=[], metavar="TICKER")
    parser.add_argument("--discovery", action="store_true")
    parser.add_argument("--sector", nargs="+", default=[], metavar="SECTOR")
    parser.add_argument("--industry", nargs="+", default=[], metavar="INDUSTRY")
    parser.add_argument("--theme", nargs="+", default=[], metavar="THEME")
    parser.add_argument("--subtheme", nargs="+", default=[], metavar="SUBTHEME")
    parser.add_argument("--market-cap", default=None, metavar="CAP", dest="market_cap")
    parser.add_argument("--list", nargs="?", const="", default=None, metavar="QUERY")
    parser.add_argument("--limit", type=int, default=tool_default("discover", "limit", 100))
    parser.add_argument("--pause", type=float, default=tool_default("discover", "pause", 0.8))
    parser.add_argument("--peers", type=int, default=tool_default("discover", "peer_count", 10), metavar="N")
    parser.add_argument(
        "--workers", type=int, default=tool_default("get_market_data", "workers", 8), metavar="N"
    )
    parser.add_argument(
        "--run",
        "--output",
        dest="run",
        default=None,
        help="Carpeta outputs/run_* (default: crea una nueva)",
    )
    parser.add_argument(
        "--write-watchlist",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Append propuestas a docs/watchlist.csv (default: sí)",
    )
    return parser
