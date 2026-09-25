"""Source ABC + merge compartido hacia campos KPI en inglés."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class Source(ABC):
    """Una fuente: solo el camino distinto (fetch + normalización a dict de campos)."""

    name: str

    @abstractmethod
    def pull(self, ticker: str) -> dict[str, Any] | None:
        """Devuelve campos normalizados (keys de METRICS + meta) o None si falló."""
        raise NotImplementedError


def merge_fields(base: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    """Rellena huecos: no pisa valores ya presentes (prioridad = orden de sources)."""
    merged = dict(base)
    for key, value in incoming.items():
        if value is None or value == "":
            continue
        if merged.get(key) is None:
            merged[key] = value
    return merged
