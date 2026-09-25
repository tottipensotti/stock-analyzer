# Pipeline — KPIs e Investment Quality Score

Scripts para extraer métricas de mercado y calcular un **Investment Quality Score (0–100)** alineado con [`agents/capa-1-instrumento.md`](agents/capa-1-instrumento.md).

## Setup (venv + pip)

```bash
cd stocks-analyzer
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Correr siempre desde la raíz del proyecto (`python main.py ...`) para que `tools` / `utils` / `cli` importen bien.

## Arquitectura

```
main.py  (orquestador) ← cli.py
  ├─ invoke(discover)
  ├─ invoke(get_market_data)       # mode=analysis | comparison + cache JSON
  ├─ invoke(calculate_financials)
  ├─ invoke(compare_performance)
  ├─ invoke(calculate_score)
  └─ invoke(add_watchlist)
       └─ outputs/run_*/ (+ cache/) + docs/watchlist.csv
```

Shared: `utils/models` (`MarketDocument`, provenance `sources`), `utils/helpers`, `utils/scoring/`, `utils/extractors/` (`KpiGateway` Finviz → Stooq → yfinance). Tunables de score/clasificación: [`docs/config.yml`](docs/config.yml).

## Uso

```bash
python main.py --ticker META GOOGL TSLA
python main.py --ticker AAPL --workers 4 --peers 10
python main.py --ticker AAPL --run outputs/run_202609251531000
python main.py --ticker AAPL --no-write-watchlist

python main.py --list
python main.py --list healthcare
python main.py --discovery --sector healthcare
python main.py --discovery --industry semiconductors --market-cap midover
```

## Layout

```
main.py / cli.py
utils/
  models.py              # dataclasses + MarketDocument + METRICS
  helpers.py             # parseo, HTTP, SMA/RSI, cache JSON, IO
  scoring/               # Investment Quality Score
  extractors/            # KpiGateway + Source
tools/
  registry.py
  discover.py
  get_market_data.py
  calculate_financials.py
  compare_performance.py
  calculate_score.py
  add_watchlist.py
docs/
  catalog.yml
  config.yml             # scores, ponderaciones, ETF/crypto, workers…
  watchlist.csv
outputs/run_*/           # artifacts + cache/{TICKER}.json
```

## Tools

| Tool | Input | Output |
|------|-------|--------|
| `discover` | filtros / `list` / `peer_documents` | tickers (+ meta) |
| `get_market_data` | tickers + `mode` + opcional `cache_dir` | `MarketDocument`s (con `sources`) |
| `calculate_financials` | documents | docs + FCF yield / FCF/NI |
| `compare_performance` | entries (+ subjects/peers) | alpha vs SPY/ETF/peers |
| `calculate_score` | entries + universe + comparisons | rankings + summary |
| `add_watchlist` | scored + documents | proposals (+ append CSV) |

## Score (resumen)

Máximo 100: Val 25 | Grw 20 | Qua 30 | Bal 15 | Mom 10. Tiers Core / Speculative. Confirmadas (≥70 + LEADING/STRONG) y dislocadas (Qua/Bal/Val altos + WEAK).
