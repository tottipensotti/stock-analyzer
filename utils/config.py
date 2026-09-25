"""Loader de docs/config.yml — configuración centralizada del pipeline."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

CONFIG_PATH = Path(__file__).resolve().parent.parent / "docs" / "config.yml"


@lru_cache(maxsize=1)
def get_config() -> dict[str, Any]:
    raw = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"Config inválida: {CONFIG_PATH}")
    return raw


def cfg(*keys: str, default: Any = None) -> Any:
    """Acceso anidado: cfg('score', 'block_max', 'valuation')."""
    node: Any = get_config()
    for key in keys:
        if not isinstance(node, dict) or key not in node:
            return default
        node = node[key]
    return node


def score_block_max(block: str) -> int:
    return int((cfg("score", "block_max") or {}).get(block, 0))


def special_categories() -> frozenset[str]:
    return frozenset(str(item) for item in (cfg("classification", "special_categories") or []))


def confirmed_strength() -> frozenset[str]:
    return frozenset(str(s) for s in (cfg("score", "confirmed_strength") or ["LEADING", "STRONG"]))
