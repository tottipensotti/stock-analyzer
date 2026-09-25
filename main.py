"""
main.py — Orquestador: CLI → invoke tools → outputs/run_*.

Pipeline:
  discover (opcional) → get_market_data (analysis + comparison)
  → calculate_financials → compare_performance → calculate_score
  → add_watchlist
"""

from __future__ import annotations

import logging
import sys
from collections.abc import Sequence
from pathlib import Path

from cli import build_parser, validate_mode_args
from tools.registry import ToolError, invoke, load_tools
from utils.helpers import (
    PORTFOLIO_PATH,
    WATCHLIST_PATH,
    dump_json,
    load_known_symbols,
    normalize_ticker_list,
    resolve_run_dir,
    write_csv_rows,
)
from utils.models import WATCHLIST_COLUMNS

logger = logging.getLogger(__name__)


def discovery_meta(payload: dict) -> dict[str, dict]:
    return {
        str(ticker).upper(): raw if isinstance(raw, dict) else {}
        for ticker, raw in (payload.get("meta") or {}).items()
    }


def persist_run(run_dir: Path, **artifacts: object) -> None:
    mapping = {
        "run": "run.json",
        "discovery": "discovery.json",
        "kpis": "kpis.json",
        "comparisons": "comparisons.json",
        "score": "score.json",
    }
    for key, filename in mapping.items():
        payload = artifacts.get(key)
        if payload is not None:
            dump_json(payload, run_dir / filename)
    summary = artifacts.get("summary")
    if isinstance(summary, str):
        (run_dir / "summary.txt").write_text(summary + "\n", encoding="utf-8")
    proposals = artifacts.get("proposals")
    if isinstance(proposals, list) and proposals:
        write_csv_rows(run_dir / "proposals.csv", WATCHLIST_COLUMNS, proposals)


def by_ticker(documents: Sequence[dict]) -> dict[str, dict]:
    return {str(doc.get("ticker", "")).upper(): doc for doc in documents if doc.get("ticker")}


def run_pipeline(
    tickers: Sequence[str],
    *,
    run_dir: Path,
    mode: str,
    meta_by_ticker: dict[str, dict] | None,
    filters: dict | None,
    write_watchlist: bool,
    workers: int,
    skip_known_for_watchlist: bool,
    fetch_peers: bool,
    peer_count: int,
    pause: float,
) -> int:
    symbols = normalize_ticker_list(tickers)
    if not symbols:
        logger.error("No hay tickers para procesar")
        return 1

    cache_dir = run_dir / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    persist_run(run_dir, run={"mode": mode, "tickers": symbols, "filters": filters or {}})

    print(f"2/5 market_data: {len(symbols)} tickers ({workers} workers)")
    try:
        subjects = invoke(
            "get_market_data",
            {
                "tickers": symbols,
                "mode": "analysis",
                "source": "auto",
                "workers": workers,
                "cache_dir": str(cache_dir),
            },
        )["data"]["tickers"]
        if not subjects:
            logger.error("Ningún ticker devolvió KPIs")
            return 1

        peer_tickers: list[str] = []
        if fetch_peers:
            peer_tickers = invoke(
                "discover",
                {"peer_documents": subjects, "peer_count": peer_count, "pause": pause},
            )["data"]["tickers"]
            if peer_tickers:
                print(f"   peers: {len(peer_tickers)}")

        benchmarks = invoke("compare_performance", {"entries": subjects, "list_benchmarks": True})["data"][
            "tickers"
        ]
        comparison_tickers = normalize_ticker_list([*peer_tickers, *benchmarks])
        existing = {str(doc.get("ticker", "")).upper() for doc in subjects}
        # Evitar re-fetch: subjects ya están en analysis (+ cache JSON de la corrida).
        comparison_tickers = [t for t in comparison_tickers if t not in existing]

        peer_docs: list[dict] = []
        if comparison_tickers:
            print(f"3/5 comparison_data: {len(comparison_tickers)} ({workers} workers)")
            peer_docs = invoke(
                "get_market_data",
                {
                    "tickers": comparison_tickers,
                    "mode": "comparison",
                    "source": "auto",
                    "workers": workers,
                    "cache_dir": str(cache_dir),
                },
            )["data"]["tickers"]
        else:
            print("3/5 comparison_data: (nada extra; subjects reutilizados)")

        # Universe = subjects (analysis, sin re-fetch) + peers/benchmarks (comparison).
        raw_universe = [*subjects, *peer_docs]
        print("4/5 financials + compare")
        financials = invoke("calculate_financials", {"documents": raw_universe})["data"]["tickers"]
        fin_by_ticker = by_ticker(financials)
        subject_fin = [fin_by_ticker[s] for s in symbols if s in fin_by_ticker]

        comparisons = invoke(
            "compare_performance",
            {
                "entries": financials,
                "subjects": symbols,
                "peers": peer_tickers,
            },
        )["data"]
        persist_run(
            run_dir,
            kpis={"count": len(financials), "tickers": financials},
            comparisons=comparisons,
        )

        print("5/5 score + watchlist")
        scored = invoke(
            "calculate_score",
            {
                "entries": subject_fin,
                "universe": financials,
                "comparisons": comparisons,
            },
        )["data"]
    except ToolError as err:
        persist_run(run_dir, run={"mode": mode, "tickers": symbols, "error": str(err)})
        logger.error("%s", err)
        return 1

    persist_run(run_dir, score=scored, summary=scored["summary"])
    print()
    print(scored["summary"])

    watch = invoke(
        "add_watchlist",
        {
            "scored": scored,
            "documents": financials,
            "meta_by_ticker": meta_by_ticker or {},
            "score_tickers": symbols if fetch_peers else None,
            "skip_known": skip_known_for_watchlist,
            "write": write_watchlist,
        },
    )["data"]
    rows = watch.get("rows") or []
    if not rows:
        print("Sin candidatos para la watchlist.")
        return 0
    persist_run(run_dir, proposals=rows)
    for row in rows:
        print(
            f"{row['ticker']:<6} {row['score']:>3} {row['kind']:<10} "
            f"Val {row['valuation']} Grw {row['growth']} Qua {row['quality']} "
            f"Bal {row['balance']} Mom {row['momentum']}  {row['relative_strength']}"
        )
    if watch.get("written"):
        print(f"Agregados {watch['written']} tickers a {watch.get('path') or WATCHLIST_PATH}")
    elif not write_watchlist:
        print("No se escribió la watchlist (--no-write-watchlist).")
    return 0


def run_tickers(
    tickers: Sequence[str],
    *,
    run_dir: Path,
    write_watchlist: bool,
    workers: int,
    peer_count: int,
    pause: float,
) -> int:
    symbols = normalize_ticker_list(tickers)
    print(f"1/5 tickers: {', '.join(symbols)}")
    return run_pipeline(
        symbols,
        run_dir=run_dir,
        mode="tickers",
        meta_by_ticker={},
        filters=None,
        write_watchlist=write_watchlist,
        workers=workers,
        skip_known_for_watchlist=False,
        fetch_peers=True,
        peer_count=peer_count,
        pause=pause,
    )


def run_discovery(
    *,
    run_dir: Path,
    sectors: Sequence[str],
    industries: Sequence[str],
    themes: Sequence[str],
    subthemes: Sequence[str],
    market_cap: str | None,
    limit: int,
    pause: float,
    write_watchlist: bool,
    workers: int,
) -> int:
    filters = {
        "sectors": list(sectors),
        "industries": list(industries),
        "themes": list(themes),
        "subthemes": list(subthemes),
        **({"market_cap": market_cap} if market_cap else {}),
    }
    labels = [
        *(f"sector:{s}" for s in sectors),
        *(f"industry:{i}" for i in industries),
        *(f"theme:{t}" for t in themes),
        *(f"subtheme:{s}" for s in subthemes),
        *([f"cap:{market_cap}"] if market_cap else []),
    ]
    print(f"1/5 discovery: {', '.join(labels) or 'default'}")
    known = load_known_symbols(PORTFOLIO_PATH) | load_known_symbols(WATCHLIST_PATH)
    try:
        discovered = invoke(
            "discover",
            {**filters, "limit": limit, "pause": pause, "known": sorted(known)},
        )["data"]
    except ToolError as err:
        persist_run(run_dir, run={"mode": "discovery", "filters": filters, "error": str(err)})
        logger.error("Screener: %s", err)
        return 1
    persist_run(
        run_dir,
        run={"mode": "discovery", "filters": filters},
        discovery={**discovered, "filters": filters},
    )
    tickers = discovered.get("tickers") or []
    if not tickers:
        print("No hay tickers nuevos.")
        return 0
    return run_pipeline(
        tickers,
        run_dir=run_dir,
        mode="discovery",
        meta_by_ticker=discovery_meta(discovered),
        filters=filters,
        write_watchlist=write_watchlist,
        workers=workers,
        skip_known_for_watchlist=True,
        fetch_peers=False,
        peer_count=0,
        pause=pause,
    )


def main(argv: Sequence[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    load_tools()
    args = build_parser().parse_args(argv)
    if args.list is not None:
        print(invoke("discover", {"list": args.list})["data"]["listing"])
        return 0
    mode_error = validate_mode_args(args)
    if mode_error:
        logging.error("%s", mode_error)
        return 1
    if args.limit < 1 or args.workers < 1 or args.peers < 0:
        logging.error("Valores inválidos en --limit / --workers / --peers")
        return 1
    run_dir = resolve_run_dir(args.run)
    print(f"run: {run_dir}")
    if args.ticker:
        return run_tickers(
            args.ticker,
            run_dir=run_dir,
            write_watchlist=args.write_watchlist,
            workers=args.workers,
            peer_count=args.peers,
            pause=args.pause,
        )
    return run_discovery(
        run_dir=run_dir,
        sectors=args.sector,
        industries=args.industry,
        themes=args.theme,
        subthemes=args.subtheme,
        market_cap=args.market_cap,
        limit=args.limit,
        pause=args.pause,
        write_watchlist=args.write_watchlist,
        workers=args.workers,
    )


if __name__ == "__main__":
    sys.exit(main())
