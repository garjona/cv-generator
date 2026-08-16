from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def adapt_context_with_mapping(context: dict[str, Any], adapter_file: Path | None) -> dict[str, Any]:
    if adapter_file is None:
        return dict(context)
    if not adapter_file.exists():
        raise FileNotFoundError(f"Archivo de adapter no encontrado: {adapter_file}")

    spec = json.loads(adapter_file.read_text(encoding="utf-8-sig"))
    if not isinstance(spec, dict):
        raise ValueError("El adapter debe ser un JSON de objeto.")

    mapping = spec.get("mapping")
    if not isinstance(mapping, dict):
        raise ValueError("El adapter debe contener `mapping` como objeto.")

    adapted = _resolve_mapping_node(mapping, context)
    static = spec.get("static", {})
    if isinstance(static, dict):
        adapted = _deep_merge(adapted, static)
    return adapted


def _resolve_mapping_node(node: Any, source: dict[str, Any]) -> Any:
    if isinstance(node, str):
        return _read_path(source, node)
    if isinstance(node, list):
        return [_resolve_mapping_node(item, source) for item in node]
    if isinstance(node, dict):
        if "$path" in node:
            path = str(node.get("$path", "")).strip()
            value = _read_path(source, path)
            if value is None and "$default" in node:
                return node.get("$default")
            return value
        out: dict[str, Any] = {}
        for key, value in node.items():
            out[key] = _resolve_mapping_node(value, source)
        return out
    return node


def _read_path(source: Any, path: str) -> Any:
    if not path:
        return source
    current: Any = source
    for token in path.split("."):
        if isinstance(current, dict):
            if token not in current:
                return None
            current = current[token]
            continue
        if isinstance(current, list) and token.isdigit():
            idx = int(token)
            if idx < 0 or idx >= len(current):
                return None
            current = current[idx]
            continue
        return None
    return current


def _deep_merge(base: Any, patch: Any) -> Any:
    if isinstance(base, dict) and isinstance(patch, dict):
        merged = dict(base)
        for key, value in patch.items():
            merged[key] = _deep_merge(merged.get(key), value)
        return merged
    return patch if patch is not None else base
