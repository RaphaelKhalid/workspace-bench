"""Port registry: every module in this package that defines ``PORTS = [...]`` is loaded."""

from __future__ import annotations

import importlib
import pkgutil

from .base import Port

_REGISTRY: list[Port] = []
_LOADED = False


def load_all() -> list[Port]:
    global _LOADED
    if not _LOADED:
        for m in pkgutil.iter_modules(__path__):
            if m.name.startswith("_") or m.name == "base":
                continue
            mod = importlib.import_module(f"{__name__}.{m.name}")
            _REGISTRY.extend(getattr(mod, "PORTS", []))
        _LOADED = True
    return _REGISTRY


def lookup(schema: dict) -> Port:
    hits = [p for p in load_all() if p.matches(schema)]
    if not hits:
        raise LookupError(f"no Jev port for schema {schema.get('name')!r}")
    if len(hits) > 1:
        raise LookupError(f"ambiguous ports for {schema.get('name')!r}: {[p.name for p in hits]}")
    return hits[0]
