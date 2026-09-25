"""
registry.py — Registro compartido de Tools.

Cada módulo de tool solo registra con `@tool`. El entrypoint (main) carga el
registry e invoca con `invoke(name, inputs)` — mismo contrato que un MCP.
"""

from __future__ import annotations

from typing import Any

TOOL_REGISTRY: dict[str, dict[str, Any]] = {}


class ToolError(Exception):
    """Fallo al resolver o ejecutar una tool."""


def tool(name: str, description: str, input_schema: dict):
    """Registra schema + handler. El handler recibe un dict y devuelve `{ok, data}`."""

    def decorator(func):
        TOOL_REGISTRY[name] = {
            "schema": {
                "name": name,
                "description": description,
                "input_schema": input_schema,
            },
            "handler": func,
        }
        return func

    return decorator


def invoke(name: str, inputs: dict | None = None) -> dict:
    entry = TOOL_REGISTRY.get(name)
    if entry is None:
        raise ToolError(f"Tool desconocida: {name}")
    result = entry["handler"](inputs or {})
    if not isinstance(result, dict):
        raise ToolError(f"{name} no devolvió un dict")
    if result.get("ok") is False:
        raise ToolError(str(result.get("error") or f"{name} falló"))
    return result


def tool_default(name: str, key: str, fallback: Any = None) -> Any:
    props = TOOL_REGISTRY.get(name, {}).get("schema", {}).get("input_schema", {}).get("properties", {})
    spec = props.get(key) or {}
    return spec["default"] if "default" in spec else fallback


def load_tools() -> None:
    """Importa los módulos con `@tool` para poblar el registry."""
    from tools import (  # noqa: F401
        add_watchlist,
        calculate_financials,
        calculate_score,
        compare_performance,
        discover,
        get_market_data,
    )
